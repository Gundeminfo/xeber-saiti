"""Xəbərləri bölmələrə ayırmaq: Siyasət, İqtisadiyyat, Cəmiyyət, Dünya, İdman, Hadisə.

Əvvəlcə mənbənin öz bölməsinə (RSS-dəki category) baxılır, yoxdursa başlıqdakı açar sözlərə.
"""

from __future__ import annotations

import re

from .text import az_lower, to_ascii

SECTIONS = [
    {"id": "siyaset", "name": "Siyasət", "color": "#1f5fbf"},
    {"id": "iqtisadiyyat", "name": "İqtisadiyyat", "color": "#0b8457"},
    {"id": "cemiyyet", "name": "Cəmiyyət", "color": "#c77700"},
    {"id": "dunya", "name": "Dünya", "color": "#7a3db8"},
    {"id": "idman", "name": "İdman", "color": "#0e7c86"},
    {"id": "hadise", "name": "Hadisə", "color": "#c8102e"},
]
BY_ID = {s["id"]: s for s in SECTIONS}
DEFAULT = "cemiyyet"

# Mənbələrin bölmə adları (latın hərfləri ilə, kiçik) → bizim bölmə
CATEGORY_MAP = [
    ("hadise", "hadise"), ("kriminal", "hadise"),
    ("futbol", "idman"), ("idman", "idman"), ("ferdi", "idman"),
    ("siyas", "siyaset"), ("resmi", "siyaset"), ("parlament", "siyaset"), ("analitika", "siyaset"),
    ("maliyy", "iqtisadiyyat"), ("iqtisad", "iqtisadiyyat"), ("birja", "iqtisadiyyat"),
    ("energet", "iqtisadiyyat"), ("senaye", "iqtisadiyyat"), ("kripto", "iqtisadiyyat"),
    ("biznes", "iqtisadiyyat"), ("bank", "iqtisadiyyat"), ("dehliz", "iqtisadiyyat"), ("ikt", "iqtisadiyyat"),
    ("dunya", "dunya"), ("diger olke", "dunya"), ("region", "dunya"), ("mdb", "dunya"),
    ("avropa", "dunya"), ("amerika", "dunya"), ("asiya", "dunya"), ("afrika", "dunya"),
    ("yaxin serq", "dunya"),
    ("infrastruktur", "cemiyyet"), ("sosial", "cemiyyet"), ("cemiyyet", "cemiyyet"),
    ("tehsil", "cemiyyet"), ("sehiyye", "cemiyyet"), ("medeniyyet", "cemiyyet"),
]

# Bölməsi olmayan xəbərlər üçün başlıqdakı söz kökləri (sıra vacibdir: ilk uyğunluq qalib gəlir)
KEYWORDS = [
    ("hadise", ["qəza", "yanğın", "xəsarət", "həlak", "ölən", "ölüb", "öldü", "meyit", "mina", "partlay",
                "bıçaq", "cinayət", "həbs", "saxlanıl", "oğurla", "itkin", "zəlzələ", "yaralı", "ölüm",
                "toqquş", "dələduz"]),
    ("idman", ["futbol", "matç", "liqa", "uefa", "fifa", "çempion", "cüdo", "güləş", "boks", "tennis",
               "olimpiya", "yığma", "stadion", "turnir", "medal", "premyer", "kubok", "neftçi", "idman",
               "mundial", "basketbol", "voleybol", "həndbol", "şahmat"]),
    ("iqtisadiyyat", ["neft", "manat", "dollar", "qiymət", "büdcə", "bank", "birja", "ixrac", "idxal",
                      "investisiya", "qızıl", "bitcoin", "valyuta", "vergi", "inflyasiya", "iqtisad",
                      "ticarət", "təbii qaz", "enerji", "istiqraz", "maaş", "pensiya", "kredit", "ədv"]),
    ("cemiyyet", ["səhiyyə", "klinika", "xəstəxana", "həkim", "təhsil", "məktəb", "universitet",
                  "tələbə", "şagird", "kitabxana", "muzey", "teatr", "festival", "konsert"]),
    ("siyaset", ["prezident", "dövlət başçısı", "nazir", "parlament", "milli məclis", "səfir", "xin",
                 "deputat", "sammit", "əliyev", "hökumət", "sülh", "danışıq", "mdb", "tdt", "partiya"]),
    ("dunya", ["ukrayna", "rusiya", "iran", "abş", "tramp", "türkiyə", "gürcüstan", "israil", "qəzza",
               "çin", "ermənistan", "bmt", "nato", "fransa", "almaniya", "putin", "moskva", "kiyev",
               "avropa", "pentaqon", "tehran", "sudan", "venesuela", "türkmən", "qazaxıstan", "özbəkistan"]),
]
_KW_RE = [(sec, re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")"))
          for sec, words in KEYWORDS]


def classify(category: str, title: str) -> str:
    cat = to_ascii(category or "")
    if cat:
        for needle, sec in CATEGORY_MAP:
            if needle in cat:
                return sec
    text = az_lower(title or "")
    for sec, rx in _KW_RE:
        if rx.search(text):
            return sec
    return DEFAULT


def section(sid: str) -> dict:
    return BY_ID.get(sid) or BY_ID[DEFAULT]
