"""Hansı xəbərin harada paylaşılacağını seçmək və paylaşmaq."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from . import telegram
from .config import NETWORK_LABELS, Config
from .social import MetaPage, SocialError, Threads, wait_until_public
from .store import Store
from .telegram import TelegramError, hashtag
from .text import parse_iso, to_ascii
from .tokens import threads_token

log = logging.getLogger(__name__)

MAX_TRIES = 3


# ------------------------------------------------------------------ seçim
def _keyword_ok(item: dict, include: list[str], exclude: list[str]) -> bool:
    hay = to_ascii(f"{item['title']} {item.get('teaser', '')} {item.get('category', '')}")
    if exclude and any(to_ascii(k) in hay for k in exclude if k.strip()):
        return False
    if include and not any(to_ascii(k) in hay for k in include if k.strip()):
        return False
    return True


def _round_robin(pool: list[dict], n: int) -> list[dict]:
    """Ən təzə xəbərləri seçir, amma eyni mənbədən ardıcıl çox götürmür."""
    if n <= 0:
        return []
    by_src: dict[str, list[dict]] = defaultdict(list)
    for it in sorted(pool, key=lambda i: i["published"], reverse=True):
        by_src[it["source"]].append(it)
    queues = sorted(by_src.values(), key=lambda q: q[0]["published"], reverse=True)
    picked: list[dict] = []
    while queues and len(picked) < n:
        nxt = []
        for q in queues:
            if len(picked) >= n:
                break
            picked.append(q.pop(0))
            if q:
                nxt.append(q)
        queues = nxt
    return picked


def select_queue(cfg: Config, store: Store, now: datetime) -> dict[str, list[dict]]:
    nets = cfg.active_networks()
    pub = cfg.publish
    max_age = timedelta(hours=float(pub["max_age_hours"]))
    include, exclude = list(pub["include_keywords"]), list(pub["exclude_keywords"])
    last_post = store.state.setdefault("last_post", {})
    result: dict[str, list[dict]] = {}

    candidates = []
    for it in store.items:
        published = parse_iso(it["published"])
        src = cfg.source(it["source"])
        # köhnəlmiş növbələri təmizlə
        for net, p in it.get("posts", {}).items():
            if p.get("status") == "queued" and published < now - 2 * max_age:
                p["status"] = "expired"
        if published < now - max_age or not src or not src.social:
            continue
        if _keyword_ok(it, include, exclude):
            candidates.append(it)

    for net in nets:
        conf = cfg.sections[net]
        # Əvvəlki növbəni sıfırla: hər dəfə ən təzə xəbərlər yenidən seçilir,
        # ona görə köhnə növbə yeni xəbərlərin qarşısını kəsmir.
        previous: dict[str, dict] = {}
        for it in store.items:
            rec = it.get("posts", {}).get(net)
            if rec and rec.get("status") == "queued":
                previous[it["id"]] = it["posts"].pop(net)
        interval = timedelta(minutes=float(conf.get("min_interval_minutes", 0)))
        last = last_post.get(net)
        if interval and last and now - parse_iso(last) < interval:
            result[net] = []
            continue
        pool = [it for it in candidates if net not in it.get("posts", {})]
        picked = _round_robin(pool, int(conf.get("max_per_run", 1)))
        for it in picked:
            it.setdefault("posts", {})[net] = previous.get(it["id"], {"status": "queued", "tries": 0})
        result[net] = picked
    return result


# ------------------------------------------------------------------ mətnlər
def page_url(cfg: Config, item: dict) -> str:
    return f"{cfg.site_url}/xeber/{item['slug']}.html" if cfg.site_url else item["link"]


def card_url(cfg: Config, item: dict) -> str:
    return f"{cfg.site_url}/kart/{item['id']}.jpg"


def _body(item: dict) -> str:
    return item.get("summary") or item.get("teaser") or ""


def _tags(cfg: Config, item: dict, source_name: str) -> str:
    if not cfg.publish.get("hashtags", True):
        return ""
    tags = [hashtag(item.get("category", "")), hashtag(source_name), hashtag(cfg.site["name"])]
    return " ".join(dict.fromkeys(t for t in tags if t))


def facebook_text(cfg: Config, item: dict, source_name: str) -> str:
    parts = [item["title"], _body(item), f"Mənbə: {source_name}", _tags(cfg, item, source_name)]
    return "\n\n".join(p for p in parts if p)


def instagram_caption(cfg: Config, item: dict, source_name: str) -> str:
    host = urlsplit(cfg.site_url).netloc if cfg.site_url else ""
    more = f"Mənbə: {source_name}"
    if host:
        more += f"\nTam xəbər: {host} (link profildədir)"
    parts = [item["title"], _body(item), more, _tags(cfg, item, source_name)]
    return "\n\n".join(p for p in parts if p)[:2100]


def threads_text(cfg: Config, item: dict, source_name: str) -> str:
    limit = 400  # Threads limiti 500-dür; Azərbaycan hərfləri üçün ehtiyat saxlanılır
    head = item["title"]
    tail = f"Mənbə: {source_name}"
    body = _body(item)
    room = limit - len(head) - len(tail) - 4
    if body and room > 60:
        if len(body) > room:
            body = body[: room - 1].rsplit(" ", 1)[0] + "…"
        return f"{head}\n\n{body}\n\n{tail}"
    return f"{head}\n\n{tail}"[:limit]


# ------------------------------------------------------------------ paylaşım
def notify_admin(cfg: Config, store: Store, key: str, text: str, every_hours: int = 6) -> None:
    """Sahibə şəxsi Telegram mesajı (TELEGRAM_ADMIN_CHAT verilibsə)."""
    chat, token = cfg.secret("TELEGRAM_ADMIN_CHAT"), cfg.secret("TELEGRAM_BOT_TOKEN")
    log.warning("XƏBƏRDARLIQ: %s", text)
    if not chat or not token:
        return
    notes = store.state.setdefault("admin_notes", {})
    now = datetime.now().astimezone()
    last = notes.get(key)
    if last and now - parse_iso(last) < timedelta(hours=every_hours):
        return
    try:
        telegram.send_message(token, chat, f"⚠️ {cfg.site['name']} botu\n\n{text}", False)
        notes[key] = now.isoformat(timespec="seconds")
    except TelegramError as exc:
        log.warning("Admin bildirişi göndərilmədi: %s", exc)


def _maybe_refresh_threads(cfg: Config, store: Store, client: Threads, now: datetime) -> None:
    last = store.state.get("threads_refreshed")
    if last and now - parse_iso(last) < timedelta(days=7):
        return
    try:
        data = client.refresh_token()
    except SocialError as exc:
        notify_admin(cfg, store, "threads_refresh",
                     f"Threads tokeni yenilənmədi: {exc}. README-dəki addımlarla yeni token yaradın.")
        return
    store.state["threads_refreshed"] = now.isoformat()
    days = int(data.get("expires_in", 0)) // 86400
    log.info("Threads tokeni yeniləndi, %s gün etibarlıdır", days)
    new = data.get("access_token", "")
    if new and new != client.token:
        notify_admin(cfg, store, "threads_new_token",
                     "Threads tokeni 60 gündən sonra bitəcək. Avtomatik uzadılması üçün "
                     "THREADS_APP_SECRET açarını əlavə edin (README, Threads bölməsi).",
                     every_hours=24 * 7)


def publish_queue(cfg: Config, store: Store, now: datetime) -> dict[str, int]:
    stats: dict[str, int] = {}
    last_post = store.state.setdefault("last_post", {})
    tz_now = now.isoformat()
    meta: MetaPage | None = None
    threads: Threads | None = None
    if cfg.network_ready("facebook")[0] or cfg.network_ready("instagram")[0]:
        meta = MetaPage(cfg.secret("FACEBOOK_PAGE_TOKEN"), cfg.facebook["graph_version"])
    if cfg.network_ready("threads")[0]:
        app_secret = cfg.secret("THREADS_APP_SECRET")
        if app_secret:
            token, warning = threads_token(cfg.secret("THREADS_TOKEN"), app_secret, store.dir, now)
            threads = Threads(token)
            if warning:
                notify_admin(cfg, store, "threads_token", warning, every_hours=24)
        else:
            threads = Threads(cfg.secret("THREADS_TOKEN"))
            _maybe_refresh_threads(cfg, store, threads, now)

    for net in cfg.active_networks():
        todo = [it for it in store.items
                if it.get("posts", {}).get(net, {}).get("status") == "queued"]
        todo.sort(key=lambda i: i["published"])  # köhnədən təzəyə: kanalda ən təzəsi üstdə qalır
        sent = 0
        for it in todo:
            src = cfg.source(it["source"])
            sname = src.name if src else it["source"]
            rec = it["posts"][net]
            try:
                if net == "telegram":
                    text = telegram.format_message(it, sname, page_url(cfg, it),
                                                   cfg.publish.get("hashtags", True))
                    pid = telegram.send_message(cfg.secret("TELEGRAM_BOT_TOKEN"),
                                                cfg.secret("TELEGRAM_CHANNEL"), text,
                                                bool(cfg.telegram.get("link_preview")))
                elif net == "facebook":
                    pid = meta.post_to_page(facebook_text(cfg, it, sname), page_url(cfg, it))
                elif net == "instagram":
                    img = card_url(cfg, it)
                    if not wait_until_public(img):
                        raise SocialError(f"şəkil saytda açılmadı: {img}")
                    pid = meta.post_to_instagram(img, instagram_caption(cfg, it, sname),
                                                 alt_text=it["title"])
                elif net == "threads":
                    pid = threads.post(threads_text(cfg, it, sname), page_url(cfg, it))
                else:
                    continue
            except (TelegramError, SocialError) as exc:
                rec["tries"] = rec.get("tries", 0) + 1
                rec["error"] = str(exc)[:300]
                if rec["tries"] >= MAX_TRIES:
                    rec["status"] = "failed"
                log.warning("  ✗ %s: %s — %s", NETWORK_LABELS[net], it["title"][:60], exc)
                notify_admin(cfg, store, f"fail_{net}",
                             f"{NETWORK_LABELS[net]} paylaşımı alınmadı: {exc}")
                if "token" in str(exc).lower() or "HTTP 401" in str(exc) or "HTTP 403" in str(exc):
                    break  # açar problemi — bu şəbəkəni bu dəfəlik dayandır
                continue
            rec.update({"status": "sent", "id": str(pid), "at": tz_now})
            rec.pop("error", None)
            last_post[net] = tz_now
            sent += 1
            log.info("  ✓ %s: %s", NETWORK_LABELS[net], it["title"][:70])
            time.sleep(3 if net == "telegram" else 5)
        stats[net] = sent
    return stats
