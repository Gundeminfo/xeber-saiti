"""Qısa təsvir: mənbənin öz təsviri və ya (açar varsa) süni intellekt xülasəsi.

Botun saytda tam məqalə mətnini saxlamır və dərc etmir. Məqalə səhifəsi yalnız
qısa təsviri (og:description) götürmək və xülasə yazmaq üçün oxunur.
"""

from __future__ import annotations

import logging
import os
import re

import requests
from bs4 import BeautifulSoup

from .text import clean_text, make_teaser

log = logging.getLogger(__name__)

ANTHROPIC_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")

AI_SYSTEM = (
    "Sən Azərbaycan dilində xəbər xülasəsi yazan redaktorsan. "
    "Verilən məqalə mətnini 2-3 cümlə ilə (ən çox 55 söz) öz sözlərinlə xülasə et. "
    "Yalnız mətndəki faktlara əsaslan; heç nə əlavə etmə, rəy bildirmə, emoji yazma. "
    "Mətndən cümlələri hərfi köçürmə. Mənbənin adını və 'xəbər verir' ifadəsini yazma. "
    "Yalnız xülasənin özünü yaz, başlıq və ya giriş sözü olmadan. "
    "Mətn xülasə üçün kifayət deyilsə, yalnız YOXDUR yaz."
)

# Mənbə saytların mətnə qatdığı tipik ifadələr: “Qafqazinfo” xəbər verir ki, / "Report"un məlumatına görə,
_BOILERPLATE = re.compile(
    r"[\"“«]?[A-ZƏÖÜĞŞÇİ][\w.]+[\"”»]?(?:[’']?[a-zəöüğşçı]{1,3})?\s+"
    r"(?:xəbər verir ki|xəbər verir|məlumatına görə)\s*,?\s*"
)


def fetch_article(url: str, session: requests.Session, timeout: float) -> dict:
    """Məqalə səhifəsindən meta təsviri və əsas mətni (yalnız xülasə üçün) çıxarır."""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.info("  səhifə açılmadı: %s (%s)", url, exc.__class__.__name__)
        return {"description": "", "text": ""}

    soup = BeautifulSoup(resp.content, "html.parser")
    desc = ""
    for attrs in ({"property": "og:description"}, {"name": "description"},
                  {"name": "twitter:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            desc = clean_text(tag["content"])
            break

    for t in soup(["script", "style", "noscript", "header", "footer", "nav",
                   "aside", "form", "iframe", "figure"]):
        t.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paras = []
    for p in container.find_all("p"):
        txt = clean_text(p.get_text(" "))
        if len(txt) >= 40:
            paras.append(txt)
    text = "\n".join(paras)[:6000]
    return {"description": desc, "text": text}


def strip_boilerplate(text: str) -> str:
    def cap(m: re.Match) -> str:
        c = m.group(2)
        return m.group(1) + {"i": "İ", "ı": "I"}.get(c, c.upper())

    out = _BOILERPLATE.sub("", text)
    # silinmədən sonra cümlə kiçik hərflə başlayırsa, böyük hərfə çevir
    out = re.sub(r"(^|[.!?]\s+)([a-zəöüğşçı])", cap, out.strip())
    return out


def source_teaser(entry_description: str, page_description: str, title: str) -> str:
    """RSS təsviri, olmadıqda səhifənin meta təsviri əsasında qısa mətn."""
    for raw in (entry_description, page_description):
        teaser = make_teaser(strip_boilerplate(clean_text(raw)))
        if teaser and teaser.lower().strip(" .") != title.lower().strip(" ."):
            return teaser
    return ""


def ai_summary(title: str, text: str, api_key: str, model: str, timeout: float = 40) -> str:
    if len(text) < 200:
        return ""
    try:
        resp = requests.post(
            f"{ANTHROPIC_URL}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 300,
                "system": AI_SYSTEM,
                "messages": [{
                    "role": "user",
                    "content": f"Başlıq: {title}\n\nMəqalə mətni:\n{text}",
                }],
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            log.warning("  AI xülasə alınmadı (HTTP %s): %s", resp.status_code, resp.text[:200])
            return ""
        data = resp.json()
        out = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    except (requests.RequestException, ValueError) as exc:
        log.warning("  AI xülasə xətası: %s", exc)
        return ""
    out = clean_text(out)
    if not out or "YOXDUR" in out.upper()[:12]:
        return ""
    return out[:600]
