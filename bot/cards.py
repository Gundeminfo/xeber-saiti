"""Instagram və link önizləmələri üçün xəbər şəkil-kartı (1080×1350 JPEG)."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from .text import fmt_day, fmt_time

FONT_PATH = Path(__file__).parent / "fonts" / "Lora-Variable.ttf"

W, H = 1080, 1350
MARGIN = 88
INK = "#0E2A47"
WHITE = "#FFFFFF"
TIME = "#7FD0EE"
MUTED = "#A9BCCD"
RULE = "#2B4A6B"


@lru_cache(maxsize=64)
def font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_PATH), size)
    try:
        f.set_variation_by_axes([weight])
    except (OSError, AttributeError):
        pass
    return f


def _wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if f.getlength(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fit_headline(text: str, width: int, height: int) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(116, 46, -4):
        f = font(size, 700)
        lines = _wrap(text, f, width)
        line_h = int(size * 1.2)
        if len(lines) * line_h <= height:
            return f, lines, line_h
    f = font(48, 700)
    line_h = int(48 * 1.2)
    lines = _wrap(text, f, width)[: height // line_h]
    if lines:
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return f, lines, line_h


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def render_card(item: dict, source_name: str, source_color: str, site_name: str,
                site_url: str, zone: ZoneInfo, out_path: Path) -> Path:
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    published = datetime.fromisoformat(item["published"])

    # Saat — kartın əsas vurğusu, saytdakı xronologiyanın davamı
    t_font = font(112, 700)
    time_txt = fmt_time(published, zone)
    d.text((MARGIN, 92), time_txt, font=t_font, fill=TIME)
    tx = MARGIN + int(t_font.getlength(time_txt)) + 28
    d.text((tx, 160), fmt_day(published, zone, with_weekday=False), font=font(34, 500), fill=MUTED)

    # Mənbə: rəngli zolaq + ad + bölmə
    y = 272
    d.rectangle((MARGIN, y + 6, MARGIN + 12, y + 50), fill=_hex(source_color))
    s_font = font(40, 600)
    d.text((MARGIN + 32, y), source_name, font=s_font, fill=WHITE)
    if item.get("category"):
        cx = MARGIN + 32 + int(s_font.getlength(source_name)) + 24
        d.text((cx, y + 4), item["category"], font=font(36, 400), fill=MUTED)

    # Başlıq və (yer qalırsa) qısa təsvir
    top, bottom = 380, 1150
    body = item.get("summary") or item.get("teaser") or ""
    head_room = (bottom - top) * 0.62 if body else bottom - top
    h_font, lines, line_h = _fit_headline(item["title"], W - 2 * MARGIN, int(head_room))
    y = top
    for ln in lines:
        d.text((MARGIN, y), ln, font=h_font, fill=WHITE)
        y += line_h
    if body:
        b_font, b_line = font(38, 400), 56
        y += 34
        max_lines = (bottom - y) // b_line
        b_lines = _wrap(body, b_font, W - 2 * MARGIN)
        if len(b_lines) > max_lines:
            b_lines = b_lines[:max_lines]
            if b_lines:
                b_lines[-1] = b_lines[-1].rstrip(".,;:") + "…"
        for ln in b_lines:
            d.text((MARGIN, y), ln, font=b_font, fill=MUTED)
            y += b_line

    # Alt hissə: saytın adı və ünvanı
    d.line((MARGIN, 1196, W - MARGIN, 1196), fill=RULE, width=2)
    d.text((MARGIN, 1226), site_name, font=font(46, 700), fill=WHITE)
    host = urlsplit(site_url).netloc + urlsplit(site_url).path.rstrip("/") if site_url else ""
    if host:
        hf = font(30, 400)
        d.text((W - MARGIN - hf.getlength(host), 1240), host, font=hf, fill=MUTED)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=88, optimize=True, progressive=False)
    return out_path


def render_site_card(site_name: str, tagline: str, out_path: Path) -> Path:
    """Saytın ümumi önizləmə şəkli (1200×630)."""
    img = Image.new("RGB", (1200, 630), INK)
    d = ImageDraw.Draw(img)
    d.text((80, 200), site_name, font=font(120, 700), fill=WHITE)
    d.text((84, 360), tagline, font=font(44, 400), fill=MUTED)
    d.rectangle((80, 470, 200, 478), fill=TIME)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=88, optimize=True)
    return out_path


# ─── Bölmə piktoqramları və xəbər kartları ─────────────────────────────

STORY_W, STORY_H = 1200, 630
DEEP = (11, 27, 43)


def _mix(a: tuple, b: tuple, k: float) -> tuple[int, int, int]:
    """a rəngindən b rənginə k qədər keçid."""
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))  # type: ignore[return-value]


def _draw_icon(d: ImageDraw.ImageDraw, kind: str, s: float, ink, clear) -> None:
    """100×100 vahid ölçüdə piktoqram çəkir (s — miqyas)."""
    def P(*xy):
        return [v * s for v in xy]

    if kind == "siyaset":          # sütunlu bina
        d.polygon(P(8, 34, 50, 8, 92, 34), fill=ink)
        d.rectangle(P(12, 37, 88, 43), fill=ink)
        for x in (17, 35, 53, 71):
            d.rectangle(P(x, 47, x + 12, 79), fill=ink)
        d.rectangle(P(10, 82, 90, 88), fill=ink)
        d.rectangle(P(4, 91, 96, 97), fill=ink)
    elif kind == "iqtisadiyyat":   # artan sütunlar
        for x0, y0 in ((10, 62), (32, 46), (54, 54), (76, 24)):
            d.rectangle(P(x0, y0, x0 + 15, 86), fill=ink)
        d.rectangle(P(4, 90, 96, 96), fill=ink)
    elif kind == "cemiyyet":       # insanlar
        for cx in (20, 80):
            d.ellipse(P(cx - 10, 26, cx + 10, 46), fill=ink)
            d.pieslice(P(cx - 18, 52, cx + 18, 96), 180, 360, fill=ink)
        d.ellipse(P(34, 6, 66, 38), fill=clear)
        d.pieslice(P(20, 38, 80, 110), 180, 360, fill=clear)
        d.ellipse(P(38, 10, 62, 34), fill=ink)
        d.pieslice(P(24, 42, 76, 106), 180, 360, fill=ink)
    elif kind == "dunya":          # qlobus
        w = max(2, int(5 * s))
        d.ellipse(P(8, 8, 92, 92), outline=ink, width=w)
        d.ellipse(P(31, 8, 69, 92), outline=ink, width=w)
        d.line(P(50, 8, 50, 92), fill=ink, width=w)
        d.line(P(8, 50, 92, 50), fill=ink, width=w)
        for y, half in ((29, 36), (71, 36)):
            d.line(P(50 - half, y, 50 + half, y), fill=ink, width=w)
    elif kind == "idman":          # kubok
        w = max(2, int(6 * s))
        d.arc(P(10, 14, 38, 46), 90, 270, fill=ink, width=w)
        d.arc(P(62, 14, 90, 46), 270, 90, fill=ink, width=w)
        d.rectangle(P(24, 8, 76, 32), fill=ink)
        d.pieslice(P(24, 2, 76, 62), 0, 180, fill=ink)
        d.rectangle(P(45, 60, 55, 76), fill=ink)
        d.rectangle(P(34, 76, 66, 83), fill=ink)
        d.rectangle(P(26, 86, 74, 94), fill=ink)
    else:                          # hadisə: xəbərdarlıq üçbucağı
        d.polygon(P(50, 6, 96, 90, 4, 90), fill=ink)
        d.rounded_rectangle(P(45, 34, 55, 66), radius=5 * s, fill=clear)
        d.ellipse(P(44.5, 71, 55.5, 82), fill=clear)


@lru_cache(maxsize=64)
def _icon_layer(kind: str, size: int, alpha: int) -> Image.Image:
    """Hamar kənarlı piktoqram (3 dəfə böyük çəkilib kiçildilir)."""
    big = size * 3
    layer = Image.new("RGBA", (big, big), (255, 255, 255, 0))
    _draw_icon(ImageDraw.Draw(layer), kind, big / 100, (255, 255, 255, alpha), (255, 255, 255, 0))
    return layer.resize((size, size), Image.LANCZOS)


def _paste_icon(img: Image.Image, kind: str, size: int, x: int, y: int, alpha: int) -> Image.Image:
    base = img.convert("RGBA")
    base.alpha_composite(_icon_layer(kind, size, alpha), (x, y))
    return base.convert("RGB")


def render_cover(label: str, color: str, site_name: str, out_path: Path,
                 small: bool = False, kind: str = "") -> Path:
    """Bölmə örtüyü. small=True — siyahıdakı kiçik şəkil (yalnız piktoqram)."""
    base = _hex(color)
    if small:
        w, h = 480, 300
        img = Image.new("RGB", (w, h), _mix(base, DEEP, 0.18))
        size = 150
        img = _paste_icon(img, kind, size, (w - size) // 2, (h - size) // 2, 235)
    else:
        w, h = STORY_W, STORY_H
        img = Image.new("RGB", (w, h), _mix(base, DEEP, 0.55))
        img = _paste_icon(img, kind, 380, w - 380 - 80, (h - 380) // 2, 60)
        d = ImageDraw.Draw(img)
        d.text((80, 70), site_name, font=font(44, 700), fill=WHITE)
        d.text((76, h - 80 - 120), label, font=font(116, 700), fill=WHITE)
        d.rectangle((0, h - 12, w, h), fill=base)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=85, optimize=True)
    return out_path


def _fit(text: str, width: int, height: int, big: int, small: int, weight: int = 700):
    for size in range(big, small - 1, -2):
        f = font(size, weight)
        lines = _wrap(text, f, width)
        line_h = int(size * 1.22)
        if len(lines) * line_h <= height:
            return f, lines, line_h
    f = font(small, weight)
    line_h = int(small * 1.22)
    lines = _wrap(text, f, width)[: max(1, height // line_h)]
    if lines:
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return f, lines, line_h


def render_story(title: str, label: str, color: str, kind: str, when: str,
                 site_name: str, out_path: Path) -> Path:
    """Hər xəbərin öz kartı (1200×630): bölmə, başlıq, tarix.

    Saytda xəbərin şəkli və Telegram/Facebook/WhatsApp önizləməsi kimi işlənir.
    Şəkil başlığın özündən yarandığı üçün həmişə xəbərə uyğundur.
    """
    w, h = STORY_W, STORY_H
    base = _hex(color)
    img = Image.new("RGB", (w, h), _mix(base, DEEP, 0.62))
    img = _paste_icon(img, kind, 360, w - 360 - 40, h - 360 - 36, 20)
    d = ImageDraw.Draw(img)
    pad = 72

    # yuxarı: bölmə nişanı və saytın adı
    lf = font(28, 700)
    lw = int(lf.getlength(label))
    d.rounded_rectangle((pad, 58, pad + lw + 40, 58 + 50), radius=25, fill=base)
    d.text((pad + 20, 58 + 9), label, font=lf, fill=WHITE)
    sf = font(36, 700)
    d.text((w - pad - sf.getlength(site_name), 62), site_name, font=sf, fill=WHITE)

    # başlıq
    top, bottom = 150, 528
    hf, lines, line_h = _fit(title, w - 2 * pad, bottom - top, 70, 38)
    y = top + max(0, (bottom - top - len(lines) * line_h) // 2)
    for ln in lines:
        d.text((pad, y), ln, font=hf, fill=WHITE)
        y += line_h

    # aşağı: tarix və rəngli xətt
    d.text((pad, h - 74), when, font=font(28, 400), fill=MUTED)
    d.rectangle((0, h - 12, w, h), fill=base)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=82, optimize=True)
    return out_path
