# components/food_search.py
# Recherche compacte & robuste pour foods.csv, avec priorité à "oeuf/œuf" (accents, ligatures, mots entiers)

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
import unicodedata

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
FOODS_CSV = ROOT / "assets" / "foods.csv"

# ---------- Modèles ----------
@dataclass
class Food:
    name: str
    kcal: float
    carbs: float
    prot: float
    fat: float

@dataclass
class Choice:
    food: Food
    grams: int  # quantité choisie en grammes

# ---------- Helpers ----------
def _num(x):
    try:
        if x is None or x == "":
            return 0.0
        return float(str(x).replace(",", "."))
    except:
        return 0.0

def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    # remplace la ligature « œ » par « oe »
    s = s.replace("œ", "oe").replace("Œ", "oe")
    s = unicodedata.normalize("NFKD", s)
    # retire les diacritiques
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def _load_csv_rows():
    if not FOODS_CSV.exists():
        return []
    CN, CK, CC, CP, CF = "nom","Énergie_kcal_100g","Glucides_g_100g","Protéines_g_100g","Lipides_g_100g"
    out = []
    with FOODS_CSV.open(encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            out.append({
                "name": (row.get(CN) or "").strip(),
                "kcal": _num(row.get(CK)),
                "carb": _num(row.get(CC)),
                "prot": _num(row.get(CP)),
                "fat":  _num(row.get(CF)),
            })
    return out

@st.cache_data(show_spinner=False)
def _get_all_foods():
    rows = _load_csv_rows()
    foods = []
    for r in rows:
        foods.append(Food(
            name=r["name"],
            kcal=r["kcal"],
            carbs=r["carb"],
            prot=r["prot"],
            fat=r["fat"],
        ))
    return foods

def _score(name_norm: str, qn: str) -> int:
    """Classement : exact > mot entier > commence par > contient."""
    if not qn:
        return 0
    if name_norm == qn:
        return 100
    tokens = name_norm.split()
    if qn in tokens:
        return 90
    if name_norm.startswith(qn):
        return 70
    if qn in name_norm:
        return 50
    return 0

def _search_foods(query: str, limit: int = 30):
    foods = _get_all_foods()
    if not query.strip():
        return foods[:limit]
    qn = _normalize(query)
    ranked = []
    for f in foods:
        n = _normalize(f.name)
        sc = _score(n, qn)
        if sc > 0:
            ranked.append((sc, f.name, f))
    if not ranked:
        return []
    ranked.sort(key=lambda t: (-t[0], t[1]))  # score desc, nom asc
    return [t[2] for t in ranked[:limit]]

# ---------- UI principal ----------
def render_food_search(prefix: str, show_custom: bool = False) -> Choice | None:
    """
    Affiche: champ de recherche + liste compacte de résultats.
    Pour chaque ligne: quantité (g) + bouton "Choisir".
    Retourne Choice(...) quand l'utilisateur clique.
    """
    st.caption("🔎 Recherche dans tous les aliments (CSV)")
    q = st.text_input("Tape un aliment (ex: oeuf, pomme…)", key=f"q_{prefix}")
    results = _search_foods(q, limit=30)

    if not results:
        st.info("Aucun résultat.")
        return None

    choice: Choice | None = None
    for idx, f in enumerate(results):
        col1, col2, col3 = st.columns([6, 2, 2])
        with col1:
            st.markdown(f"**{f.name}**  \n{kcal_fmt(f.kcal)} • {macros_fmt(f.carbs, f.prot, f.fat)}")
        with col2:
            grams = st.number_input("g", min_value=10, max_value=2000, value=100, step=10,
                                    key=f"grams_{prefix}_{idx}", label_visibility="collapsed")
        with col3:
            if st.button("Choisir", key=f"choose_{prefix}_{idx}"):
                choice = Choice(food=f, grams=int(grams))
        st.markdown("<hr style='border:none;border-top:1px dashed #eee;margin:4px 0;'>", unsafe_allow_html=True)

    return choice

def kcal_fmt(k: float) -> str:
    return f"{int(round(k))} kcal/100g"

def macros_fmt(c: float, p: float, f: float) -> str:
    return f"{round(c,1)} g C • {round(p,1)} g P • {round(f,1)} g L"


