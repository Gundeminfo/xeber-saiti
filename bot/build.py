"""Statik saytı qurur: _site/ qovluğuna HTML, RSS, sitemap, axtarış və şəkil-kartlar."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .cards import render_card, render_site_card
from .config import AD_SLOTS, Config
from .text import fmt_datetime, fmt_day, fmt_time, parse_iso, to_ascii, tz

log = logging.getLogger(__name__)


def _env(root: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def _prepare(cfg: Config, items: list[dict], zone) -> list[dict]:
    out = []
    for it in items:
        dt = parse_iso(it["published"])
        src = cfg.source(it["source"])
        out.append({
            **it,
            "dt": dt,
            "time": fmt_time(dt, zone),
            "day": fmt_day(dt, zone),
            "when": fmt_datetime(dt, zone),
            "iso": dt.isoformat(),
            "path": f"xeber/{it['slug']}.html",
            "src_name": src.name if src else it["source"],
            "src_color": src.color if src else "#5b6b78",
            "body": it.get("summary") or it.get("teaser") or "",
        })
    return out


def _group_by_day(items: list[dict], ad_after: int = 0) -> list[dict]:
    """Xəbərləri günlərə bölür. ad_after > 0 olarsa, həmin xəbərdən sonra reklam yeri qeyd olunur."""
    groups: list[dict] = []
    for n, it in enumerate(items, start=1):
        if not groups or groups[-1]["day"] != it["day"]:
            groups.append({"day": it["day"], "entries": [], "ad_at": 0})
        groups[-1]["entries"].append(it)
        if ad_after and n == ad_after and n < len(items):
            groups[-1]["ad_at"] = len(groups[-1]["entries"])
    return groups


def _ads(cfg: Config) -> dict:
    a = cfg.ads
    slots = {}
    for name in AD_SLOTS:
        s = dict(a[name])
        s["active"] = bool(a["enabled"] and s["enabled"]
                           and (s["html"] or s["banners"] or a["placeholder"]))
        slots[name] = s
    return {
        "enabled": bool(a["enabled"]),
        "label": a["label"],
        "placeholder_text": a["placeholder_text"],
        "contact_url": a["contact_url"],
        "head_html": str(a.get("head_html", "")).strip() if a["enabled"] else "",
        "slots": slots,
        "rails": slots["left"]["active"] or slots["right"]["active"],
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_site(cfg: Config, items: list[dict], out_dir: Path, updated: datetime) -> int:
    root = cfg.root_dir
    zone = tz(cfg.site["timezone"])
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(root / "static", out / "static")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    env = _env(root)
    items = _prepare(cfg, sorted(items, key=lambda i: i["published"], reverse=True), zone)
    site_url = cfg.site_url
    socials = [
        {"id": net, "label": label, "url": cfg.sections[net].get("url", "")}
        for net, label in (("telegram", "Telegram"), ("instagram", "Instagram"),
                           ("facebook", "Facebook"), ("threads", "Threads"))
        if cfg.sections[net].get("url")
    ]
    counts = {s.id: 0 for s in cfg.sources}
    for it in items:
        counts[it["source"]] = counts.get(it["source"], 0) + 1
    sources = [{"id": s.id, "name": s.name, "color": s.color, "count": counts.get(s.id, 0)}
               for s in cfg.sources if s.enabled or counts.get(s.id)]

    common = {
        "site": cfg.site,
        "site_url": site_url,
        "socials": socials,
        "sources": sources,
        "updated": fmt_datetime(updated, zone),
        "updated_iso": updated.isoformat(),
        "year": updated.astimezone(zone).year,
        "ads": _ads(cfg),
    }
    lent_after = int(cfg.ads.get("lent_after", 6)) if common["ads"]["slots"]["lent"]["active"] else 0
    ads_txt = str(cfg.ads.get("ads_txt", "")).strip()
    if ads_txt:
        _write(out / "ads.txt", ads_txt + "\n")

    # ---- Şəkil-kartlar: sosial şəbəkəyə gedən son xəbərlər üçün
    cards_dir = out / "kart"
    render_site_card(cfg.site["name"], cfg.site["tagline"], out / "static" / "og.jpg")
    card_ids: set[str] = set()
    cutoff = updated - timedelta(hours=48)
    for it in items:
        if it["dt"] < cutoff:
            break
        if any(p.get("status") in ("queued", "sent") for p in it.get("posts", {}).values()):
            render_card(it, it["src_name"], it["src_color"], cfg.site["name"], site_url,
                        zone, cards_dir / f"{it['id']}.jpg")
            card_ids.add(it["id"])

    # ---- Ana səhifə (səhifələnmiş)
    per_page = int(cfg.site["per_page"])
    max_pages = int(cfg.site["max_pages"])
    listed = items[: per_page * max_pages]
    pages = max(1, -(-len(listed) // per_page))
    tpl_list = env.get_template("index.html")
    for n in range(1, pages + 1):
        chunk = listed[(n - 1) * per_page: n * per_page]
        r = "./" if n == 1 else "../"
        if n == 1:
            prev_url = None
        elif n == 2:
            prev_url = "../index.html"
        else:
            prev_url = f"{n - 1}.html"
        if n == pages:
            next_url = None
        else:
            next_url = "sehife/2.html" if n == 1 else f"{n + 1}.html"
        html = tpl_list.render(**common, root=r, groups=_group_by_day(chunk, lent_after), page=n, pages=pages,
                               prev_url=prev_url, next_url=next_url, nav="home",
                               canonical=f"{site_url}/" if n == 1 else f"{site_url}/sehife/{n}.html")
        _write(out / ("index.html" if n == 1 else f"sehife/{n}.html"), html)

    # ---- Xəbər səhifələri
    tpl_article = env.get_template("article.html")
    for idx, it in enumerate(items):
        same_src = [x for x in items[max(0, idx - 40): idx + 40]
                    if x["source"] == it["source"] and x["id"] != it["id"]][:3]
        latest = [x for x in items[:12] if x["id"] != it["id"] and x not in same_src][:5]
        og_image = (f"{site_url}/kart/{it['id']}.jpg" if it["id"] in card_ids
                    else f"{site_url}/static/og.jpg")
        html = tpl_article.render(**common, root="../", it=it, related=same_src, latest=latest,
                                  og_image=og_image, nav="",
                                  canonical=f"{site_url}/{it['path']}")
        _write(out / it["path"], html)

    # ---- Mənbə səhifələri
    tpl_src = env.get_template("source.html")
    for s in sources:
        lst = [x for x in items if x["source"] == s["id"]][:80]
        html = tpl_src.render(**common, root="../", source=s, groups=_group_by_day(lst, lent_after),
                              nav=s["id"], canonical=f"{site_url}/menbe/{s['id']}.html")
        _write(out / "menbe" / f"{s['id']}.html", html)

    # ---- Axtarış
    search = [{"t": x["title"], "k": to_ascii(x["title"]), "u": x["path"], "s": x["src_name"],
               "c": x["src_color"], "d": x["when"]} for x in items[:1500]]
    _write(out / "axtaris.json", json.dumps(search, ensure_ascii=False, separators=(",", ":")))
    _write(out / "axtar.html", env.get_template("search.html").render(
        **common, root="./", nav="search", canonical=f"{site_url}/axtar.html"))

    # ---- 404 (GitHub Pages istənilən dərinlikdə göstərir, ona görə mütləq yol)
    _write(out / "404.html", env.get_template("404.html").render(
        **common, root=cfg.base_path, nav="", canonical=""))

    # ---- RSS, sitemap, robots
    if site_url:
        _write(out / "feed.xml", _rss(cfg, items[:50], updated))
        _write(out / "sitemap.xml", _sitemap(site_url, items[:1000], sources))
        _write(out / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n")

    log.info("Sayt quruldu: %s xəbər, %s səhifə, %s şəkil-kart", len(items), pages, len(card_ids))
    return len(items)


def _rss(cfg: Config, items: list[dict], updated: datetime) -> str:
    from email.utils import format_datetime
    url = cfg.site_url
    rows = []
    for it in items:
        rows.append(
            "<item>"
            f"<title>{xml_escape(it['title'])}</title>"
            f"<link>{xml_escape(url + '/' + it['path'])}</link>"
            f"<guid isPermaLink=\"true\">{xml_escape(url + '/' + it['path'])}</guid>"
            f"<pubDate>{format_datetime(it['dt'])}</pubDate>"
            f"<category>{xml_escape(it['src_name'])}</category>"
            f"<description>{xml_escape(it['body'])}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{xml_escape(cfg.site['name'])}</title>"
        f"<link>{xml_escape(url)}/</link>"
        f"<description>{xml_escape(cfg.site['tagline'])}</description>"
        "<language>az</language>"
        f"<lastBuildDate>{format_datetime(updated)}</lastBuildDate>"
        f'<atom:link href="{xml_escape(url)}/feed.xml" rel="self" type="application/rss+xml"/>'
        + "".join(rows) + "</channel></rss>\n"
    )


def _sitemap(url: str, items: list[dict], sources: list[dict]) -> str:
    locs = [f"<url><loc>{xml_escape(url)}/</loc><changefreq>hourly</changefreq></url>"]
    locs += [f"<url><loc>{xml_escape(url)}/menbe/{s['id']}.html</loc></url>" for s in sources]
    locs += [f"<url><loc>{xml_escape(url + '/' + it['path'])}</loc>"
             f"<lastmod>{it['dt'].date().isoformat()}</lastmod></url>" for it in items]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(locs) + "</urlset>\n")
