"""Xəbərləri bölmələrə ayırmaq: Siyasət, İqtisadiyyat, Cəmiyyət, Dünya, İdman, Hadisə.

Əvvəlcə mənbənin öz bölməsinə (RSS-dəki category) baxılır, yoxdursa başlıqdakı açar sözlərə.
"""

from __future__ import annotations

import re

from .text import to_ascii

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
    ("hadise", ["qeza", "yangin", "xesaret", "helak", "olen", "meyit", "mina", "partlay", "bicaq",
                "cinayet", "hebs", "saxlanil", "ogurl", "itkin", "zelzele", "yarali", "olum", "toqqus"]),
    ("idman", ["futbol", "matc", "liqa", "uefa", "fifa", "cempion", "cudo", "gules", "boks", "tennis",
               "olimpiya", "yigma", "stadion", "turnir", "medal", "premyer", "kubok", "neftci", "idman",
               "qarabag fk", "mundial", "basketbol", "voleybol", "boksc", "hentbol", "sahmat"]),
    ("iqtisadiyyat", ["neft", "manat", "dollar", "qiymet", "budce", "bank", "birja", "ixrac", "idxal",
                      "investisiya", "qizil", "bitcoin", "valyuta", "vergi", "inflyasiya", "iqtisad",
                      "ticaret", "tebii qaz", "enerji", "istiqraz", "maas", "pensiya", "kredit"]),
    ("cemiyyet", ["sehiyye", "klinika", "xestexana", "hekim", "tehsil", "mekteb", "universitet",
                  "telebe", "sagird", "kitabxana", "muzey", "teatr", "festival", "konsert"]),
    ("siyaset", ["prezident", "nazir", "parlament", "milli meclis", "sefir", "xin", "deputat", "sammit",
                 "eliyev", "hokumet", "sulh", "danisiq", "mdb", "tdt", "partiya"]),
    ("dunya", ["ukrayna", "rusiya", "iran", "abs", "tramp", "turkiye", "gurcustan", "israil", "qezza",
               "cin", "ermenistan", "bmt", "nato", "fransa", "almaniya", "putin", "moskva", "kiyev",
               "avropa", "pentaqon", "tehran", "sudan", "venesuela", "turkmen", "qazaxistan", "ozbekistan"]),
]
_KW_RE = [(sec, re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")"))
          for sec, words in KEYWORDS]


def classify(category: str, title: str) -> str:
    cat = to_ascii(category or "")
    if cat:
        for needle, sec in CATEGORY_MAP:
            if needle in cat:
                return sec
    text = to_ascii(title or "")
    for sec, rx in _KW_RE:
        if rx.search(text):
            return sec
    return DEFAULT


def section(sid: str) -> dict:
    return BY_ID.get(sid) or BY_ID[DEFAULT]
