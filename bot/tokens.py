"""Threads tokeninin avtomatik uzadılması.

Threads tokenləri 60 gündən sonra bitir. Bot tokeni hər həftə yeniləyir və yeni
tokeni data/ qovluğunda ŞİFRƏLİ saxlayır (açar: THREADS_APP_SECRET). Beləliklə
GitHub Secrets-ə yalnız bir dəfə token yazmaq kifayətdir.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .social import THREADS_BASE, SocialError, _get

log = logging.getLogger(__name__)

FILE = "threads_token.enc"


def _fernet(app_secret: str) -> Fernet:
    key = hashlib.sha256(b"xeber-bot/threads/" + app_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _load(path: Path, app_secret: str) -> dict | None:
    try:
        return json.loads(_fernet(app_secret).decrypt(path.read_bytes()))
    except (FileNotFoundError, InvalidToken, ValueError):
        return None


def _save(path: Path, app_secret: str, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fernet(app_secret).encrypt(json.dumps(data).encode()))


def threads_token(secret_token: str, app_secret: str, data_dir: Path, now: datetime) -> tuple[str, str]:
    """İstifadə üçün etibarlı Threads tokeni və (varsa) xəbərdarlıq mətni qaytarır."""
    if not app_secret:
        return secret_token, ""

    path = Path(data_dir) / FILE
    fp = _fingerprint(secret_token)
    saved = _load(path, app_secret)

    if not saved or saved.get("from") != fp:
        # Yeni (və ya dəyişdirilmiş) token: qısamüddətlidirsə 60 günlüyə çevir
        token, expires_in = secret_token, 0
        try:
            r = _get(f"{THREADS_BASE}/access_token", grant_type="th_exchange_token",
                     client_secret=app_secret, access_token=secret_token)
            token, expires_in = r["access_token"], int(r.get("expires_in", 0))
            log.info("Threads tokeni 60 günlük tokenə çevrildi")
        except (SocialError, KeyError):
            log.info("Threads tokeni artıq uzunmüddətlidir (və ya çevrilmədi), olduğu kimi saxlanılır")
        saved = {"from": fp, "token": token, "refreshed": now.isoformat(),
                 "expires": (now + timedelta(seconds=expires_in or 60 * 86400)).isoformat()}
        _save(path, app_secret, saved)
        return token, ""

    refreshed = datetime.fromisoformat(saved["refreshed"])
    if now - refreshed >= timedelta(days=7):
        try:
            r = _get(f"{THREADS_BASE}/refresh_access_token", grant_type="th_refresh_token",
                     access_token=saved["token"])
            saved.update(token=r["access_token"], refreshed=now.isoformat(),
                         expires=(now + timedelta(seconds=int(r.get("expires_in", 60 * 86400)))).isoformat())
            _save(path, app_secret, saved)
            log.info("Threads tokeni yeniləndi")
        except (SocialError, KeyError) as exc:
            expires = datetime.fromisoformat(saved["expires"])
            days = (expires - now).days
            return saved["token"], (f"Threads tokeni yenilənmədi ({exc}). {days} gün sonra bitəcək — "
                                    "README-dəki addımla yeni THREADS_TOKEN əlavə edin.")
    return saved["token"], ""

