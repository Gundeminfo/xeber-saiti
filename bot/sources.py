"""RSS və Atom lentlərini oxuyur (yalnız Python standart kitabxanası ilə)."""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from .config import Source
from .text import clean_text

log = logging.getLogger(__name__)

_BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BARE_AMP = re.compile(r"&(?!(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)")
_NAMED_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>", re.S)
_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _child_text(el: ET.Element, *names: str) -> str:
    for name in names:
        c = _child(el, name)
        if c is not None:
            txt = "".join(c.itertext()).strip()
            if txt:
                return txt
    return ""


def _fix_entity(m: re.Match) -> str:
    name = m.group(1)
    if name in _XML_ENTITIES:
        return m.group(0)
    ch = html.unescape(m.group(0))
    if ch == m.group(0):
        return "&amp;" + name + ";"
    return html.escape(ch, quote=False)


def _parse_xml(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data.lstrip())
    except ET.ParseError:
        pass
    # Səliqəsiz lentlər üçün ikinci cəhd
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    text = text.lstrip("﻿")
    text = _XML_DECL.sub("", text, count=1)
    text = _BAD_CHARS.sub("", text)
    text = _NAMED_ENTITY.sub(_fix_entity, text)
    text = _BARE_AMP.sub("&amp;", text)
    return ET.fromstring(text.strip())


def _parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _entry_link(el: ET.Element, atom: bool) -> str:
    if atom:
        best = ""
        for c in el:
            if _local(c.tag) == "link":
                rel = c.get("rel", "alternate")
                href = c.get("href", "")
                if rel == "alternate" and href:
                    return href.strip()
                best = best or href
        return best.strip()
    link = _child_text(el, "link")
    if not link:
        guid = _child(el, "guid")
        if guid is not None and (guid.get("isPermaLink", "true").lower() == "true"):
            link = (guid.text or "").strip()
    return link


def parse_feed(data: bytes) -> list[dict]:
    root = _parse_xml(data)
    entries: list[dict] = []
    for el in root.iter():
        name = _local(el.tag)
        if name not in ("item", "entry"):
            continue
        atom = name == "entry"
        title = clean_text(_child_text(el, "title"))
        link = _entry_link(el, atom)
        if not title or not link.startswith(("http://", "https://")):
            continue
        cat_el = _child(el, "category")
        category = ""
        if cat_el is not None:
            category = clean_text(cat_el.get("term") or "".join(cat_el.itertext()))
        entries.append({
            "title": title,
            "link": link,
            "published": _parse_date(_child_text(el, "pubDate", "published", "updated", "date")),
            "category": category,
            "description": _child_text(el, "description", "summary"),
        })
    return entries


def fetch_source(src: Source, session: requests.Session, timeout: float) -> list[dict]:
    resp = session.get(src.url, timeout=timeout)
    resp.raise_for_status()
    entries = parse_feed(resp.content)
    for e in entries:
        e["source"] = src.id
    return entries
