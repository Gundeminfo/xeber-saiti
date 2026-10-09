"""Facebook səhifəsi, Instagram və Threads üçün paylaşım (Meta-nın rəsmi API-ləri)."""

from __future__ import annotations

import logging
import os
import time

import requests

log = logging.getLogger(__name__)

GRAPH_BASE = os.environ.get("META_GRAPH_BASE", "https://graph.facebook.com").rstrip("/")
THREADS_BASE = os.environ.get("THREADS_API_BASE", "https://graph.threads.net").rstrip("/")


class SocialError(Exception):
    pass


def _check(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise SocialError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        msg = err.get("error_user_msg") or err.get("message") or resp.text[:200]
        raise SocialError(f"HTTP {resp.status_code}: {msg}")
    return data


def _get(url: str, **params) -> dict:
    try:
        return _check(requests.get(url, params=params, timeout=30))
    except requests.RequestException as exc:
        raise SocialError(f"şəbəkə xətası: {exc.__class__.__name__}") from exc


def _post(url: str, **data) -> dict:
    try:
        return _check(requests.post(url, data=data, timeout=60))
    except requests.RequestException as exc:
        raise SocialError(f"şəbəkə xətası: {exc.__class__.__name__}") from exc


# ---------------------------------------------------------------- Facebook / Instagram
class MetaPage:
    """Bir Facebook səhifə tokeni ilə həm səhifəyə, həm ona bağlı Instagrama yazır."""

    def __init__(self, page_token: str, version: str = "v26.0"):
        self.token = page_token
        self.base = f"{GRAPH_BASE}/{version}"
        self._page: dict | None = None

    def page(self) -> dict:
        if self._page is None:
            self._page = _get(f"{self.base}/me", access_token=self.token,
                              fields="id,name,instagram_business_account{id,username}")
        return self._page

    def instagram_id(self) -> str:
        ig = self.page().get("instagram_business_account") or {}
        if not ig.get("id"):
            raise SocialError("Facebook səhifəsinə Instagram biznes hesabı bağlanmayıb")
        return ig["id"]

    def post_to_page(self, message: str, link: str) -> str:
        page_id = self.page()["id"]
        data = _post(f"{self.base}/{page_id}/feed", message=message, link=link,
                     access_token=self.token)
        return data.get("id", "")

    def post_to_instagram(self, image_url: str, caption: str, alt_text: str = "") -> str:
        ig_id = self.instagram_id()
        params = {"image_url": image_url, "caption": caption, "access_token": self.token}
        if alt_text:
            params["alt_text"] = alt_text[:1000]
        container = _post(f"{self.base}/{ig_id}/media", **params)["id"]
        # Konteyner hazır olana qədər gözlə (adətən bir neçə saniyə)
        for _ in range(12):
            status = _get(f"{self.base}/{container}", fields="status_code",
                          access_token=self.token).get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise SocialError(f"Instagram şəkli qəbul etmədi ({status})")
            time.sleep(5)
        data = _post(f"{self.base}/{ig_id}/media_publish", creation_id=container,
                     access_token=self.token)
        return data.get("id", "")


# ---------------------------------------------------------------- Threads
class Threads:
    def __init__(self, token: str):
        self.token = token
        self.base = f"{THREADS_BASE}/v1.0"
        self._me: dict | None = None

    def me(self) -> dict:
        if self._me is None:
            self._me = _get(f"{self.base}/me", fields="id,username", access_token=self.token)
        return self._me

    def post(self, text: str, link: str) -> str:
        uid = self.me()["id"]
        params = {"media_type": "TEXT", "text": text, "access_token": self.token}
        if link:
            params["link_attachment"] = link
        container = _post(f"{self.base}/{uid}/threads", **params)["id"]
        for _ in range(12):
            status = _get(f"{self.base}/{container}", fields="status",
                          access_token=self.token).get("status")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise SocialError(f"Threads postu qəbul etmədi ({status})")
            time.sleep(5)
        data = _post(f"{self.base}/{uid}/threads_publish", creation_id=container,
                     access_token=self.token)
        return data.get("id", "")

    def refresh_token(self) -> dict:
        """Uzunmüddətli tokenin 60 günlük müddətini yeniləyir."""
        return _get(f"{THREADS_BASE}/refresh_access_token", grant_type="th_refresh_token",
                    access_token=self.token)


def wait_until_public(url: str, timeout: int = 180) -> bool:
    """Yeni yerləşdirilmiş faylın (şəkil) internetdə açıldığını yoxlayır."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.head(url, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(10)
    return False
