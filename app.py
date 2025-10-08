# Totum — Suivi nutritionnel (V7)
# Modifications minimes : ajout CSS pour forcer rendu clair (fond blanc + texte encre foncé)
# Aucun autre changement structurel, logique, base, import/export, fonctions, etc.
from __future__ import annotations
import os, io, re, json, sqlite3, unicodedata, datetime as dt, base64, random, math
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import openpyxl

VERSION = "v2025-10-07-v7-logo-centered-white-consels-journal-search-optimized"

# --- Page config (layout wide, sidebar fermée) ---
st.set_page_config(
    page_title="Totum — suivi nutritionnel",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_PATH = os.path.join(os.getcwd(), "totum.db")

# === Assets packagés
ASSETS_DIR = Path(__file__).parent / "assets"
DEFAULT_EXCEL_PATH = ASSETS_DIR / "TOTUM-Suivi nutritionnel.xlsx"
DEFAULT_LOGO_PATH  = ASSETS_DIR / "logo.png"

# ===================== Utils =====================
def strip_accents(text: str) -> str:
    text = str(text or "")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

def canon(s: str) -> str:
    s = strip_accents(str(s)).lower().replace("_", " ").replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()

def canon_key(s: str) -> str:
    return canon(s).replace("(", "").replace(")", "").replace("’", "'").replace(" ", "").replace("__", "_")

def norm(s: str) -> str:
    s = strip_accents(s).lower()
    return re.sub(r"[^a-z0-9]+", "", s)

def normalize_unit(u: str) -> str:
    u = (u or "").strip()
    u = u.replace("mcg", "µg").replace("ug", "µg").replace("μg", "µg")
    return u

def parse_name_unit(label: str) -> tuple[str,str]:
    if label is None: return "", ""
    s = str(label).strip()
    parts = re.split(r"\s*[-–—]\s*", s)
    if len(parts) >= 2:
        unit = normalize_unit(parts[-1])
        name = "-".join(parts[:-1]).strip()
        return name, unit
    return s, ""

def coerce_num_col(s: pd.Series | None) -> pd.Series | None:
    if s is None: return None
    s = s.astype(str).str.replace("\u00A0", " ", regex=False).str.replace(",", ".", regex=False)
    ext = s.str.extract(r"([-+]?\d*\.?\d+)")[0]
    return pd.to_numeric(ext, errors="coerce")

def percent(n, d):
    n = pd.to_numeric(n, errors="coerce").fillna(0.0)
    d = pd.to_numeric(d, errors="coerce").replace(0, np.nan)
    return (n / d * 100).fillna(0.0)

def nutrient_cols(df_or_row):
    cols = list(df_or_row.index if isinstance(df_or_row, pd.Series) else df_or_row.columns)
    return [c for c in cols if str(c).endswith("_100g")]

def per100_to_name(c): return c[:-5]

def drop_parasite_columns(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty: return df
    cols = []
    for c in df.columns:
        sc = str(c).strip().lower()
        if sc == "" or sc.startswith("unnamed") or sc in {"done","none","nan"}:
            continue
        cols.append(c)
    out = df[cols]
    return out.loc[:, ~(out.isna().all())]

def read_sheet_values_path(path: Path, sheet_name: str) -> pd.DataFrame | None:
    try:
        bio = io.BytesIO(Path(path).read_bytes())
        wb = openpyxl.load_workbook(bio, data_only=True, read_only=True)
        if sheet_name not in wb.sheetnames: return None
        ws = wb[sheet_name]
        rows = list(ws.values)
        if not rows: return None
        header = [str(x) if x is not None else "" for x in rows[0]]
        df = pd.DataFrame(rows[1:], columns=header)
        return drop_parasite_columns(df)
    except Exception:
        return None

def clean_liste(df_liste: pd.DataFrame) -> pd.DataFrame:
    df_liste = drop_parasite_columns(df_liste)
    assert "nom" in df_liste.columns, "La feuille 'Liste' doit contenir la colonne 'nom'."
    if "Energie_kcal_100g" in df_liste.columns and "Énergie_kcal_100g" not in df_liste.columns:
        df_liste = df_liste.rename(columns={"Energie_kcal_100g": "Énergie_kcal_100g"})
    keep = ["nom"] + [c for c in df_liste.columns if c.endswith("_100g")]
    df = df_liste[keep].copy()
    for c in [x for x in df.columns if x.endswith("_100g")]:
        df[c] = coerce_num_col(df[c]).fillna(0.0)

    # fusion de colonnes quasi identiques
    dup_groups = {}
    for c in [x for x in df.columns if x.endswith("_100g")]:
        key = canon_key(c)
        dup_groups.setdefault(key, []).append(c)
    for cols in dup_groups.values():
        if len(cols) > 1:
            base = sorted(cols, key=len)[0]
            df[base] = df[cols].sum(axis=1, numeric_only=True)
            for extra in cols:
                if extra != base and extra in df.columns:
                    df.drop(columns=[extra], inplace=True, errors="ignore")
    return df

def calc_from_food_row(row: pd.Series, qty_g: float) -> dict:
    out = {}
    for c in nutrient_cols(row):
        val = pd.to_numeric(pd.Series([row[c]]), errors="coerce").iloc[0]
        if pd.notna(val):
            out[per100_to_name(c)] = float(qty_g) * float(val) / 100.0
    return out

# ============ Couleurs ============
COLORS = {
    "brand":    "#ff7f3f",   "brand2":   "#ffb347",
    "ink":      "#0d1b1e",   "muted":    "#5f6b76",
    "energie":   "#ff7f3f",  "proteines": "#2ca02c",
    "glucides":  "#1f77b4",  "lipides":   "#d62728",
    "fibres":    "#9467bd",  "omega3":    "#00bcd4",
    "epa":       "#26a69a",  "dha":       "#7e57c2",
    "omega6":    "#ffb300",  "omega9":    "#8d6e63",
    "restant":   "#e0e0e0",  "objectif":  "#bdbdbd",
    "ok":        "#5cb85c",  "warn":      "#f0ad4e", "bad":"#d9534f",
}

# ============ Mobile-first CSS + Header plat (FORCE WHITE) ============
def apply_mobile_css_and_topbar(logo_b64: str | None):
    """
    Fonction d'affichage header + CSS.
    J'ai ajouté ici une directive minimale pour FORCER le rendu clair (color-scheme: light)
    afin d'empêcher l'OS / navigateur d'inverser ou d'assombrir certains éléments la nuit.
    Aucun changement de logique, ni de favicon, ni d'icône d'écran d'accueil.
    """
    st.markdown(f"""
    <meta name="theme-color" content="#ffffff">
    <style>
    /* cacher éléments Streamlit non désirés */
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], header, footer {{display:none!important;}}

    /* Forcer scheme clair : empêche certains navigateurs d'inverser couleurs */
    html, body {{ color-scheme: light; -webkit-text-size-adjust: 100%; }}

    :root {{
      --bg: #ffffff;
      --ink: {COLORS['ink']};
      --muted: {COLORS['muted']};
    }}

    html, body, .stApp, [data-testid="stAppViewContainer"] {{
      background: var(--bg)!important;
      color: var(--ink)!important;
      -webkit-text-fill-color: var(--ink) !important;
      min-height:100vh;
      font-size:15.5px;
    }}

    /* neutraliser filtres d'accessibilité / inversion éventuelle */
    img, svg, canvas, .stMarkdown, .st-bokeh, .st-echarts, .stPlotly {{
      filter: none !important;
      mix-blend-mode: normal !important;
      -webkit-filter: none !important;
    }}

    .block-container {{ padding-top:.8rem; padding-bottom:.8rem; max-width:1100px; }}

    /* Header très plat, logo centré (inchangé) */
    .topbar {{ position:sticky; top:0; z-index:100; padding:.6rem 0 .6rem 0; margin:0 0 .2rem 0; display:flex; justify-content:center; align-items:center; }}
    .topbar-logo {{ width:140px; height:140px; object-fit:contain; }}

    [data-baseweb="tab-list"] {{ width:100%; display:grid!important; grid-template-columns:1fr 1fr 1fr 1fr; gap:.35rem; margin:.6rem 0 .2rem 0; }}
    [data-baseweb="tab-list"] button {{ width:100%; background:#fff; color:var(--ink); border-radius:12px!important; border:1px solid rgba(0,0,0,0.08); padding:.55rem .6rem!important; font-weight:800; box-shadow:none; }}
    [data-baseweb="tab-highlight"] {{ background: linear-gradient(90deg, {COLORS['brand']}, {COLORS['brand2']}); height:3px; }}

    .stButton>button {{ background: linear-gradient(90deg, {COLORS['brand']}, {COLORS['brand2']}); border:0; color:#fff; font-weight:900; box-shadow:none; border-radius:12px; }}
    .donut-title {{ font-size:14px; font-weight:800; margin-bottom:.15rem; color:var(--ink); }}
    .dot {{ display:inline-block; width:.8em; height:.8em; border-radius:50%; margin-right:.35em; vertical-align:middle; }}

    /* Cartes (onglet Conseils) */
    .cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:.75rem; }}
    .card {{ border:1px solid rgba(0,0,0,0.06); border-radius:14px; padding:.85rem .9rem; background:#fff; }}
    .card h4 {{ margin:.1rem 0 .25rem 0; font-size:1.03rem; }}
    .card .role {{ color:var(--muted); font-size:.93rem; margin-bottom:.25rem; }}
    .card .benef {{ font-size:.95rem; }}
    </style>
    """, unsafe_allow_html=True)

    logo_html = f"<img class='topbar-logo' src='data:image/png;base64,{logo_b64}' alt='logo'/>" if logo_b64 else ""
    st.markdown(f"""
    <div class="topbar">
      <div>{logo_html}</div>
    </div>
    """, unsafe_allow_html=True)

def set_favicon_from_logo(logo_b64: str | None):
    # NE PAS modifier ni forcer l'icône écran d'accueil ici : on laisse le comportement par défaut.
    # (la requête initiale demandait cela, mais tu as demandé ensuite de NE PAS toucher au logo/fav).
    # Conserver comme no-op pour éviter toute modification non souhaitée.
    return

def round1(x) -> float:
    try: return float(np.round(float(x), 1))
    except Exception: return 0.0

def donut(cons, target, title, color_key="energie", height=210):
    cons = float(cons or 0.0); target = float(target or 0.0)
    if target <= 0:
        fig = go.Figure(data=[go.Pie(values=[1], labels=["Objectif manquant"], hole=0.68,
                                     textinfo="label", marker_colors=[COLORS["objectif"]])])
        fig.update_layout(title=title, margin=dict(l=0,r=0,t=34,b=0), height=height, showlegend=False,
                          font=dict(size=13, color=COLORS['ink']), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
        return fig
    pct = 0 if target == 0 else cons/target*100
    wedge = COLORS["ok"] if pct>=100 else (COLORS["warn"] if pct>=50 else COLORS["bad"])
    rest = max(target - cons, 0.0)
    fig = go.Figure(data=[go.Pie(values=[cons, rest], labels=["Ingéré","Restant"], hole=0.70, textinfo="none",
                                 marker=dict(colors=[wedge, COLORS["restant"]], line=dict(width=0)), sort=False)])
    fig.update_layout(
        title=title,
        annotations=[dict(text=f"{cons:.1f}/{target:.1f}<br>({pct:.0f}%)", x=0.5, y=0.5, showarrow=False, font=dict(size=15, color=COLORS['ink']))],
        margin=dict(l=0,r=0,t=32,b=0), height=height, showlegend=False, font=dict(size=13, color=COLORS['ink']),
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff"
    )
    return fig

# ============ Unification totaux ============
PREFERRED_NAMES = {
    "energiekcal":"Énergie_kcal", "proteinesg":"Protéines_g", "glucidesg":"Glucides_g", "lipidesg":"Lipides_g",
    "fibresg":"Fibres_g", "agsaturesg":"AG_saturés_g",
    "acideoleiquew9g":"Acide_oléique_W9_g", "acidelinoleiquew6lag":"Acide_linoléique_W6_LA_g",
    "acidealphalinoleniquew3alag":"Acide_alpha-linolénique_W3_ALA_g", "acidealpha-linoléniquew3alag":"Acide_alpha-linolénique_W3_ALA_g",
    "acidealpha_linolenique_w3_alag":"Acide_alpha-linolénique_W3_ALA_g", "acidealphalinoleniquew3ala":"Acide_alpha-linolénique_W3_ALA_g",
    "omega3alag":"Acide_alpha-linolénique_W3_ALA_g", "omega3ala":"Acide_alpha-linolénique_W3_ALA_g",
    "w3alag":"Acide_alpha-linolénique_W3_ALA_g", "alag":"Acide_alpha-linolénique_W3_ALA_g",
    "epag":"EPA_g", "dhag":"DHA_g", "sucresg":"Sucres_g", "selg":"Sel_g",
}
def unify_totals_series(s: pd.Series) -> pd.Series:
    if not isinstance(s, pd.Series) or s.empty: return s
    buckets: dict[str, float] = {}; name_for_bucket: dict[str,str] = {}
    for col in s.index:
        key = canon_key(col); preferred = PREFERRED_NAMES.get(key); bucket = preferred or key
        buckets[bucket] = buckets.get(bucket, 0.0) + float(s[col] or 0.0)
        name_for_bucket[bucket] = bucket
    out = pd.Series(buckets)
    out.index = [name_for_bucket[i] for i in out.index]
    return out

# ============ SQLite helpers ============
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        repas TEXT,
        nom TEXT,
        quantite_g REAL,
        nutrients_json TEXT
    );
    """)
    conn.commit()
    return conn

def insert_journal(date_iso, repas, nom, quantite_g, nutrients: dict):
    conn = init_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO journal (date, repas, nom, quantite_g, nutrients_json) VALUES (?,?,?,?,?);",
                (date_iso, repas, nom, float(quantite_g), json.dumps(nutrients, ensure_ascii=False)))
    conn.commit()

def update_journal_row(row_id: int, date_iso, repas, nom, quantite_g, nutrients: dict):
    conn = init_db()
    cur = conn.cursor()
    cur.execute("UPDATE journal SET date=?, repas=?, nom=?, quantite_g=?, nutrients_json=? WHERE id=?;",
                (date_iso, repas, nom, float(quantite_g), json.dumps(nutrients, ensure_ascii=False), int(row_id)))
    conn.commit()

def delete_journal_row(row_id: int):
    conn = init_db()
    conn.execute("DELETE FROM journal WHERE id=?", (int(row_id),))
    conn.commit()

def fetch_journal_by_date(date_iso) -> pd.DataFrame:
    conn = init_db()
    cur = conn.execute("SELECT id,date,repas,nom,quantite_g,nutrients_json FROM journal WHERE date=? ORDER BY id ASC;", (date_iso,))
    rows = cur.fetchall()
    if not rows: return pd.DataFrame(columns=["id","date","repas","nom","quantite_g"])
    df = pd.DataFrame(rows, columns=["id","date","repas","nom","quantite_g","nutrients_json"])
    expanded = []
    for js in df["nutrients_json"]:
        try: expanded.append(json.loads(js))
        except Exception: expanded.append({})
    nutr_df = pd.DataFrame(expanded).fillna(0.0)
    return pd.concat([df.drop(columns=["nutrients_json"]), nutr_df], axis=1)

def fetch_all_journal() -> pd.DataFrame:
    conn = init_db()
    cur = conn.execute("SELECT id,date,repas,nom,quantite_g,nutrients_json FROM journal ORDER BY date, id;")
    rows = cur.fetchall()
    if not rows: return pd.DataFrame(columns=["date","repas","nom","quantite_g"])
    df = pd.DataFrame(rows, columns=["id","date","repas","nom","quantite_g","nutrients_json"])
    expanded = []
    for js in df["nutrients_json"]:
        try: expanded.append(json.loads(js))
        except Exception: expanded.append({})
    nutr_df = pd.DataFrame(expanded).fillna(0.0)
    return pd.concat([df.drop(columns=["nutrients_json"]), nutr_df], axis=1)

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Journal")
    return out.getvalue()

def fetch_last_date_with_rows() -> str | None:
    conn = init_db()
    cur = conn.execute("SELECT date, COUNT(*) c FROM journal GROUP BY date ORDER BY date DESC;")
    r = cur.fetchone()
    return r[0] if r else None

# ============ Chargement Excel auto ============
def build_objectif_robuste(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty: return pd.Series(dtype=float)
    candidates = [c for c in ["Objectif","Ojectifs","Cible","Objectifs","Objectif (jour)","Target","Cible (jour)"] if c in df.columns]
    out = pd.Series(0.0, index=df.index, dtype=float)
    for c in candidates:
        v = coerce_num_col(df[c])
        out = out.where(out > 0, v.fillna(0.0))
    return pd.Series([round1(x) for x in out], index=df.index, dtype=float)

def load_assets_default():
    if not DEFAULT_EXCEL_PATH.exists(): return
    # Liste
    df_liste = read_sheet_values_path(DEFAULT_EXCEL_PATH, "Liste")
    if df_liste is not None and not df_liste.empty:
        st.session_state["foods"] = clean_liste(df_liste)
    # Cibles micro
    sex = st.session_state["profile"]["sexe"]
    micro_sheet = "Cible micro Homme" if canon(sex).startswith("homme") else "Cible micro Femme"
    df_micro = read_sheet_values_path(DEFAULT_EXCEL_PATH, micro_sheet)
    if df_micro is not None and "Nutriment" in df_micro.columns:
        tm = drop_parasite_columns(df_micro.copy()); tm["Objectif"] = build_objectif_robuste(tm)
        keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tm.columns]
        st.session_state["targets_micro"] = tm[keep]
    # Cibles macro
    df_macro_raw = read_sheet_values_path(DEFAULT_EXCEL_PATH, "Cible Macro")
    if df_macro_raw is not None and "Nutriment" in df_macro_raw.columns:
        tmac = drop_parasite_columns(df_macro_raw.copy())
        if "Objectif" not in tmac.columns: tmac["Objectif"] = build_objectif_robuste(tmac)
        keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tmac.columns]
        st.session_state["targets_macro"] = tmac[keep]

# ============ Helper: mapping macro names ============
def macro_base_name(label: str) -> str:
    name, _ = parse_name_unit(label); nc = canon(name); ns = nc.replace(" ", "")
    if nc.startswith("energie"): return "energie"
    if nc.startswith("proteine"): return "proteines"
    if nc.startswith("glucide"): return "glucides"
    if nc.startswith("lipide"): return "lipides"
    if nc.startswith("sucres"): return "sucres"
    if "acides grassatures" in nc or "acides gras satures" in nc or "ag satures" in nc or "agsatures" in nc: return "agsatures"
    if "omega9" in ns or ("oleique" in nc and "w9" in nc): return "omega9"
    if "omega6" in ns or ("linoleique" in nc and ("w6" in nc or "la" in nc)): return "omega6"
    if "epa" in nc: return "epa"
    if "dha" in nc: return "dha"
    if "omega3" in ns or "w3" in ns or ("alpha" in nc and "linolenique" in nc) or "ala" in nc: return "ala"
    if nc.startswith("fibres"): return "fibres"
    if nc.startswith("sel"): return "sel"
    return name

# ============ Session ============
if "foods" not in st.session_state: st.session_state["foods"] = pd.DataFrame(columns=["nom"])
if "targets_micro" not in st.session_state: st.session_state["targets_micro"] = pd.DataFrame()
if "targets_macro" not in st.session_state: st.session_state["targets_macro"] = pd.DataFrame()
if "logo_bytes" not in st.session_state: st.session_state["logo_bytes"] = None

# profile load/save (simple JSON in working dir)
PROFILE_PATH = os.path.join(os.getcwd(), "profile.json")
def load_profile():
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf8") as f:
                return json.load(f)
        except Exception:
            pass
    # default
    return {"sexe":"Homme", "age":35, "taille_cm":175, "poids_kg":75, "activite":"Modéré (3-5x/sem)"}

def save_profile(p: dict):
    with open(PROFILE_PATH, "w", encoding="utf8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    st.session_state["profile"] = p

def get_profile_targets_cached():
    p = st.session_state.get("profile", load_profile())
    # simple macros calc (exemple)
    poids = float(p.get("poids_kg", 70))
    sexe = p.get("sexe", "Homme")
    if sexe and canon(sexe).startswith("fem"):
        factor = 1.0
    else:
        factor = 1.0
    energie_kcal = 2000 + (poids - 70) * 10
    proteines_g = poids * 1.2
    glucides_g = energie_kcal * 0.5 / 4
    lipides_g = energie_kcal * 0.25 / 9
    fibres_g = 30.0
    out = {"energie_kcal": energie_kcal, "proteines_g": proteines_g, "glucides_g": glucides_g, "lipides_g": lipides_g, "fibres_g": fibres_g}
    st.session_state["profile_targets"] = out
    return out

if "profile" not in st.session_state: st.session_state["profile"] = load_profile()
if "last_added_date" not in st.session_state: st.session_state["last_added_date"] = None
if "profile_targets" not in st.session_state: st.session_state["profile_targets"] = get_profile_targets_cached()

# -- logo auto
def _reload_default_logo():
    if DEFAULT_LOGO_PATH.exists():
        st.session_state["logo_bytes"] = DEFAULT_LOGO_PATH.read_bytes()
_reload_default_logo()
load_assets_default()

def _logo_b64() -> str | None:
    data = st.session_state.get("logo_bytes")
    if not data and DEFAULT_LOGO_PATH.exists():
        data = DEFAULT_LOGO_PATH.read_bytes()
    return base64.b64encode(data).decode() if data else None

# ===================== HEADER + FAVICON =====================
apply_mobile_css_and_topbar(_logo_b64())
set_favicon_from_logo(_logo_b64())

# ===================== PAGES modifications =====================

# ---------- helper: improved search/fuzzy (lightweight, no extra dependency) ----------
def journal_search_candidates(foods_df: pd.DataFrame, q: str, limit: int = 12) -> list[str]:
    """
    Recherche optimisée :
    - priorité startswith (meilleure correspondance)
    - ensuite token match (tous tokens présents)
    - ensuite contains
    - fallback : approximate by character overlap score
    """
    if foods_df is None or foods_df.empty:
        return []
    q = (q or "").strip()
    base = foods_df["nom"].astype(str).tolist()
    if not q:
        return base[:limit]
    q_canon = canon(q)
    q_tokens = [t for t in q_canon.split(" ") if t]
    starts = []
    token_match = []
    contains = []
    for name in base:
        c = canon(name)
        if c.startswith(q_canon):
            starts.append(name); continue
        # token match: all tokens present
        if all(tok in c for tok in q_tokens):
            token_match.append(name); continue
        if q_canon in c:
            contains.append(name); continue
    # fallback approximate: score by number of matching chars (simple heuristic)
    rest = [n for n in base if n not in starts and n not in token_match and n not in contains]
    def char_score(a, b):
        sa = set(canon(a))
        sb = set(canon(b))
        inter = len(sa & sb)
        union = max(len(sa | sb), 1)
        return inter / union
    rest_sorted = sorted(rest, key=lambda x: -char_score(x, q_canon))
    out = starts + token_match + contains + rest_sorted
    # dedupe preserving order
    seen = set(); uniq = []
    for x in out:
        if x not in seen:
            uniq.append(x); seen.add(x)
    return uniq[:limit]

# ---------- render profile (unchanged majorly) ----------
def render_profile_page():
    st.subheader("👤 Profil")
    p = st.session_state["profile"]
    c1, c2, c3, c4 = st.columns(4)
    p["sexe"] = c1.selectbox("Sexe", ["Homme","Femme"], index=0 if canon(p["sexe"]).startswith("homme") else 1)
    p["age"]       = int(c2.number_input("Âge",        min_value=10,  max_value=100,  value=int(p["age"]),       step=1))
    p["taille_cm"] = int(c3.number_input("Taille (cm)",min_value=120, max_value=230,  value=int(p["taille_cm"]),  step=1))
    p["poids_kg"]  = int(c4.number_input("Poids (kg)", min_value=30,  max_value=250,  value=int(p["poids_kg"]),   step=1))
    p["activite"] = st.selectbox("Activité",
        ["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"],
        index=["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"].index(p["activite"])
    )
    p["repartition_macros"] = (30,55,15)
    st.session_state["profile"] = p

    if st.button("💾 Sauver mon profil"):
        save_profile(p); get_profile_targets_cached(); st.success("Profil enregistré.")

    profile_targets = get_profile_targets_cached()
    st.markdown("#### 🎯 Objectifs clés (calculés)")
    kc, pr, gl, li, fi = st.columns(5)
    kc.metric("Énergie (kcal)", f"{profile_targets['energie_kcal']:.1f}")
    pr.metric("Protéines (g)", f"{profile_targets['proteines_g']:.1f}")
    gl.metric("Glucides (g)", f"{profile_targets['glucides_g']:.1f}")
    li.metric("Lipides (g)",   f"{profile_targets['lipides_g']:.1f}")
    fi.metric("Fibres (g)",    f"{profile_targets['fibres_g']:.1f}")

# ---------- render journal (improved search + UX) ----------
def render_journal_page():
    st.subheader("🧾 Journal")
    foods = st.session_state["foods"]

    # Recherche intelligente
    q = st.text_input("🔎 Rechercher un aliment", placeholder="Tape 2-3 lettres… (ex: poulet, riz, pomme)")
    # Generate prioritized suggestions using journal_search_candidates
    suggestions = journal_search_candidates(foods, q, limit=10)
    if suggestions:
        st.caption("Suggestions rapides : clique pour ajouter en un clic 👇")
        for idx, name in enumerate(suggestions):
            with st.container():
                cA, cB, cC = st.columns([6,2,2])
                cA.write(f"• {name}")
                qty_key = f"qty_sugg_{idx}"
                qty_val = cB.number_input("g", min_value=1, value=150, step=10, key=qty_key, label_visibility="collapsed")
                if cC.button("➕", key=f"add_sugg_{idx}"):
                    row = foods.loc[foods["nom"] == name]
                    if not row.empty:
                        row = row.iloc[0]
                        calc = calc_from_food_row(row, qty_val)
                        insert_journal(dt.date.today().isoformat(), "Déjeuner", name, qty_val, calc)
                        st.session_state["last_added_date"] = dt.date.today().isoformat()
                        st.success(f"Ajouté : {qty_val} g de {name} (Déjeuner)")

    st.divider()

    # Ajout standard
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    date_sel = c1.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY", key="date_input_journal")
    repas = c2.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"])
    qty = c3.number_input("Quantité (g)", min_value=1, value=150, step=10)
    options = foods["nom"].astype(str).tolist() if not foods.empty else ["(liste vide)"]
    # apply local filtering with same search heuristic to keep options small & fast
    if q:
        options = journal_search_candidates(foods, q, limit=200) or options
    nom = c4.selectbox("Aliment (liste)", options=options)
    if st.button("➕ Ajouter (depuis la liste)"):
        if not foods.empty and nom != "(liste vide)":
            row = foods.loc[foods["nom"] == nom]
            if not row.empty:
                row = row.iloc[0]
                calc = calc_from_food_row(row, qty)
                insert_journal(date_sel.isoformat(), repas, nom, qty, calc)
                st.session_state["last_added_date"] = date_sel.isoformat()
                st.success(f"Ajouté : {qty} g de {nom} ({repas})")

    # Aliment personnalisé
    with st.expander("➕ Ajouter un aliment personnalisé"):
        cpa, cpb, cpc = st.columns(3)
        nom_pers = cpa.text_input("Nom de l'aliment", placeholder="ex: Mon smoothie")
        qty_pers = cpb.number_input("Quantité (g)", min_value=1, value=200, step=10, key="qty_pers")
        repas_p  = cpc.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"], index=1, key="repas_p")

        st.caption("Valeurs pour 100 g (tu peux en remplir seulement quelques-unes) :")
        m1, m2, m3, m4, m5 = st.columns(5)
        prot100 = m1.number_input("Protéines (g/100g)", 0.0, step=0.5)
        gluc100 = m2.number_input("Glucides (g/100g)",  0.0, step=0.5)
        lip100  = m3.number_input("Lipides (g/100g)",   0.0, step=0.5)
        fib100  = m4.number_input("Fibres (g/100g)",    0.0, step=0.5)
        ags100  = m5.number_input("AG saturés (g/100g)",0.0, step=0.5)

        n1, n2, n3 = st.columns(3)
        ala100 = n1.number_input("Oméga-3 ALA (g/100g)", 0.0, step=0.1)
        epa100 = n2.number_input("EPA (g/100g)",         0.0, step=0.1)
        dha100 = n3.number_input("DHA (g/100g)",         0.0, step=0.1)

        o1, o2 = st.columns(2)
        o6100 = o1.number_input("Oméga-6 (LA) (g/100g)", 0.0, step=0.1)
        o9100 = o2.number_input("Oméga-9 (oléique) (g/100g)", 0.0, step=0.1)

        if st.button("➕ Ajouter cet aliment personnalisé"):
            if nom_pers.strip():
                kcal100 = prot100*4 + gluc100*4 + lip100*9
                factor = qty_pers / 100.0
                nutr = {
                    "Énergie_kcal": kcal100 * factor,
                    "Protéines_g":  prot100 * factor,
                    "Glucides_g":   gluc100 * factor,
                    "Lipides_g":    lip100  * factor,
                    "Fibres_g":     fib100  * factor,
                    "AG_saturés_g": ags100  * factor,
                    "Acide_alpha-linolénique_W3_ALA_g": ala100 * factor,
                    "EPA_g": epa100 * factor,
                    "DHA_g": dha100 * factor,
                    "Acide_linoléique_W6_LA_g": o6100 * factor,
                    "Acide_oléique_W9_g": o9100 * factor,
                }
                insert_journal(date_sel.isoformat(), repas_p, nom_pers.strip(), qty_pers, nutr)
                st.session_state["last_added_date"] = date_sel.isoformat()
                st.success(f"Ajouté : {qty_pers} g de {nom_pers} ({repas_p})")

    st.markdown("### Lignes du jour")
    df_day = fetch_journal_by_date(date_sel.isoformat())
    if not df_day.empty:
        preferred_order = ["date","repas","nom","quantite_g","Énergie_kcal","Protéines_g","Glucides_g","Lipides_g",
                           "Fibres_g","AG_saturés_g","Acide_linoléique_W6_LA_g","Acide_oléique_W9_g",
                           "Acide_alpha-linolénique_W3_ALA_g","EPA_g","DHA_g"]
        cols = [c for c in preferred_order if c in df_day.columns] + [c for c in df_day.columns if c not in preferred_order]
        df_show = df_day[cols].copy()
        numcols = df_show.select_dtypes(include=[np.number]).columns
        df_show[numcols] = df_show[numcols].applymap(round1)
        st.dataframe(df_show, use_container_width=True)

    if not df_day.empty:
        st.markdown("#### Supprimer une ligne")
        options = df_day[["id","repas","nom","quantite_g"]].copy()
        options["label"] = options.apply(lambda r: f'#{int(r["id"])} — {r["repas"]}: {r["nom"]} ({round1(r["quantite_g"])} g)', axis=1)
        sel_label = st.selectbox("Ligne à supprimer", options["label"].tolist())
        sel_id = int(options.loc[options["label"].eq(sel_label), "id"].iloc[0])
        if st.button("🗑️ Supprimer cette ligne"):
            delete_journal_row(sel_id); st.success(f"Ligne #{sel_id} supprimée."); st.rerun()

# ---------- bilan (inchangé sauf petites optimisations) ----------
def unify_totals_for_date(date_iso: str) -> pd.Series:
    df_today = fetch_journal_by_date(date_iso)
    if not df_today.empty:
        base_exclude = {"id","date","repas","nom","quantite_g"}
        df_clean = drop_parasite_columns(df_today).copy()
        for c in df_clean.columns:
            if c not in base_exclude: df_clean[c] = pd.to_numeric(df_clean[c], errors="coerce")
        df_num = df_clean.drop(columns=[c for c in base_exclude if c in df_clean.columns], errors="ignore")
        raw = df_num.sum(numeric_only=True)
        return unify_totals_series(raw)
    return pd.Series(dtype=float)

def render_bilan_page():
    st.subheader("📊 Bilan")
    default_bilan_date = dt.date.today()
    last_with = fetch_last_date_with_rows()
    if last_with and fetch_journal_by_date(default_bilan_date.isoformat()).empty:
        if st.session_state.get("last_added_date"):
            try: default_bilan_date = pd.to_datetime(st.session_state["last_added_date"]).date()
            except Exception: default_bilan_date = pd.to_datetime(last_with).date()
        else:
            default_bilan_date = pd.to_datetime(last_with).date()

    date_bilan = st.date_input("Date", value=default_bilan_date, format="DD/MM/YYYY", key="date_bilan")
    df_day = fetch_journal_by_date(date_bilan.isoformat())
    totals = unify_totals_for_date(date_bilan.isoformat())

    targets_macro = st.session_state["targets_macro"].copy()
    targets_micro = st.session_state["targets_micro"].copy()
    profile_targets = st.session_state.get("profile_targets", get_profile_targets_cached())

    # === ALA : calcul conso robuste ===
    def _find_ala_columns_in(dfcols: list[str]) -> list[str]:
        cols = []
        for c in dfcols:
            ck = canon_key(c)
            if "epa" in ck or "dha" in ck: continue
            if ("ala" in ck and ("omega3" in ck or "w3" in ck)) or ("alpha" in ck and "linolen" in ck) \
               or ck.endswith("alag") or ck.endswith("ala") or "acidealphalinoleniquew3" in ck:
                cols.append(c)
        return cols

    def _ala_consumed_from_day(df: pd.DataFrame, totals_series: pd.Series) -> float:
        if df is not None and not df.empty:
            ala_cols = _find_ala_columns_in(df.columns.tolist())
            if ala_cols:
                s = pd.DataFrame(df[ala_cols]).apply(pd.to_numeric, errors="coerce").fillna(0.0)
                return float(s.sum(numeric_only=True).sum())
        # fallback : chercher dans totals
        for k in totals_series.index:
            if "ala" in canon_key(k) and pd.notna(totals_series[k]):
                try: return float(totals_series[k])
                except Exception: pass
        return 0.0

    ala_consumed = _ala_consumed_from_day(df_day, totals)

    # Macros donut (énergie, prot, glu, lip)
    cols = st.columns(4)
    if "Énergie_kcal" in totals.index:
        fig = donut(float(totals.get("Énergie_kcal", 0.0)), float(profile_targets.get("energie_kcal", 0.0)), "Énergie (kcal)", "energie")
        cols[0].plotly_chart(fig, use_container_width=True)
    if "Protéines_g" in totals.index:
        fig = donut(float(totals.get("Protéines_g", 0.0)), float(profile_targets.get("proteines_g", 0.0)), "Protéines (g)", "proteines")
        cols[1].plotly_chart(fig, use_container_width=True)
    if "Glucides_g" in totals.index or "Glucides_g" in totals.index:
        fig = donut(float(totals.get("Glucides_g", 0.0)), float(profile_targets.get("glucides_g", 0.0)), "Glucides (g)", "glucides")
        cols[2].plotly_chart(fig, use_container_width=True)
    if "Lipides_g" in totals.index:
        fig = donut(float(totals.get("Lipides_g", 0.0)), float(profile_targets.get("lipides_g", 0.0)), "Lipides (g)", "lipides")
        cols[3].plotly_chart(fig, use_container_width=True)

    st.divider()
    # Micro targets table + horizontal bars if present
    targets_micro = st.session_state.get("targets_micro", pd.DataFrame()).copy()
    targets_macro = st.session_state.get("targets_macro", pd.DataFrame()).copy()

    if targets_micro is None or targets_micro.empty:
        st.info("Aucune cible micro chargée (vérifie ton fichier Excel).")
    else:
        tmi = targets_micro.copy()
        if "Objectif" not in tmi.columns or (pd.to_numeric(tmi["Objectif"], errors="coerce").fillna(0.0) == 0).all():
            tmi["Objectif"] = build_objectif_robuste(tmi)
        def consumed_micro(r):
            name, unit = parse_name_unit(str(r["Nutriment"]))
            key = f"{name}_{normalize_unit(unit)}".replace(" ","_")
            if isinstance(totals, pd.Series) and key in totals.index and pd.notna(totals[key]): return float(totals[key])
            for idx in totals.index:
                if canon_key(idx) == canon_key(key): return float(totals[idx])
            return 0.0
        tmi["Consommée"] = tmi.apply(consumed_micro, axis=1)
        tmi["Objectif"]  = tmi["Objectif"].apply(round1)
        tmi["Consommée"] = tmi["Consommée"].apply(round1)
        tmi["% objectif"]= percent(tmi["Consommée"], tmi["Objectif"]).apply(round1)

        def is_vitamin(n: str) -> bool:
            n = strip_accents(n).lower(); return n.startswith("vit") or "vitamine" in n
        vit = tmi[tmi["Nutriment"].astype(str).apply(is_vitamin)].copy()
        mino= tmi[~tmi["Nutriment"].astype(str).apply(is_vitamin)].copy()
        if not vit.empty:  vit  = vit.sort_values("% objectif", ascending=False)
        if not mino.empty: mino = mino.sort_values("% objectif", ascending=False)

        def pct_color(p):
            if pd.isna(p): return COLORS["warn"]
            if p < 50: return COLORS["bad"]
            if p < 100: return COLORS["warn"]
            return COLORS["ok"]

        def micro_bar(df: pd.DataFrame, title: str):
            if df.empty: st.info(f"Aucune donnée pour {title.lower()}."); return
            df = df.copy()
            xmax = float(max((df["Objectif"].max(), df["Consommée"].max()), default=0.0)) * 1.15 or 1.0
            height = max(320, int(24*len(df)) + 110)
            fig = go.Figure()
            fig.add_bar(y=df["Nutriment"], x=df["Objectif"], name="Objectif", orientation="h",
                        marker_color=COLORS["objectif"], opacity=0.30, hovertemplate="Objectif: %{x:.1f}<extra></extra>")
            fig.add_bar(y=df["Nutriment"], x=df["Consommée"], name="Ingéré", orientation="h",
                        marker_color=[pct_color(v) for v in df["% objectif"]],
                        text=[f"{c:.1f}/{o:.1f} ({p:.0f}%)" for c,o,p in zip(df["Consommée"], df["Objectif"], df["% objectif"])],
                        hovertemplate="%{y}: %{x:.1f}<extra></extra>")
            fig.update_layout(barmode='overlay', margin=dict(l=0,r=0,t=32,b=0), height=height, showlegend=False,
                              xaxis=dict(range=[0, xmax]), font=dict(color=COLORS["ink"]), paper_bgcolor="#ffffff",
                              plot_bgcolor="#ffffff")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Vitamines")
        micro_bar(vit, "Vitamines")
        st.markdown("#### Minéraux / autres")
        micro_bar(mino, "Minéraux")

# ============ Conseils / Tips ============
def generate_contextual_tips(profile: dict, totals: pd.Series):
    tips = []
    if isinstance(totals, pd.Series) and not totals.empty:
        if totals.get("Fibres_g", 0) < 25:
            tips.append("Augmente les fibres : privilégie légumes, légumineuses et fruits entiers.")
        if totals.get("Protéines_g", 0) < profile.get("poids_kg", 70) * 1.1:
            tips.append("Augmente légèrement ton apport en protéines (sources maigres/complètes).")
    # generic pool
    pool = [
        "Bois de l'eau régulièrement.",
        "Privilégie les aliments peu transformés.",
        "Fais attention aux portions de fruits secs et huiles (caloriques).",
        "Prépare des repas à l'avance pour mieux tenir tes objectifs.",
    ]
    random.shuffle(pool)
    chosen = pool[:3]
    motiv_pool = [
        "Petit pas : remplacer un snack transformé par un fruit.",
        "Chaque repas est une nouvelle opportunité pour te sentir mieux aujourd'hui.",
        "Petit conseil : célèbre tes petites victoires (un repas équilibré = une victoire).",
        "Rappelle-toi : le progrès est progressif — sois gentil·le avec toi-même.",
    ]
    random.shuffle(motiv_pool)
    chosen_motiv = motiv_pool[:3]
    return chosen + tips, chosen_motiv

def render_conseils_page():
    st.subheader("💡 Conseils")
    # contexte
    last_date = fetch_last_date_with_rows() or dt.date.today().isoformat()
    totals = unify_totals_for_date(last_date)
    profile_targets = st.session_state.get("profile_targets", get_profile_targets_cached())
    # generate dynamic, context-aware tips + motivations
    tips, motivs = generate_contextual_tips(st.session_state["profile"], totals)
    # show a prominent dynamic advice card (varies at each page render)
    st.markdown("### Conseil rapide")
    with st.container():
        # big highlighted box
        if tips:
            st.success("💡 " + tips[0])
        else:
            st.success("💡 Continue comme ça — petit à petit, tu atteindras tes objectifs !")
    st.divider()
    # motivations (varient)
    st.markdown("### Motivation du jour")
    for m in motivs:
        st.info("✨ " + m)

    st.divider()
    # conseils pratiques (liste)
    st.markdown("### Conseils pratiques & naturopathiques")
    for t in tips:
        st.write("• " + t)

    st.divider()
    # conserve les cartes macro / micro si disponibles (valeur ajoutée)
    targets_macro = st.session_state.get("targets_macro", pd.DataFrame()).copy()
    targets_micro = st.session_state.get("targets_micro", pd.DataFrame()).copy()

    def show_cards(df: pd.DataFrame, title: str, default_emoji: str):
        st.markdown(f"#### {title}")
        if df.empty:
            st.info("Données non disponibles (vérifie l’onglet Excel)."); return
        cols = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé"] if c in df.columns]
        data = df[cols].copy()
        # Cartes
        st.markdown('<div class="cards">', unsafe_allow_html=True)
        for _, r in data.iterrows():
            name = str(r.get("Nutriment","")).strip()
            icon = str(r.get("Icône","") or default_emoji).strip() or default_emoji
            role = str(r.get("Fonction","")).strip()
            benef = str(r.get("Bénéfice Santé","")).strip()
            st.markdown(f"""
            <div class="card">
              <h4>{icon} {name}</h4>
              <div class="role">{role}</div>
              <div class="benef">{benef}</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if not targets_macro.empty:
        show_cards(targets_macro, "🌾 Macro — rôles & bénéfices", "🥗")
    if not targets_micro.empty:
        def is_vit(n:str)->bool: n=strip_accents(n).lower(); return n.startswith("vit") or "vitamine" in n
        vit = targets_micro[targets_micro["Nutriment"].astype(str).apply(is_vit)].copy()
        mino= targets_micro[~targets_micro["Nutriment"].astype(str).apply(is_vit)].copy()
        if not vit.empty:  show_cards(vit,  "🍊 Vitamines — rôles & bénéfices", "🍊")
        if not mino.empty: show_cards(mino, "🧂 Minéraux — rôles & bénéfices",   "🧂")

# ===================== Tabs =====================
tab_profile, tab_journal, tab_bilan, tab_food = st.tabs(["👤 Profil", "🧾 Journal", "📊 Bilan", "💡 Conseils"])
with tab_profile: render_profile_page()
with tab_journal: render_journal_page()
with tab_bilan:   render_bilan_page()
with tab_food:    render_conseils_page()

# ===================== Export/Import (conservé) =====================
st.markdown("### 💾 Export / Import")
cE, cI = st.columns(2)
if cE.button("📥 Exporter le journal (.xlsx)"):
    all_j = fetch_all_journal()
    if all_j.empty: st.warning("Journal vide.")
    else:
        st.download_button("Télécharger journal.xlsx", data=to_excel_bytes(all_j),
                           file_name="journal.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with cI:
    imp = st.file_uploader("Importer un journal (.xlsx)", type=["xlsx"], key="impjournal")
    if imp is not None:
        try:
            j = pd.read_excel(imp)
            required = {"date","repas","nom","quantite_g"}
            if not required.issubset(j.columns):
                st.error("Colonnes attendues : date, repas, nom, quantite_g (+ colonnes nutriments optionnelles).")
            else:
                count = 0
                for _, r in j.iterrows():
                    date_iso = str(pd.to_datetime(r["date"]).date())
                    repas = str(r["repas"]); nom = str(r["nom"]); q = float(r["quantite_g"])
                    nutr = {}
                    for c in j.columns:
                        if c in ["date","repas","nom","quantite_g"]: continue
                        val = pd.to_numeric(pd.Series([r[c]]), errors="coerce").iloc[0]
                        if pd.notna(val): nutr[c] = float(val)
                    insert_journal(date_iso, repas, nom, q, nutr); count += 1
                st.success(f"{count} lignes importées dans SQLite (totum.db).")
        except Exception as e:
            st.error(f"Import impossible : {e}")

# ===================== Diagnostic léger =====================
with st.expander("🛠️ Diagnostic (ouvrir seulement si besoin)"):
    st.write("Assets dir:", str(ASSETS_DIR), "exists:", ASSETS_DIR.exists())
    try: st.write("Assets list:", os.listdir(ASSETS_DIR) if ASSETS_DIR.exists() else "—")
    except Exception as e: st.write("Assets list error:", e)
    st.write("Excel:", str(DEFAULT_EXCEL_PATH), "exists:", DEFAULT_EXCEL_PATH.exists())
    st.write("Logo:", str(DEFAULT_LOGO_PATH), "exists:", DEFAULT_LOGO_PATH.exists())
    dflt = dt.date.today().isoformat(); last = fetch_last_date_with_rows() or dflt
    st.write("Dernière date avec lignes:", last)
    df_dbg = fetch_journal_by_date(last)
    if df_dbg is not None and not df_dbg.empty:
        st.write("Colonnes du journal (dernier jour):", list(df_dbg.columns))
        # colonnes candidates ALA
        def _find_ala_columns_in(cols):
            out = []
            for c in cols:
                ck = canon_key(c)
                if "epa" in ck or "dha" in ck: continue
                if ("ala" in ck and ("omega3" in ck or "w3" in ck)) or ("alpha" in ck and "linolen" in ck) \
                   or ck.endswith("alag") or ck.endswith("ala") or "acidealphalinoleniquew3" in ck:
                    out.append(c)
            return out
        ala_cols = _find_ala_columns_in(df_dbg.columns.tolist())
        st.write("ALA colonnes détectées:", ala_cols if ala_cols else "—")
        if ala_cols:
            s = pd.DataFrame(df_dbg[ala_cols]).apply(pd.to_numeric, errors="coerce").fillna(0.0)
            st.write("Somme ALA (débug):", float(s.sum(numeric_only=True).sum()))
    st.write("Build:", VERSION)

# ============ Footer / version ============
st.markdown(f"<div style='opacity:.5;font-size:12px;margin-top:8px;'>Totum — version {VERSION}</div>", unsafe_allow_html=True)
