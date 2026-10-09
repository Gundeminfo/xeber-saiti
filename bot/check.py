"""Açarların düzgün qurulduğunu yoxlayır. Heç bir açarı ekrana çıxarmır.

    python -m bot.check
"""

from __future__ import annotations

import os
import sys

import requests

from .config import load_config
from .social import GRAPH_BASE, THREADS_BASE
from .telegram import API_BASE as TG_BASE

OK, BAD, SKIP = "✅", "❌", "➖"


def line(mark: str, name: str, msg: str) -> None:
    print(f"{mark} {name}: {msg}")


def _json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {}


def check_telegram(cfg) -> bool:
    token, chat = cfg.secret("TELEGRAM_BOT_TOKEN"), cfg.secret("TELEGRAM_CHANNEL")
    if not token:
        line(SKIP, "Telegram", "TELEGRAM_BOT_TOKEN əlavə edilməyib")
        return True
    me = _json(requests.get(f"{TG_BASE}/bot{token}/getMe", timeout=20))
    if not me.get("ok"):
        line(BAD, "Telegram", "bot tokeni yanlışdır — @BotFather-dən yenidən kopyalayın")
        return False
    bot_id, username = me["result"]["id"], me["result"].get("username")
    if not chat:
        line(BAD, "Telegram", f"bot @{username} tapıldı, amma TELEGRAM_CHANNEL əlavə edilməyib")
        return False
    member = _json(requests.get(f"{TG_BASE}/bot{token}/getChatMember",
                                params={"chat_id": chat, "user_id": bot_id}, timeout=20))
    if not member.get("ok"):
        line(BAD, "Telegram", f"kanal tapılmadı: {member.get('description', '')}. "
                              "Kanal adını @ ilə yazın (məs. @menim_kanalim)")
        return False
    status = member["result"].get("status")
    can_post = member["result"].get("can_post_messages", status == "creator")
    if status not in ("administrator", "creator") or not can_post:
        line(BAD, "Telegram", f"@{username} kanalda admin deyil və ya mesaj yaza bilmir")
        return False
    line(OK, "Telegram", f"@{username} kanala yaza bilir")
    admin = cfg.secret("TELEGRAM_ADMIN_CHAT")
    if admin:
        r = _json(requests.get(f"{TG_BASE}/bot{token}/getChat", params={"chat_id": admin}, timeout=20))
        if r.get("ok"):
            line(OK, "Admin bildirişləri", "xəbərdarlıqlar şəxsi çatınıza gələcək")
        else:
            line(BAD, "Admin bildirişləri", "TELEGRAM_ADMIN_CHAT tapılmadı — əvvəlcə bota /start yazın")
            return False
    return True


def check_meta(cfg) -> bool:
    token = cfg.secret("FACEBOOK_PAGE_TOKEN")
    if not token:
        line(SKIP, "Facebook və Instagram", "FACEBOOK_PAGE_TOKEN əlavə edilməyib")
        return True
    base = f"{GRAPH_BASE}/{cfg.facebook['graph_version']}"
    me = _json(requests.get(f"{base}/me", params={
        "access_token": token, "fields": "id,name,instagram_business_account{id,username}"}, timeout=20))
    if "error" in me:
        line(BAD, "Facebook", f"token qəbul olunmadı: {me['error'].get('message', '')}")
        return False
    # Səhifə tokeni olduğunu yoxla (istifadəçi tokeni ilə /me şəxsi profili qaytarır)
    acc = _json(requests.get(f"{base}/me/accounts", params={"access_token": token}, timeout=20))
    if "data" in acc and "error" not in acc:
        line(BAD, "Facebook", "bu istifadəçi tokenidir. README-dəki addımla SƏHİFƏ tokenini götürün")
        return False
    line(OK, "Facebook", f"“{me.get('name')}” səhifəsinə yazmağa hazırdır")
    ok = True
    ig = me.get("instagram_business_account")
    if not cfg.instagram.get("enabled", True):
        line(SKIP, "Instagram", "config.toml-da söndürülüb")
    elif ig and ig.get("id"):
        line(OK, "Instagram", f"@{ig.get('username', ig['id'])} hesabına yazmağa hazırdır")
    else:
        line(BAD, "Instagram", "səhifəyə Instagram biznes/kreator hesabı bağlı deyil və ya icazə verilməyib")
        ok = False
    return ok


def check_threads(cfg) -> bool:
    token = cfg.secret("THREADS_TOKEN")
    if not token:
        line(SKIP, "Threads", "THREADS_TOKEN əlavə edilməyib")
        return True
    app_secret = cfg.secret("THREADS_APP_SECRET")
    if app_secret:
        from datetime import datetime, timezone
        from pathlib import Path
        from .tokens import threads_token
        token, _ = threads_token(token, app_secret, Path("data"), datetime.now(timezone.utc))
    me = _json(requests.get(f"{THREADS_BASE}/v1.0/me", params={
        "access_token": token, "fields": "id,username"}, timeout=20))
    if "error" in me or not me.get("id"):
        line(BAD, "Threads", f"token qəbul olunmadı: {me.get('error', {}).get('message', '')}. "
                             "Token 1 saatlıqdırsa, vaxtı keçmiş ola bilər — yenisini yaradın")
        return False
    note = ("token hər həftə avtomatik uzadılacaq" if app_secret
            else "THREADS_APP_SECRET yoxdur — token 60 gündən sonra əl ilə yenilənməlidir")
    line(OK, "Threads", f"@{me.get('username')} hesabına yazmağa hazırdır ({note})")
    return True


def check_ai(cfg) -> bool:
    key = cfg.secret("ANTHROPIC_API_KEY")
    if not key:
        line(SKIP, "Süni intellekt xülasəsi", "ANTHROPIC_API_KEY yoxdur — mənbənin öz təsviri istifadə olunacaq")
        return True
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    r = requests.get(f"{base}/v1/models", headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                     timeout=20)
    if r.status_code != 200:
        line(BAD, "Süni intellekt xülasəsi", f"açar qəbul olunmadı (HTTP {r.status_code})")
        return False
    line(OK, "Süni intellekt xülasəsi", f"aktivdir, model: {cfg.summary['ai_model']}")
    return True


def check_sources(cfg) -> bool:
    from .sources import fetch_source
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; xeber-bot/1.0)"
    ok = True
    for src in cfg.sources:
        if not src.enabled:
            line(SKIP, src.name, "söndürülüb")
            continue
        try:
            n = len(fetch_source(src, s, 20))
            line(OK if n else BAD, src.name, f"lentdə {n} xəbər" if n else "lent boşdur")
            ok &= bool(n)
        except Exception as exc:  # noqa: BLE001 — hər xətanı istifadəçiyə göstər
            line(BAD, src.name, f"lent oxunmadı: {exc.__class__.__name__}")
            ok = False
    return ok


def main() -> int:
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.toml")
    print(f"Sayt: {cfg.site_url or '(ünvan GitHub tərəfindən veriləcək)'}\n")
    results = []
    for fn in (check_sources, check_telegram, check_meta, check_threads, check_ai):
        try:
            results.append(fn(cfg))
        except requests.RequestException as exc:
            line(BAD, fn.__name__.replace("check_", ""), f"şəbəkə xətası: {exc.__class__.__name__}")
            results.append(False)
    print()
    if all(results):
        print("Hər şey qaydasındadır.")
        return 0
    print("❌ olan sətirlərdəki problemi düzəldin və yoxlamanı yenidən işə salın.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
