"""Xəbərlərin saxlanması: data/news.json, data/seen.json, data/state.json."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from .text import normalize_url, now_utc, parse_iso, short_hash, title_key

SEEN_LIMIT = 20000


def _read_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        # Zədələnmiş fayl botu dayandırmasın — ehtiyat nüsxə saxla, sıfırdan başla
        path.rename(path.with_suffix(path.suffix + ".broken"))
        return default


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def link_key(link: str) -> str:
    return short_hash(normalize_url(link), 16)


class Store:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.items: list[dict] = _read_json(self.dir / "news.json", [])
        self.seen: list[str] = _read_json(self.dir / "seen.json", [])
        self.state: dict = _read_json(self.dir / "state.json", {})
        self._seen_set = set(self.seen)
        self._recent_titles = self._build_recent_titles()

    def _build_recent_titles(self) -> set[str]:
        cutoff = now_utc() - timedelta(hours=48)
        out = set()
        for it in self.items:
            try:
                if parse_iso(it["published"]) >= cutoff:
                    out.add(title_key(it["title"]))
            except (KeyError, ValueError):
                continue
        return out

    def is_new(self, entry: dict) -> bool:
        return link_key(entry["link"]) not in self._seen_set

    def is_duplicate_title(self, title: str) -> bool:
        key = title_key(title)
        return bool(key) and key in self._recent_titles

    def mark_seen(self, link: str) -> None:
        k = link_key(link)
        if k not in self._seen_set:
            self._seen_set.add(k)
            self.seen.append(k)

    def add(self, item: dict) -> None:
        self.items.append(item)
        self._recent_titles.add(title_key(item["title"]))

    def sorted_items(self) -> list[dict]:
        return sorted(self.items, key=lambda i: i["published"], reverse=True)

    def save(self, keep_items: int) -> None:
        self.items = self.sorted_items()[:keep_items]
        self.seen = self.seen[-SEEN_LIMIT:]
        _write_json(self.dir / "news.json", self.items)
        _write_json(self.dir / "seen.json", self.seen)
        _write_json(self.dir / "state.json", self.state)
