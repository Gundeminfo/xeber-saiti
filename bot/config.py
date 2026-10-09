"""config.toml faylını oxuyur və çatışmayan dəyərlərə defolt verir."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

NETWORKS = ("telegram", "facebook", "instagram", "threads")

DEFAULTS = {
    "site": {
        "name": "Gündəm",
        "tagline": "Azərbaycan xəbərləri bir yerdə",
        "url": "",
        "timezone": "Asia/Baku",
        "per_page": 40,
        "max_pages": 15,
        "keep_items": 1500,
        "show_sources": True,
    },
    "images": {
        "mode": "topic",
    },
    "publish": {
        "max_age_hours": 3,
        "include_keywords": [],
        "exclude_keywords": [],
        "hashtags": True,
    },
    "telegram": {"enabled": True, "url": "", "max_per_run": 4,
                 "min_interval_minutes": 0, "link_preview": False},
    "facebook": {"enabled": True, "url": "", "max_per_run": 1,
                 "min_interval_minutes": 60, "graph_version": "v26.0"},
    "instagram": {"enabled": True, "url": "", "max_per_run": 1,
                  "min_interval_minutes": 120},
    "threads": {"enabled": True, "url": "", "max_per_run": 1,
                "min_interval_minutes": 60},
    "summary": {
        "mode": "auto",
        "ai_model": "claude-haiku-5-5",
        "ai_only_for_social": True,
        "fetch_article_page": True,
    },
    "fetch": {
        "max_new_per_source": 15,
        "timeout_seconds": 15,
        "delay_seconds": 0.5,
    },
    "ads": {
        "enabled": True,
        "label": "Reklam",
        "placeholder": True,
        "placeholder_text": "Reklamınız burada ola bilər",
        "contact_url": "",
        "head_html": "",
        "ads_txt": "",
        "lent_after": 6,
    },
}

# Reklam yerləri: ad → defolt ölçü (en×hündürlük, piksel)
AD_SLOTS = {
    "top": (728, 90),
    "left": (160, 600),
    "right": (300, 600),
    "lent": (300, 250),
}

NETWORK_LABELS = {
    "telegram": "Telegram",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "threads": "Threads",
}


@dataclass
class Source:
    id: str
    name: str
    url: str
    color: str = "#2b6cb0"
    enabled: bool = True
    social: bool = True


@dataclass
class Config:
    sections: dict
    sources: list[Source] = field(default_factory=list)
    root_dir: Path = Path(".")

    def __getattr__(self, name):
        sections = self.__dict__.get("sections", {})
        if name in sections:
            return sections[name]
        raise AttributeError(name)

    @property
    def site_url(self) -> str:
        # config.toml-da yazılmayıbsa, GitHub Actions avtomatik ötürür
        url = self.site.get("url") or os.environ.get("SITE_URL", "")
        return url.strip().rstrip("/")

    @property
    def base_path(self) -> str:
        """Saytın domen daxilindəki yolu: https://x.github.io/repo → /repo/"""
        if not self.site_url:
            return "/"
        path = urlsplit(self.site_url).path.strip("/")
        return f"/{path}/" if path else "/"

    def source(self, sid: str) -> Source | None:
        return next((s for s in self.sources if s.id == sid), None)

    @property
    def show_sources(self) -> bool:
        return bool(self.site.get("show_sources", True))

    def source_names(self) -> list[str]:
        """Mətnlərdən təmizlənəcək mənbə adları (mənbə adları gizlədiləndə)."""
        out = set()
        for s in self.sources:
            out.update({s.name, s.id})
            out.add(s.name.replace("Ə", "E").replace("ə", "e"))
        out.update({"AZƏRTAC", "Azərtac", "AZERTAC", "Azertag", "AZƏRTAG", "Azərtag"})
        return sorted(out)

    # ---- Gizli açarlar: config-də yox, GitHub Secrets-də saxlanılır ----
    @staticmethod
    def secret(name: str) -> str:
        return os.environ.get(name, "").strip()

    def network_ready(self, net: str) -> tuple[bool, str]:
        """Şəbəkənin işə hazır olub-olmadığını və səbəbini qaytarır."""
        if not self.sections[net].get("enabled", True):
            return False, "config.toml-da söndürülüb"
        if net == "telegram":
            if not self.secret("TELEGRAM_BOT_TOKEN"):
                return False, "TELEGRAM_BOT_TOKEN açarı yoxdur"
            if not self.secret("TELEGRAM_CHANNEL"):
                return False, "TELEGRAM_CHANNEL açarı yoxdur"
            return True, ""
        if net in ("facebook", "instagram"):
            if not self.secret("FACEBOOK_PAGE_TOKEN"):
                return False, "FACEBOOK_PAGE_TOKEN açarı yoxdur"
            if net == "instagram" and not self.site_url:
                return False, "saytın ünvanı bilinmir (şəkil üçün lazımdır)"
            return True, ""
        if net == "threads":
            if not self.secret("THREADS_TOKEN"):
                return False, "THREADS_TOKEN açarı yoxdur"
            return True, ""
        return False, "naməlum şəbəkə"

    def active_networks(self) -> list[str]:
        return [n for n in NETWORKS if self.network_ready(n)[0]]

    @property
    def ai_enabled(self) -> bool:
        mode = str(self.summary.get("mode", "auto")).lower()
        if mode in ("off", "source"):
            return False
        return bool(self.secret("ANTHROPIC_API_KEY"))


def _merge(defaults: dict, given: dict | None) -> dict:
    out = dict(defaults)
    out.update(given or {})
    return out


def load_config(path: str | Path) -> Config:
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    sources: list[Source] = []
    seen_ids: set[str] = set()
    for s in raw.get("sources", []):
        sid = re.sub(r"[^a-z0-9_-]", "", str(s.get("id", "")).lower())
        if not sid or not s.get("url"):
            raise ValueError(f"config.toml: hər mənbədə 'id' və 'url' olmalıdır: {s}")
        if sid in seen_ids:
            raise ValueError(f"config.toml: '{sid}' id-si iki dəfə yazılıb")
        seen_ids.add(sid)
        sources.append(Source(
            id=sid,
            name=s.get("name", sid.upper()),
            url=s["url"],
            color=s.get("color", "#2b6cb0"),
            enabled=bool(s.get("enabled", True)),
            social=bool(s.get("social", True)),
        ))

    sections = {name: _merge(defaults, raw.get(name)) for name, defaults in DEFAULTS.items()}
    raw_ads = raw.get("ads") or {}
    for slot, (w, h) in AD_SLOTS.items():
        given = raw_ads.get(slot) or {}
        sections["ads"][slot] = {
            "enabled": bool(given.get("enabled", True)),
            "width": int(given.get("width", w)),
            "height": int(given.get("height", h)),
            "banners": [b for b in given.get("banners", []) if isinstance(b, dict) and b.get("image")],
            "html": str(given.get("html", "")).strip(),
        }
    return Config(sections=sections, sources=sources, root_dir=path.parent.resolve())
