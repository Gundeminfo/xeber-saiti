"""Telegram kanalına mesaj göndərmək."""

from __future__ import annotations

import html
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)

API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")


def hashtag(text: str) -> str:
    words = re.findall(r"[0-9A-Za-zƏəÖöÜüĞğŞşÇçİıI]+", text or "")
    tag = "".join(w[:1].upper() + w[1:] for w in words)
    return f"#{tag}" if tag and not tag.isdigit() else ""


def format_message(item: dict, source_name: str, page_url: str, use_hashtags: bool,
                   show_category: bool = True) -> str:
    e = lambda s: html.escape(s or "", quote=False)  # noqa: E731
    parts = [f"<b>{e(item['title'])}</b>"]
    body = item.get("summary") or item.get("teaser") or ""
    if body:
        parts.append(e(body))
    meta = f"📰 {e(source_name)}"
    if show_category and item.get("category"):
        meta += f" | {e(item['category'])}"
    parts.append(meta)
    href = html.escape(page_url or item["link"], quote=True)
    parts.append(f'<a href="{href}">Ətraflı oxu</a>')
    if use_hashtags:
        cat = item.get("category", "") if show_category else ""
        tags = " ".join(dict.fromkeys(t for t in (hashtag(cat), hashtag(source_name)) if t))
        if tags:
            parts.append(tags)
    return "\n\n".join(parts)


class TelegramError(Exception):
    pass


def send_message(token: str, chat_id: str, text: str, link_preview: bool) -> int:
    """Mesajı göndərir və message_id qaytarır. Uğursuz olarsa TelegramError atır."""
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": not link_preview},
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=20)
        except requests.RequestException as exc:
            if attempt == 2:
                raise TelegramError(f"şəbəkə xətası: {exc}") from exc
            time.sleep(3)
            continue
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if data.get("ok"):
            return int(data["result"]["message_id"])
        if resp.status_code == 429:
            wait = int(data.get("parameters", {}).get("retry_after", 5))
            log.info("  Telegram limit: %s saniyə gözlənilir", wait)
            time.sleep(min(wait, 60) + 1)
            continue
        desc = data.get("description", resp.text[:200])
        raise TelegramError(f"HTTP {resp.status_code}: {desc}")
    raise TelegramError("3 cəhddən sonra göndərilmədi")
