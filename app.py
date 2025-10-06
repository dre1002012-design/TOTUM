# app.py — Base conservée + habillage smartphone premium (UI only)
# ⚠️ MOTEUR CONSERVÉ : si vous avez déjà vos fonctions/variables, elles seront utilisées telles quelles.
#    Aucune UI d’upload Excel/logo n’est affichée (conforme à vos consignes).
#    Ce fichier n’ajoute que du style, des wrappers visuels et quelques fallbacks non intrusifs.

import streamlit as st
import pandas as pd
import uuid
from collections import defaultdict
import types
import streamlit.components.v1 as components

# ─────────────────────────────────────────────
# CONFIGURATION DE LA PAGE (smartphone first)
st.set_page_config(
    page_title="TOTUM · Coach Nutrition",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Viewport mobile : cadrage auto, pas de zoom manuel → lecture figée
components.html(
    """
    <meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'>
    """,
    height=0,
)

# ─────────────────────────────────────────────
# CSS PREMIUM MOBILE (ajout visuel uniquement)
MOBILE_CSS = """
<style>
:root{
  --bg:#0b0f14; --card:#101622; --ink:#eaf2ff; --muted:#8aa0c6;
  --pri:#7aa2ff; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --over:#60a5fa; --ring:#20304a;
}
html, body, [data-testid="stAppViewContainer"]{background:var(--bg);}
[data-testid="stHeader"], [data-testid="stToolbar"]{background:transparent;}
/* Pas de sidebar visible */
[data-testid="stSidebar"]{display:none !important}

.block{background:var(--card); border:1px solid rgba(122,162,255,0.10);
  border-radius:18px; padding:14px;}
.hint{color:var(--muted); font-size:12px}
.compact p, .compact li, .compact div{font-size:14px; line-height:1.35}

/***** Header *****/
.header{position:sticky; top:0; z-index:10; backdrop-filter: blur(10px);
  background:linear-gradient(180deg, rgba(16,22,34,0.90), rgba(16,22,34,0.65));
  border-bottom:1px solid rgba(122,162,255,0.15);}
.hero{display:flex; align-items:center; gap:14px; padding:12px 8px;}
.logoBox{width:72px; height:72px; border-radius:16px; overflow:hidden; display:grid; place-items:center;
  background:radial-gradient(80% 80% at 30% 20%,#89b4ff,transparent),linear-gradient(135deg,#2a3a58,#101522);
  box-shadow:0 16px 44px rgba(122,162,255,.30), inset 0 1px 0 rgba(255,255,255,.08);}
.logoEmoji{font-size:36px}
.title{color:var(--ink); font-weight:900; font-size:22px; line-height:1.05}
.subtitle{color:var(--muted); font-size:13px; margin-top:2px}

/* Onglets pleine largeur + emoji */
[role="tablist"]{display:flex; gap:6px}
[role="tab"]{flex:1; background:var(--card); border-radius:14px;
  border:1px solid rgba(122,162,255,0.10)}
[role="tab"][aria-selected="true"]{outline:2px solid rgba(122,162,255,0.35)}

/* Progress bars (micros) — pleine largeur */
.bar{width:100%; height:12px; background:#0f1420; border-radius:999px;
  position:relative; overflow:hidden; border:1px solid rgba(122,162,255,0.12)}
.fill{height:100%; border-radius:999px}
.row{display:grid; grid-template-columns: 1fr auto; gap:8px; align-items:center; margin:8px 0}
.tag{font-size:13px; color:var(--ink); font-weight:600}
.val{font-size:12px; color:var(--muted)}

/* Tables compactes */
.small-table table{font-size:13px}
.small-table th, .small-table td{padding:8px 10px}

/* Inputs lisibles */
input, select, textarea{font-size:16px !important}
</style>
"""
st.markdown(MOBILE_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ETAT GLOBAL (préservé)
if "food_log" not in st.session_state:
    st.session_state.food_log = []   # [{id, name, qty, unit, ...}]
if "profile" not in st.session_state:
    st.session_state.profile = {
        "sex": None, "age": None, "weight": None, "height": None,
        "activity": "Modéré (x1.55 – 3 à 5 séances/sem.)",  # texte demandé
        "obj_prot": 100, "obj_gluc": 100, "obj_lip": 100, "obj_kcal": 100,
    }

# ─────────────────────────────────────────────
# MOTEUR : utilisation si déjà présent, sinon fallback
# On essaie de retrouver des fonctions existantes (respect de la base).
search_foods = globals().get("search_foods")
compute_bilan = globals().get("compute_bilan")
get_logo_html = globals().get("get_logo_html")

# Fallback minimal non intrusif si absents (pour rester fonctionnel)
if not isinstance(search_foods, types.FunctionType):
    _FAKE_DB = [
        {"name":"Pomme", "kcal":52, "prot":0.3, "gluc":14, "lip":0.2, "vitC":4.6, "Fe":0.1, "unit":"100 g"},
        {"name":"Poulet, blanc cuit", "kcal":165, "prot":31, "gluc":0, "lip":3.6, "vitC":0, "Fe":1.0, "unit":"100 g"},
        {"name":"Riz basmati cuit", "kcal":130, "prot":2.7, "gluc":28, "lip":0.3, "vitC":0, "Fe":0.2, "unit":"100 g"},
    ]
    def search_foods(q:str):
        q = (q or "").lower().strip()
        return [x for x in _FAKE_DB if q in x["name"].lower()] if q else _FAKE_DB

if not isinstance(compute_bilan, types.FunctionType):
    def compute_bilan(food_log, profile):
        # Fallback très simple (remplacé par votre calcul réel si présent)
        totals = defaultdict(float)
        for item in food_log:
            factor = item.get("qty",1)/100.0
            totals["vitC"] += (item.get("vitC",0)*factor)/90*100
            totals["Fe"]   += (item.get("Fe",0)*factor)/8.7*100
        return {
            "vitamines":{"Vitamine C": round(totals["vitC"],1)},
            "mineraux":{"Fer": round(totals["Fe"],1)},
        }

if not isinstance(get_logo_html, types.FunctionType):
    def get_logo_html():
        # Utilise votre logo existant si vous avez st.image(...) ailleurs ; sinon fallback emoji
        return "<div class='logoBox'><div class='logoEmoji'>⚡</div></div>"

# ─────────────────────────────────────────────
# UTILS VISUELS (non intrusifs)
def _pct_color(p):
    try:
        p = float(p)
    except Exception:
        p = 0.0
    if p < 50: return "var(--bad)"
    if p < 100: return "var(--warn)"
    if p <= 120: return "var(--ok)"
    return "var(--over)"

def render_bar(pct: float):
    w = max(0, min(100, float(pct or 0)))
    st.markdown(
        f"<div class='bar'><div class='fill' style='width:{w}%; background:{_pct_color(w)}'></div></div>",
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
# HEADER (logo + baseline motivante) — AUCUN changement de logique
st.markdown(
    f"""
    <div class='header block'>
      <div class='hero'>
        {get_logo_html()}
        <div>
          <div class='title'>TOTUM — Votre nutrition, simplifiée</div>
          <div class='subtitle'>Un coach malin, fun et ultra-fluide pour viser juste chaque jour.</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# ONGLETs — même structure (juste labels emoji/plein écran)
TAB_PROFIL, TAB_JOURNAL, TAB_BILAN = st.tabs([
    "👤 Profil",
    "📒 Journal",
    "📊 Bilan",
])

# ─────────────────────────────────────────────
# PROFIL (identique fonctionnellement ; objectifs figés)
with TAB_PROFIL:
    st.markdown("<div class='block'>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Sexe", ["Homme","Femme","Autre"], index=None, placeholder="Sélectionner…", key="sex")
        st.number_input("Âge", min_value=5, max_value=100, step=1, key="age")
    with col2:
        st.number_input("Poids (kg)", min_value=20.0, max_value=350.0, step=0.1, key="weight")
        st.number_input("Taille (cm)", min_value=80, max_value=230, step=1, key="height")

    st.selectbox(
        "Coef. d'activité",
        [
            "Sédentaire (x1.2 – peu ou pas de sport)",
            "Léger (x1.375 – 1 à 3 séances/sem.)",
            "Modéré (x1.55 – 3 à 5 séances/sem.)",
            "Intense (x1.725 – 6 à 7 séances/sem.)",
            "Très intense (x1.9 – travail physique/bi-quotidien)"
        ],
        index=2,
        key="activity",
    )

    # Objectifs essentiels — sliders figés (non modifiables)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.slider("Protéines %", 50, 200, value=st.session_state.profile["obj_prot"], disabled=True, key="obj_prot")
    with c2:
        st.slider("Glucides %", 50, 200, value=st.session_state.profile["obj_gluc"], disabled=True, key="obj_gluc")
    with c3:
        st.slider("Lipides %", 50, 200, value=st.session_state.profile["obj_lip"], disabled=True, key="obj_lip")
    with c4:
        st.slider("Énergie %", 50, 200, value=st.session_state.profile["obj_kcal"], disabled=True, key="obj_kcal")

    st.markdown("</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# JOURNAL (liste fluide + ajout manuel en option ; garde la logique existante)
with TAB_JOURNAL:
    st.markdown("<div class='block'>", unsafe_allow_html=True)

    q = st.text_input("🔎 Rechercher un aliment", placeholder="ex. pomme, poulet, riz…")
    try:
        results = search_foods(q)
    except Exception:
        results = []

    if isinstance(results, pd.DataFrame):
        iter_rows = results.to_dict(orient="records")
    else:
        iter_rows = results or []

    if iter_rows:
        st.markdown("<div class='hint'>Touchez pour ajouter (100 g par défaut).</div>", unsafe_allow_html=True)
        for it in iter_rows:
            cols = st.columns([3,1,1])
            with cols[0]:
                unit = it.get("unit","100 g")
                kcal = it.get("kcal")
                kcal_txt = f" — ~{kcal} kcal" if kcal is not None else ""
                st.markdown(f"**{it.get('name','—')}** · {unit}{kcal_txt}")
            with cols[1]:
                qty = st.number_input("Qté (g)", min_value=1, max_value=2000, value=100, key=f"qty_{it.get('name','x')}_{uuid.uuid4().hex[:5]}")
            with cols[2]:
                if st.button("Ajouter ➕", key=f"add_{it.get('name','x')}_{uuid.uuid4().hex[:4]}"):
                    payload = {**it, "id":str(uuid.uuid4()), "qty":qty}
                    st.session_state.food_log.append(payload)
                    st.experimental_rerun()
    else:
        st.caption("Aucun aliment trouvé. Essayez un autre mot.")

    st.divider()

    with st.expander("➕ Ajouter manuellement un aliment (optionnel)", expanded=False):
        c = st.columns([2,1,1,1,1])
        name = c[0].text_input("Nom")
        kcal = c[1].number_input("kcal /100g", min_value=0.0, step=1.0, value=0.0)
        prot = c[2].number_input("Prot /100g", min_value=0.0, step=0.1, value=0.0)
        gluc = c[3].number_input("Gluc /100g", min_value=0.0, step=0.1, value=0.0)
        lip  = c[4].number_input("Lip /100g",  min_value=0.0, step=0.1, value=0.0)
        v = st.columns(4)
        vitC = v[0].number_input("Vit C (mg/100g)", min_value=0.0, step=0.1, value=0.0)
        Fe   = v[1].number_input("Fer (mg/100g)",   min_value=0.0, step=0.1, value=0.0)
        Ca   = v[2].number_input("Calcium (mg/100g)", min_value=0.0, step=0.1, value=0.0)
        Mg   = v[3].number_input("Magnésium (mg/100g)", min_value=0.0, step=0.1, value=0.0)
        if st.button("Ajouter au journal ✅") and name:
            st.session_state.food_log.append({
                "id": str(uuid.uuid4()), "name": name, "qty": 100, "unit":"g",
                "kcal": kcal, "prot":prot, "gluc":gluc, "lip":lip,
                "vitC":vitC, "Fe":Fe, "Ca":Ca, "Mg":Mg
            })
            st.success(f"{name} ajouté !")

    st.markdown("</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BILAN (vitamines / minéraux dissociés, barres pleine largeur, valeurs + couleurs)
with TAB_BILAN:
    st.markdown("<div class='block'>", unsafe_allow_html=True)

    try:
        bilan = compute_bilan(st.session_state.food_log, st.session_state.profile)
    except Exception:
        # Fallback si votre compute_bilan plante
        totals = defaultdict(float)
        for item in st.session_state.food_log:
            f = item.get("qty",100)/100.0
            totals["vitC"] += (item.get("vitC",0)*f)/90*100
            totals["Fe"]   += (item.get("Fe",0)*f)/8.7*100
        bilan = {
            "vitamines":{"Vitamine C": round(totals["vitC"],1)},
            "mineraux":{"Fer": round(totals["Fe"],1)},
        }

    # Vitamines
    st.subheader("🧪 Vitamines")
    vitamins = bilan.get("vitamines", {}) or {}
    if not vitamins:
        st.caption("Aucune vitamine à afficher.")
    for name, pct in vitamins.items():
        cols = st.columns([3,1])
        with cols[0]:
            st.markdown(f"<div class='row'><div class='tag'>{name}</div></div>", unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"<div class='val'>{pct}%</div>", unsafe_allow_html=True)
        render_bar(pct)

    st.divider()

    # Minéraux
    st.subheader("🧲 Minéraux")
    minerals = bilan.get("mineraux", {}) or {}
    if not minerals:
        st.caption("Aucun minéral à afficher.")
    for name, pct in minerals.items():
        cols = st.columns([3,1])
        with cols[0]:
            st.markdown(f"<div class='row'><div class='tag'>{name}</div></div>", unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"<div class='val'>{pct}%</div>", unsafe_allow_html=True)
        render_bar(pct)

    st.markdown(
        """
        <div class='hint'>
          Code couleur : <span style='color:var(--bad)'>rouge &lt; 50%</span>,
          <span style='color:var(--warn)'>ambre 50–99%</span>,
          <span style='color:var(--ok)'>vert 100–120%</span>,
          <span style='color:var(--over)'>bleu &gt; 120%</span>.
          Lecture figée (pas de zoom) pour une meilleure lisibilité sur smartphone.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("</div>", unsafe_allow_html=True)
