"""Botun giriş nöqtəsi.

    python -m bot.run collect   # xəbərləri topla, paylaşım növbəsini seç, saytı qur
    python -m bot.run publish   # növbədəki xəbərləri Telegram/Facebook/Instagram/Threads-ə göndər
    python -m bot.run build     # yalnız saytı yenidən qur
    python -m bot.run all       # hamısı birlikdə (öz kompüterinizdə sınaq üçün)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from .build import build_site
from .config import NETWORK_LABELS, Config, load_config
from .publish import select_queue, publish_queue
from .sources import fetch_source
from .store import Store
from .summarize import ai_summary, fetch_article, source_teaser
from .text import now_utc, parse_iso, short_hash, slugify

log = logging.getLogger("bot")


def _session(cfg: Config) -> requests.Session:
    s = requests.Session()
    name = slugify(cfg.site["name"]).replace("-", "") or "xeber"
    contact = f"; +{cfg.site_url}" if cfg.site_url else ""
    s.headers.update({
        "User-Agent": f"Mozilla/5.0 (compatible; {name}-bot/1.0{contact})",
        "Accept-Language": "az,en;q=0.7",
    })
    return s


def collect(cfg: Config, store: Store) -> list[dict]:
    now = now_utc()
    session = _session(cfg)
    timeout = float(cfg.fetch["timeout_seconds"])
    delay = float(cfg.fetch["delay_seconds"])
    limit = int(cfg.fetch["max_new_per_source"])
    src_state = store.state.setdefault("sources", {})
    added: list[dict] = []

    log.info("Mənbələr oxunur…")
    for src in cfg.sources:
        if not src.enabled:
            continue
        try:
            entries = fetch_source(src, session, timeout)
        except (requests.RequestException, ET.ParseError, ValueError) as exc:
            log.warning("  ✗ %s: %s", src.name, exc)
            src_state[src.id] = {**src_state.get(src.id, {}), "error": str(exc)[:200],
                                 "checked": now.isoformat()}
            continue
        fresh = [e for e in entries if store.is_new(e)]
        fresh.sort(key=lambda e: e["published"] or now, reverse=True)
        count = 0
        for e in fresh[:limit]:
            store.mark_seen(e["link"])
            if store.is_duplicate_title(e["title"]):
                continue
            published = e["published"] or now
            if published > now:
                published = now
            iid = short_hash(e["link"])
            item = {
                "id": iid,
                "slug": f"{slugify(e['title'])}-{iid[:6]}",
                "title": e["title"],
                "link": e["link"],
                "source": src.id,
                "category": e["category"],
                "published": published.isoformat(),
                "added": now.isoformat(),
                "teaser": source_teaser(e["description"], "", e["title"]),
                "summary": "",
            }
            store.add(item)
            added.append(item)
            count += 1
        src_state[src.id] = {"ok": now.isoformat(), "checked": now.isoformat(),
                             "in_feed": len(entries), "new": count}
        log.info("  ✓ %-12s lentdə %3d, yeni %2d", src.name, len(entries), count)

    # Paylaşım növbəsi
    queue = select_queue(cfg, store, now)
    for net, lst in queue.items():
        if lst:
            log.info("Növbə — %s: %s xəbər", NETWORK_LABELS[net], len(lst))
    for net in ("telegram", "facebook", "instagram", "threads"):
        ok, why = cfg.network_ready(net)
        if not ok:
            log.info("%s paylaşımı aktiv deyil: %s", NETWORK_LABELS[net], why)

    # Qısa təsvirlər və xülasələr
    pages: dict[str, dict] = {}

    def page(it: dict) -> dict:
        if it["link"] not in pages:
            pages[it["link"]] = fetch_article(it["link"], session, timeout)
            time.sleep(delay)
        return pages[it["link"]]

    if cfg.summary.get("fetch_article_page", True):
        for it in added:
            if not it["teaser"]:
                it["teaser"] = source_teaser("", page(it)["description"], it["title"])

    if cfg.ai_enabled:
        queued_ids = {it["id"] for lst in queue.values() for it in lst}
        targets = [it for it in store.items if it["id"] in queued_ids]
        if not cfg.summary.get("ai_only_for_social", True):
            targets += [it for it in added if it["id"] not in queued_ids]
        done = 0
        for it in targets:
            if it.get("summary") or it.get("ai_tried"):
                continue
            it["ai_tried"] = True
            text = page(it)["text"]
            summary = ai_summary(it["title"], text, cfg.secret("ANTHROPIC_API_KEY"),
                                 cfg.summary["ai_model"])
            if summary:
                it["summary"] = summary
                done += 1
        if targets:
            log.info("Süni intellekt xülasəsi: %s/%s", done, len(targets))

    store.state["last_collect"] = now.isoformat()
    log.info("Cəmi yeni xəbər: %s", len(added))
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bot.run")
    ap.add_argument("command", choices=["collect", "publish", "build", "all"])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="_site")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    cfg = load_config(args.config)
    store = Store(Path(args.data))
    keep = int(cfg.site["keep_items"])
    # Söndürülmüş mənbələrin xəbərlərini saytdan və növbədən çıxar
    active = {s.id for s in cfg.sources if s.enabled}
    before = len(store.items)
    store.items = [i for i in store.items if i.get("source") in active]
    if len(store.items) != before:
        log.info("Söndürülmüş mənbələrin %s xəbəri silindi", before - len(store.items))

    if args.command in ("collect", "all"):
        collect(cfg, store)
        store.save(keep)
    if args.command in ("collect", "build", "all"):
        updated = parse_iso(store.state.get("last_collect") or now_utc().isoformat())
        build_site(cfg, store.items, Path(args.out), updated)
    if args.command in ("publish", "all"):
        stats = publish_queue(cfg, store, now_utc())
        sent = ", ".join(f"{NETWORK_LABELS[k]}: {v}" for k, v in stats.items()) or "aktiv şəbəkə yoxdur"
        log.info("Paylaşıldı — %s", sent)
        store.save(keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
