"""Başlığa görə mövzu fotosu seçmək (sekiller.toml)."""

from __future__ import annotations

import logging
import re
import tomllib
from pathlib import Path

from .text import az_lower

log = logging.getLogger(__name__)


class PhotoPicker:
    def __init__(self, path: Path):
        self.topics: list[tuple[str, re.Pattern, list[str]]] = []
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            return
        except tomllib.TOMLDecodeError as exc:
            log.warning("sekiller.toml oxunmadı: %s", exc)
            return
        for t in data.get("topic", []):
            words = [az_lower(str(w)).strip() for w in t.get("words", []) if str(w).strip()]
            if not words:
                continue
            rx = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")")
            photos = [u.strip() for u in t.get("photos", []) if isinstance(u, str) and u.strip()]
            self.topics.append((t.get("name", ""), rx, photos))

    def pick(self, title: str, key: str) -> tuple[str, str]:
        """(foto_url, mövzu_adı) qaytarır. Uyğun mövzu yoxdursa və ya mövzu şəkilsizdirsə ("", ad)."""
        text = az_lower(title or "")
        for name, rx, photos in self.topics:
            if rx.search(text):
                if not photos:
                    return "", name
                return photos[int(key[:8], 16) % len(photos)], name
        return "", ""
