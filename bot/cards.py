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
