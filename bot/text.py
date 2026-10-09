"""Mətn köməkçiləri: təmizləmə, slug, tarix formatı."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

AZ_TRANSLIT = str.maketrans({
    "ə": "e", "Ə": "e", "ı": "i", "I": "i", "İ": "i", "ö": "o", "Ö": "o",
    "ü": "u", "Ü": "u", "ğ": "g", "Ğ": "g", "ş": "s", "Ş": "s", "ç": "c", "Ç": "c",
})

AZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
             "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
AZ_WEEKDAYS = ["bazar ertəsi", "çərşənbə axşamı", "çərşənbə", "cümə axşamı",
               "cümə", "şənbə", "bazar"]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Başlıqların sonundakı "- YENİLƏNİB", "(VİDEO)" kimi əlavələr
_TITLE_NOISE = re.compile(
    r"\b(yenilenib\d*|video|foto|fotolar|siyahi|serh|ekskluziv|musahibe|reportaj)\b"
)


def to_ascii(text: str) -> str:
    t = text.translate(AZ_TRANSLIT).lower()
    t = unicodedata.normalize("NFKD", t)
    return t.encode("ascii", "ignore").decode()


def az_lower(text: str) -> str:
    """Azərbaycan qaydası ilə kiçik hərf: İ→i, I→ı (ə, ö, ü, ğ, ş, ç saxlanılır)."""
    return (text or "").replace("İ", "i").replace("I", "ı").lower()


def slugify(text: str, max_len: int = 70) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", to_ascii(text)).strip("-")
    if len(t) > max_len:
        t = t[:max_len].rsplit("-", 1)[0]
    return t or "xeber"


def title_key(title: str) -> str:
    """Eyni xəbərin müxtəlif mənbələrdəki başlığını tutmaq üçün sadələşdirilmiş açar."""
    t = _TITLE_NOISE.sub(" ", to_ascii(title))
    return re.sub(r"[^a-z0-9]+", "", t)


def short_hash(text: str, n: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def normalize_url(url: str) -> str:
    """utm_* parametrlərini və #fraqmenti atır ki, eyni link iki dəfə sayılmasın."""
    url = url.strip()
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(query), ""))


def clean_text(raw: str | None) -> str:
    """HTML teqlərini, CDATA qalıqlarını və artıq boşluqları təmizləyir."""
    if not raw:
        return ""
    t = raw.replace("<![CDATA[", " ").replace("]]>", " ")
    t = html.unescape(t)
    t = t.replace("<![CDATA[", " ").replace("]]>", " ")  # ikiqat kodlanmış hallar üçün
    t = _TAG_RE.sub(" ", t)
    t = html.unescape(t)
    return _WS_RE.sub(" ", t).strip()


_SENT_END = re.compile(r"(?<=[.!?…])[\"”»']?\s+")


def make_teaser(text: str, max_chars: int = 260) -> str:
    """Mətnin əvvəlindən tam cümlələrlə qısa təsvir düzəldir.

    Mənbə təsviri yarımçıq kəsibsə (məs. "...xəb"), yarımçıq hissə atılır.
    """
    text = clean_text(text)
    if not text:
        return ""
    sentences = [s.strip() for s in _SENT_END.split(text) if s.strip()]
    out = ""
    for s in sentences:
        complete = s.rstrip("\"”»'").endswith((".", "!", "?", "…"))
        if not complete:
            break
        candidate = f"{out} {s}".strip()
        if len(candidate) > max_chars:
            break
        out = candidate
    if out:
        return out
    # İlk cümlə çox uzundursa və ya heç bir cümlə tam deyilsə — söz sərhədində kəs
    first = sentences[0] if sentences else text
    if len(first) <= max_chars and first.rstrip("\"”»'").endswith((".", "!", "?", "…")):
        return first
    if len(first) < 40:
        return ""
    cut = first[:max_chars].rsplit(" ", 1)[0].rstrip(",;:—-– ")
    return cut + "…"


def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def fmt_time(dt: datetime, zone: ZoneInfo) -> str:
    return dt.astimezone(zone).strftime("%H:%M")


def fmt_day(dt: datetime, zone: ZoneInfo, with_weekday: bool = True) -> str:
    d = dt.astimezone(zone)
    s = f"{d.day} {AZ_MONTHS[d.month - 1]} {d.year}"
    return f"{s}, {AZ_WEEKDAYS[d.weekday()]}" if with_weekday else s


def fmt_datetime(dt: datetime, zone: ZoneInfo) -> str:
    d = dt.astimezone(zone)
    return f"{d.day} {AZ_MONTHS[d.month - 1]} {d.year}, {d.strftime('%H:%M')}"
