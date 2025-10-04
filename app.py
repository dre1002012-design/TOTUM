# app.py — Mobile-first premium UI v3 (Streamlit)
# IMPORTANT : le « moteur » (base aliments + calculs) reste inchangé.
# Branchez vos fonctions existantes aux hooks TODO(plug:...) indiqués ci-dessous.

import streamlit as st
import pandas as pd
from typing import Dict, List, Any
import uuid
from collections import defaultdict
import streamlit.components.v1 as components

# ────────────────────────────────────────────────────────────────────────────────
# CONFIG GÉNÉRALE (orienté smartphone)
st.set_page_config(
    page_title="TOTUM · Coach Nutrition",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Viewport strict : format/cadrage auto, pas de zoom manuel si supporté
components.html(
    """
    <meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'>
    """,
    height=0,
)

# ────────────────────────────────────────────────────────────────────────────────
# STYLES — élégant, compact, homogène smartphone
CUSTOM_CSS = """
<style>
:root{
  --bg:#0b0f14; --card:#101622; --ink:#eaf2ff; --muted:#8aa0c6;
  --pri:#7aa2ff; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --over:#60a5fa; --ring:#20304a;
}
html, body, [data-testid="stAppViewContainer"]{background:var(--bg);}
[data-testid="stHeader"], [data-testid="stToolbar"]{background:transparent;}

/***** Header *****/
.header{position:sticky; top:0; z-index:10; backdrop-filter: blur(10px);
  background:linear-gradient(180deg, rgba(16,22,34,0.90), rgba(16,22,34,0.65));
  border-bottom:1px solid rgba(122,162,255,0.15);
}
.hero{display:flex; align-items:center; gap:14px; padding:14px 8px;}
.logo{width:64px; height:64px; border-radius:16px; display:grid; place-items:center;
  background:radial-gradient(80% 80% at 30% 20%,#89b4ff,transparent),linear-gradient(135deg,#2a3a58,#101522);
  box-shadow:0 14px 40px rgba(122,162,255,.28), inset 0 1px 0 rgba(255,255,255,.08);
}
.logo span{font-size:32px}
.title{color:var(--ink); font-weight:900; font-size:24px; line-height:1.05}
.subtitle{color:var(--muted); font-size:13px; margin-top:2px}

/***** Tabs plein écran *****/
[role="tablist"]{display:flex; gap:6px}
[role="tab"]{flex:1; background:var(--card); border-radius:14px; border:1px solid rgba(122,162,255,0.10)}
[role="tab"][aria-selected="true"]{outline:2px solid rgba(122,162,255,0.35)}

/***** Cartes / inputs *****/
.block{background:var(--card); border:1px solid rgba(122,162,255,0.10); border-radius:18px; padding:14px;}
.hint{color:var(--muted); font-size:12px}
.label{color:var(--ink); font-weight:700; font-size:13px}

/***** Progress bars (micros) *****/
.bar{width:100%; height:12px; background:#0f1420; border-radius:999px; position:relative; overflow:hidden; border:1px solid rgba(122,162,255,0.12)}
.fill{height:100%; border-radius:999px}
.row{display:grid; grid-template-columns: 1fr auto; gap:8px; align-items:center; margin:8px 0}
.tag{font-size:13px; color:var(--ink); font-weight:600}
.val{font-size:12px; color:var(--muted)}

/***** Macros — mini tableaux visuels *****/
.macro-grid{display:grid; grid-template-columns: repeat(3, 1fr); gap:10px}
.macro-card{background:#0f1624; border:1px solid rgba(122,162,255,0.12); border-radius:16px; padding:12px; display:grid; gap:10px; align-items:center; justify-items:center}
.macro-name{font-size:12px; color:var(--muted)}
.macro-gram{font-size:16px; color:var(--ink); font-weight:800}

/***** Anneaux de progression (SVG) *****/
.ring{width:70px; height:70px; display:grid; place-items:center}
.ring svg{filter: drop-shadow(0 2px 8px rgba(122,162,255,.25));}
.ring .pct{position:relative; top:-44px; font-size:12px; color:var(--ink); font-weight:700}

/***** Micros — liste compacte *****/
.micros{display:grid; gap:8px}
.group-title{font-weight:800; color:var(--ink); margin:8px 0 4px}
.pill{display:inline-flex; align-items:center; gap:6px; background:#0f1624; border:1px solid rgba(122,162,255,0.12); padding:6px 10px; border-radius:999px; font-size:12px; color:var(--muted)}

/* Tables compactes */
.small-table table{font-size:13px}
.small-table th, .small-table td{padding:8px 10px}

/* Champs input compacts pour mobile */
input, select, textarea{font-size:16px !important}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────────
# ÉTAT GLOBAL (compatible moteur existant)
if "food_log" not in st.session_state:
    st.session_state.food_log = []  # [{id, name, qty, unit, kcal, prot, gluc, lip, micros...}]
if "profile" not in st.session_state:
    st.session_state.profile = {
        "sex": None,
        "age": None,
        "weight": None,
        "height": None,
        "activity": "Modéré (x1.55)",
        # objectifs (figés par défaut — gardent vos calculs stables)
        "obj_prot": 100,  # %
        "obj_gluc": 100,
        "obj_lip": 100,
        "obj_kcal": 100,
    }

# ────────────────────────────────────────────────────────────────────────────────
# HOOKS MOTEUR – à brancher sur vos fonctions métiers
# TODO(plug:food_db_search): remplacez par votre recherche réelle (base/Excel/API)
_FAKE_DB = [
    {"name":"Pomme", "kcal":52, "prot":0.3, "gluc":14, "lip":0.2, "vitC":4.6, "Fe":0.1, "Ca":6.0, "Mg":5.0, "unit":"100 g"},
    {"name":"Poulet, blanc cuit", "kcal":165, "prot":31, "gluc":0, "lip":3.6, "vitC":0, "Fe":1.0, "Ca":15.0, "Mg":29.0, "unit":"100 g"},
    {"name":"Riz basmati cuit", "kcal":130, "prot":2.7, "gluc":28, "lip":0.3, "vitC":0, "Fe":0.2, "Ca":10.0, "Mg":13.0, "unit":"100 g"},
]

def search_foods(q:str)->List[Dict[str,Any]]:
    q=q.lower().strip()
    return [x for x in _FAKE_DB if q in x["name"].lower()] if q else _FAKE_DB

# TODO(plug:compute_bilan): branchez votre calculateur réel (vitamines/minéraux/énergie)
# Cette version fournit aussi un calcul simple des macros pour animer l'UI.
AJR = {
    "vitC": 90.0,   # mg
    "Fe": 8.7,      # mg
    "Ca": 1000.0,   # mg
    "Mg": 375.0,    # mg
}
CALORIES = {"prot":4, "gluc":4, "lip":9}

def compute_macros_and_micros(food_log:List[Dict[str,Any]], profile:Dict[str,Any])->Dict[str,Any]:
    totals = defaultdict(float)
    for item in food_log:
        factor = item.get("qty",1)/100.0
        for k in ("kcal","prot","gluc","lip","vitC","Fe","Ca","Mg"):
            totals[k] += (item.get(k,0) * factor)

    # Recalcule kcal par macros si kcal manquantes
    kcal_from_macros = totals["prot"]*CALORIES["prot"] + totals["gluc"]*CALORIES["gluc"] + totals["lip"]*CALORIES["lip"]
    if totals["kcal"] == 0 and kcal_from_macros>0:
        totals["kcal"] = kcal_from_macros

    # Pourcentages AJR pour micros
    micros_pct = {}
    for k, ajr in AJR.items():
        val = totals.get(k,0.0)
        micros_pct[k] = 0 if ajr==0 else round((val/ajr)*100, 1)

    # Pourcentages objectifs macros (objectifs figés = 100% par défaut)
    macros = {
        "prot": {"g": round(totals["prot"],1), "pct": 100},
        "gluc": {"g": round(totals["gluc"],1), "pct": 100},
        "lip":  {"g": round(totals["lip"],1),  "pct": 100},
        "kcal": {"kcal": int(round(totals["kcal"])) if totals["kcal"]>0 else int(round(kcal_from_macros))},
    }

    # Map lisible pour affichage
    micros_groups = {
        "vitamines": {"Vitamine C": micros_pct.get("vitC",0)},
        "mineraux":  {"Fer": micros_pct.get("Fe",0), "Calcium": micros_pct.get("Ca",0), "Magnésium": micros_pct.get("Mg",0)},
    }
    return {"macros":macros, "micros":micros_groups}

# ────────────────────────────────────────────────────────────────────────────────
# UTILITAIRES UI

def pct_color(pct: float) -> str:
    if pct < 50: return "var(--bad)"
    if pct < 100: return "var(--warn)"
    if pct <= 120: return "var(--ok)"
    return "var(--over)"

def ring_svg(pct: float) -> str:
    # Anneau de progression compact pour smartphone (SVG)
    pct = max(0, min(200, pct))
    radius = 28
    circ = 2*3.1416*radius
    prog = min(1.0, pct/100.0)
    dash = circ*prog
    gap = circ - dash
    color = pct_color(pct)
    return f"""
    <div class='ring'>
      <svg width='70' height='70' viewBox='0 0 70 70'>
        <circle cx='35' cy='35' r='{radius}' stroke='var(--ring)' stroke-width='8' fill='none'/>
        <circle cx='35' cy='35' r='{radius}' stroke='{color}' stroke-width='8' fill='none'
                stroke-dasharray='{dash} {gap}' stroke-linecap='round' transform='rotate(-90 35 35)'/>
      </svg>
      <div class='pct'>{int(round(pct))}%</div>
    </div>
    """

def bar_html(pct:float)->str:
    color = pct_color(pct)
    w = max(0, min(100, pct))
    return f"<div class='bar'><div class='fill' style='width:{w}%; background:{color}'></div></div>"

# ────────────────────────────────────────────────────────────────────────────────
# EN-TÊTE : Logo + descriptif inspirant
st.markdown(
    """
    <div class='header block'>
      <div class='hero'>
        <div class='logo'><span>⚡</span></div>
        <div>
          <div class='title'>TOTUM — Votre nutrition, simplifiée</div>
          <div class='subtitle'>Un coach malin, fun et ultra-fluide pour viser juste chaque jour.</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────────
# BARRE D'ONGLETS — plein écran avec emoji
TAB_PROFIL, TAB_JOURNAL, TAB_BILAN = st.tabs([
    "👤 Profil",
    "📒 Journal",
    "📊 Bilan",
])

# ────────────────────────────────────────────────────────────────────────────────
# ONGLET PROFIL — minimal, clair, objectifs figés
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
        ["Sédentaire (x1.2)", "Léger (x1.375)", "Modéré (x1.55)", "Intense (x1.725)", "Très intense (x1.9)"],
        index=2,
        key="activity",
    )

    st.markdown("""
    <div class='hint' style='margin-top:6px'>
      Objectifs essentiels (figés par défaut pour stabilité des calculs)
    </div>
    """, unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.slider("Protéines %", 50, 200, value=100, disabled=True, key="obj_prot")
    with c2:
        st.slider("Glucides %", 50, 200, value=100, disabled=True, key="obj_gluc")
    with c3:
        st.slider("Lipides %", 50, 200, value=100, disabled=True, key="obj_lip")
    with c4:
        st.slider("Énergie %", 50, 200, value=100, disabled=True, key="obj_kcal")
    st.markdown("</div>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────────
# ONGLET JOURNAL — recherche fluide + ajout manuel
with TAB_JOURNAL:
    st.markdown("<div class='block'>", unsafe_allow_html=True)

    q = st.text_input("🔎 Rechercher un aliment (base)", placeholder="ex. pomme, poulet, riz…")
    results = search_foods(q)

    if results:
        st.markdown("<div class='hint'>Tap pour ajouter, quantité par 100 g par défaut.</div>", unsafe_allow_html=True)
        for it in results:
            cols = st.columns([3,1,1])
            with cols[0]:
                st.markdown(f"**{it['name']}** · {it['unit']} — ~{it['kcal']} kcal")
            with cols[1]:
                qty = st.number_input("Qté (g)", min_value=1, max_value=1000, value=100, key=f"qty_{it['name']}")
            with cols[2]:
                if st.button("Ajouter ➕", key=f"add_{it['name']}"):
                    st.session_state.food_log.append({
                        "id": str(uuid.uuid4()),
                        "name": it["name"],
                        "qty": qty,
                        "unit": "g",
                        **it,
                    })
                    st.experimental_rerun()
    else:
        st.info("Aucun aliment trouvé. Essayez un autre mot.")

    st.divider()

    with st.expander("➕ Ajouter manuellement un aliment", expanded=False):
        mcols = st.columns([2,1,1,1,1])
        name = mcols[0].text_input("Nom")
        kcal = mcols[1].number_input("kcal /100g", min_value=0.0, step=1.0)
        prot = mcols[2].number_input("Prot /100g", min_value=0.0, step=0.1)
        gluc = mcols[3].number_input("Gluc /100g", min_value=0.0, step=0.1)
        lip  = mcols[4].number_input("Lip /100g",  min_value=0.0, step=0.1)
        vcols = st.columns(4)
        vitC = vcols[0].number_input("Vit C (mg/100g)", min_value=0.0, step=0.1)
        Fe   = vcols[1].number_input("Fer (mg/100g)",   min_value=0.0, step=0.1)
        Ca   = vcols[2].number_input("Calcium (mg/100g)",   min_value=0.0, step=0.1)
        Mg   = vcols[3].number_input("Magnésium (mg/100g)", min_value=0.0, step=0.1)
        if st.button("Ajouter cet aliment au journal ✅") and name:
            st.session_state.food_log.append({
                "id": str(uuid.uuid4()), "name": name, "qty": 100, "unit":"g",
                "kcal": kcal, "prot":prot, "gluc":gluc, "lip":lip,
                "vitC":vitC, "Fe":Fe, "Ca":Ca, "Mg":Mg
            })
            st.success(f"{name} ajouté !")

    st.divider()

    # Journal du jour — liste compacte
    if st.session_state.food_log:
        st.markdown("**Journal du jour**")
        total_kcal = 0
        rows = []
        for item in st.session_state.food_log:
            factor = item["qty"] / 100.0
            total_kcal += item.get("kcal",0) * factor
            rows.append({
                "Aliment": item["name"],
                "Qté": f"{item['qty']} g",
                "Énergie": round(item.get("kcal",0) * factor),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        cta_cols = st.columns([1,1,2])
        with cta_cols[0]:
            st.metric("Total kcal", value=int(total_kcal))
        with cta_cols[1]:
            if st.button("Vider le journal 🗑️"):
                st.session_state.food_log.clear()
                st.experimental_rerun()
        with cta_cols[2]:
            st.caption("Astuce : interface pensée pour smartphone (scroll vertical)")
    else:
        st.caption("Votre journal est vide. Ajoutez un aliment pour commencer.")

    st.markdown("</div>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────────
# ONGLET BILAN — macros & micros plus visuels, compacts et homogènes
with TAB_BILAN:
    st.markdown("<div class='block'>", unsafe_allow_html=True)

    bilan = compute_macros_and_micros(st.session_state.food_log, st.session_state.profile)

    # ---- MACROS : cartes compactes + anneaux ----
    st.subheader("⚙️ Macros")
    macros = bilan["macros"]
    colA, colB = st.columns([2,1])

    with colA:
        st.markdown("<div class='macro-grid'>", unsafe_allow_html=True)
        for name, label in [("prot","Protéines"),("gluc","Glucides"),("lip","Lipides")]:
            g = macros[name]["g"]
            pct = macros[name]["pct"]
            st.markdown(
                "<div class='macro-card'>" +
                ring_svg(pct) +
                f"<div class='macro-name'>{label}</div><div class='macro-gram'>{g} g</div></div>",
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)

    with colB:
        st.metric("Énergie", f"{macros['kcal']['kcal']} kcal")
        st.caption("Objectifs figés par défaut (peuvent être branchés sur vos cibles).")

    st.divider()

    # ---- MICROS : vitamines et minéraux séparés, barres pleine largeur ----
    micros = bilan["micros"]
    st.markdown("<div class='micros'>", unsafe_allow_html=True)

    st.markdown("<div class='group-title'>🧪 Vitamines</div>", unsafe_allow_html=True)
    for name, pct in micros.get("vitamines", {}).items():
        st.markdown(f"<span class='pill'>{name}</span>", unsafe_allow_html=True)
        st.markdown(f"<div class='row'><div class='tag'>Couverture</div><div class='val'>{pct}%</div></div>", unsafe_allow_html=True)
        st.markdown(bar_html(pct), unsafe_allow_html=True)

    st.markdown("<div class='group-title'>🧲 Minéraux</div>", unsafe_allow_html=True)
    for name, pct in micros.get("mineraux", {}).items():
        st.markdown(f"<span class='pill'>{name}</span>", unsafe_allow_html=True)
        st.markdown(f"<div class='row'><div class='tag'>Couverture</div><div class='val'>{pct}%</div></div>", unsafe_allow_html=True)
        st.markdown(bar_html(pct), unsafe_allow_html=True)

    st.markdown("""
    <div class='hint'>
      Code couleur : <span style='color:var(--bad)'>rouge &lt; 50%</span>,
      <span style='color:var(--warn)'>ambre 50–99%</span>,
      <span style='color:var(--ok)'>vert 100–120%</span>,
      <span style='color:var(--over)'>bleu &gt; 120%</span>.
      Écran figé (pas de zoom) pour une lecture stable sur smartphone.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────────
# NOTES D'INTÉGRATION
st.caption(
    """
    ✅ v3 UI :
    • Mobile-first, design épuré • Logo plus grand + baseline motivante
    • Onglets Profil/Journal/Bilan pleine largeur
    • Profil minimal (sexe, âge, poids, taille, activité). Objectifs : sliders figés
    • Journal : recherche fluide + ajout manuel d'aliment (micros inclus)
    • Bilan :
      – Macros en cartes compactes avec anneaux de progression (SVG) + énergie en métrique
      – Micros séparés vitamines/minéraux, barres pleine largeur, puces/badges lisibles
    • Pas de flèches latérales, pas d'options de zoom, cadrage auto smartphone

    🔌 À brancher :
      – TODO(plug:food_db_search) pour votre base réelle
      – TODO(plug:compute_bilan) si vous avez des formules/cibles spécifiques (macros & micros)
    """
)
