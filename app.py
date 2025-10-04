# Totum — Suivi nutritionnel
# Build visuel : Hero branding + tabs stylés + logique métier conservée

from __future__ import annotations
import os, io, re, json, sqlite3, unicodedata, datetime as dt, base64
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import openpyxl

VERSION = "v2025-10-04-hero-ui-01"

st.set_page_config(
    page_title="Totum, suivi nutritionnel",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = os.path.join(os.getcwd(), "totum.db")

# === Assets packagés (logo + Excel)
ASSETS_DIR = Path(__file__).parent / "assets"
DEFAULT_EXCEL_PATH = ASSETS_DIR / "TOTUM-Suivi nutritionnel.xlsx"
DEFAULT_LOGO_PATH  = ASSETS_DIR / "logo.png"

# ============ Utils ============
def strip_accents(text: str) -> str:
    text = str(text or "")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

def canon(s: str) -> str:
    s = strip_accents(str(s)).lower().replace("_", " ").replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()

def canon_key(s: str) -> str:
    return canon(s).replace("(", "").replace(")", "").replace("’", "'").replace(" ", "").replace("__", "_")

def norm(s: str) -> str:
    s = strip_accents(str(s)).lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

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

def per100_to_name(c):  # "Calcium_mg_100g" -> "Calcium_mg"
    return c[:-5]

def drop_parasite_columns(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty: return df
    cols = []
    for c in df.columns:
        sc = str(c).strip()
        if sc == "" or sc.lower().startswith("unnamed") or sc.lower() in {"done", "none", "nan"}:
            continue
        cols.append(c)
    out = df[cols]
    out = out.loc[:, ~(out.isna().all())]
    return out

def read_sheet_values(uploaded_file, sheet_name) -> pd.DataFrame | None:
    try:
        data_bytes = uploaded_file.getvalue()
    except Exception:
        uploaded_file.seek(0); data_bytes = uploaded_file.read()
    bio = io.BytesIO(data_bytes)
    try:
        wb = openpyxl.load_workbook(bio, data_only=True, read_only=True)
        if sheet_name not in wb.sheetnames: return None
        ws = wb[sheet_name]; data = list(ws.values)
        if not data: return None
        header = [str(x) if x is not None else "" for x in data[0]]
        df = pd.DataFrame(data[1:], columns=header)
        return drop_parasite_columns(df)
    except Exception:
        try:
            bio.seek(0)
            xls = pd.ExcelFile(bio, engine="openpyxl")
            return drop_parasite_columns(xls.parse(sheet_name))
        except Exception:
            return None

def read_sheet_values_path(path: Path, sheet_name: str) -> pd.DataFrame | None:
    try:
        with open(path, "rb") as f:
            data = f.read()
        bio = io.BytesIO(data)
        wb = openpyxl.load_workbook(bio, data_only=True, read_only=True)
        if sheet_name not in wb.sheetnames:
            return None
        ws = wb[sheet_name]
        rows = list(ws.values)
        if not rows:
            return None
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
    "energie":   "#ff7f3f",  # brand orange
    "proteines": "#2ca02c",
    "glucides":  "#1f77b4",
    "lipides":   "#d62728",
    "fibres":    "#9467bd",
    "omega3":    "#00bcd4",
    "epa":       "#26a69a",
    "dha":       "#7e57c2",
    "omega6":    "#ffb300",
    "omega9":    "#8d6e63",
    "restant":   "#e0e0e0",
    "objectif":  "#bdbdbd",
    "ok":        "#5cb85c",
    "warn":      "#f0ad4e",
    "bad":       "#d9534f",
}

# ============ Mobile UI helpers ============
def apply_mobile_css(is_mobile: bool, ultra: bool):
    scale = 0.95 if is_mobile else 1.0
    st.markdown(f"""
    <style>
    :root {{
      --brand: #ff7f3f;
      --brand2: #ffb347;
      --ink: #0d1b1e;
      --muted: #5f6b76;
      --bg1: #fffaf5;
      --bg2: #fff5ea;
      --shadow: 0 8px 26px rgba(0,0,0,.08);
      --scale: {scale};
    }}
    html, body, [data-testid="stAppViewContainer"] {{
      font-size: calc(16px * var(--scale));
      background: linear-gradient(180deg, var(--bg1) 0%, var(--bg2) 80%);
    }}
    .block-container {{ padding-top: {0.6 if ultra else 0.9}rem; padding-bottom: {0.6 if ultra else 0.9}rem; }}
    h1, h2, h3 {{ line-height: 1.15; margin: 0.15rem 0 0.5rem 0; color: var(--ink); }}

    /* HERO band */
    .hero-band {{
      background: radial-gradient(1200px 450px at 10% -10%, rgba(255,127,63,.18), transparent 60%),
                  linear-gradient(135deg, #fff0e5 0%, #fffaf6 40%, #ffffff 100%);
      border: 1px solid rgba(0,0,0,.06);
      border-radius: 18px;
      padding: {0.9 if ultra else 1.1}rem 1.2rem;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }}
    .hero-content {{ display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .9rem; }}
    .hero-title {{ font-size: clamp(22px, 2.6vw, 30px); font-weight: 800; color: var(--ink); margin: 0; }}
    .hero-sub   {{ color: var(--muted); margin-top: -2px; }}
    .hero-logo {{ display:block; aspect-ratio:1/1; object-fit:contain; filter: drop-shadow(0 8px 18px rgba(255,127,63,.35)); }}
    .hero-pill {{ background: rgba(255,127,63,.10); color:#a64b00; padding:.25rem .6rem; border-radius:999px; font-weight:700; font-size:.85rem; }}

    /* Tabs (top) */
    [data-baseweb="tab-list"] button {{
      background: #fff;
      border-radius: 10px !important;
      margin-right: .3rem;
      box-shadow: 0 2px 10px rgba(0,0,0,.04);
      border: 1px solid rgba(0,0,0,.06);
    }}
    [data-baseweb="tab"] {{
      padding: .4rem .8rem !important;
      font-weight: 600;
    }}
    [data-baseweb="tab-highlight"] {{ background: linear-gradient(90deg, var(--brand), var(--brand2)); height: 3px; }}

    /* DataFrames */
    [data-testid="stDataFrame"] div {{ font-size: {0.92 if ultra else 0.96}em; }}
    .stPlotlyChart {{ height: auto; }}

    /* Buttons */
    .stButton>button {{
      background: linear-gradient(90deg, var(--brand), var(--brand2));
      border: 0;
      color: #fff;
      font-weight: 700;
      box-shadow: 0 6px 16px rgba(255,127,63,.28);
    }}

    /* Donut titles */
    .donut-title {{ font-size: {13 if ultra else 14}px; font-weight: 700; margin-bottom: 0.15rem; color: var(--ink); }}
    </style>
    """, unsafe_allow_html=True)

def short_title(label_long: str, label_short: str, is_mobile: bool) -> str:
    return label_short if is_mobile else label_long

def round1(x) -> float:
    try:
        return float(np.round(float(x), 1))
    except Exception:
        return 0.0

def donut(cons, target, title, color_key="energie", height=210):
    cons = float(cons or 0.0); target = float(target or 0.0)
    if target <= 0:
        fig = go.Figure(data=[go.Pie(values=[1], labels=["Objectif manquant"], hole=0.68,
                                     textinfo="label", marker_colors=[COLORS["objectif"]])])
        fig.update_layout(title=title, margin=dict(l=0, r=0, t=34, b=0), height=height, showlegend=False,
                          font=dict(size=13))
        return fig
    pct = 0.0 if target == 0 else (cons / target * 100.0)
    if pct < 50: wedge = COLORS["bad"]
    elif pct < 100: wedge = COLORS["warn"]
    else: wedge = COLORS["ok"]
    rest = max(target - cons, 0.0)
    fig = go.Figure(data=[
        go.Pie(values=[cons, rest], labels=["Ingéré", "Restant"], hole=0.70, textinfo="none",
               marker_colors=[wedge, COLORS["restant"]])
    ])
    fig.update_layout(
        title=title,
        annotations=[dict(text=f"{cons:.1f}/{target:.1f}<br>({pct:.0f}%)", x=0.5, y=0.5, showarrow=False, font=dict(size=15))],
        margin=dict(l=0, r=0, t=32, b=0), height=height, showlegend=False, font=dict(size=13)
    )
    return fig

# ============ Unification noms totaux ============
PREFERRED_NAMES = {
    "energiekcal": "Énergie_kcal",
    "proteinesg":  "Protéines_g",
    "glucidesg":   "Glucides_g",
    "lipidesg":    "Lipides_g",
    "fibresg":     "Fibres_g",
    "agsaturesg":  "AG_saturés_g",
    "acideoleiquew9g":           "Acide_oléique_W9_g",
    "acidelinoleiquew6lag":      "Acide_linoléique_W6_LA_g",
    "acidealphalinoleniquew3alag":"Acide_alpha-linolénique_W3_ALA_g",
    "acidealpha-linoléniquew3alag":"Acide_alpha-linolénique_W3_ALA_g",
    "acidealpha_linolenique_w3_alag":"Acide_alpha-linolénique_W3_ALA_g",
    "epag": "EPA_g", "dhag": "DHA_g",
    "sucresg":"Sucres_g", "selg":"Sel_g", "cholesterolmg":"Cholestérol_mg",
    "omega3g": "Omega3_g", "omega3totalg": "Omega3_total_g", "w3totalg":"W3_total_g",
}

def unify_totals_series(s: pd.Series) -> pd.Series:
    if not isinstance(s, pd.Series) or s.empty:
        return s
    buckets: dict[str, float] = {}
    name_for_bucket: dict[str, str] = {}
    for col in s.index:
        key = canon_key(col)
        preferred = PREFERRED_NAMES.get(key)
        bucket = preferred or key
        buckets[bucket] = buckets.get(bucket, 0.0) + float(s[col] or 0.0)
        if preferred:
            name_for_bucket[bucket] = preferred
        else:
            name_for_bucket.setdefault(bucket, col)
    out = pd.Series({name_for_bucket[k]: v for k, v in buckets.items()})
    if "Énergie_kcal" not in out.index and "Energie_kcal" in out.index:
        out["Énergie_kcal"] = out["Energie_kcal"]
    return out

# ============ Profil / objectifs ============
def bmr_harris_benedict_revised(sex, age, height_cm, weight_kg):
    if norm(sex).startswith("h"):  # homme
        return 88.362 + 13.397*float(weight_kg) + 4.799*float(height_cm) - 5.677*int(age)
    else:
        return 447.593 + 9.247*float(weight_kg) + 3.098*float(height_cm) - 4.330*int(age)

ACTIVITY_TABLE = {
    "sedentaire":   {"factor": 1.2,   "prot_min": 0.8, "prot_max": 1.0},
    "leger":        {"factor": 1.375, "prot_min": 1.0, "prot_max": 1.2},
    "modere":       {"factor": 1.55,  "prot_min": 1.2, "prot_max": 1.6},
    "intense":      {"factor": 1.725, "prot_min": 1.6, "prot_max": 2.0},
    "tresintense":  {"factor": 1.9,   "prot_min": 2.0, "prot_max": 2.5},
    "athlete":      {"factor": 1.9,   "prot_min": 2.0, "prot_max": 2.5},
}

def activity_key(a: str) -> str:
    a = norm(a)
    if "sedentaire" in a: return "sedentaire"
    if "leger" in a or "13x" in a: return "leger"
    if "modere" in a or "35x" in a: return "modere"
    if "intense" in a and "tres" not in a and "2x" not in a: return "intense"
    if "tresintense" in a or "2x" in a or "athlete" in a: return "tresintense"
    return "sedentaire"

RULES = {
    "lipides_pct": 0.35,
    "agsat_pct":   0.10,
    "omega9_pct":  0.15,
    "omega6_pct":  0.04,
    "ala_pct":     0.01,
    "glucides_pct":0.55,
    "sucres_pct":  0.10,
    "fibres_g":    30.0,
    "epa_g":       0.25,
    "dha_g":       0.25,
    "sel_g":       6.0,
}

def excel_like_targets(p: dict) -> dict:
    bmr = bmr_harris_benedict_revised(p["sexe"], int(p["age"]), float(p["taille_cm"]), float(p["poids_kg"]))
    akey = activity_key(p["activite"])
    af = ACTIVITY_TABLE[akey]["factor"]
    prot_max = ACTIVITY_TABLE[akey]["prot_max"]
    tdee = bmr * af
    out = {}
    out["energie_kcal"] = float(tdee)
    out["proteines_g"]  = float(float(p["poids_kg"]) * prot_max)
    out["lipides_g"]    = float(tdee * RULES["lipides_pct"] / 9.0)
    out["agsatures_g"]  = float(tdee * RULES["agsat_pct"]   / 9.0)
    out["omega9_g"]     = float(tdee * RULES["omega9_pct"]  / 9.0)
    out["omega6_g"]     = float(tdee * RULES["omega6_pct"]  / 9.0)
    out["ala_w3_g"]     = float(tdee * RULES["ala_pct"]     / 9.0)
    out["epa_g"]        = RULES["epa_g"]
    out["dha_g"]        = RULES["dha_g"]
    out["glucides_g"]   = float(tdee * RULES["glucides_pct"]/ 4.0)
    out["sucres_g"]     = float(tdee * RULES["sucres_pct"]  / 4.0)
    out["fibres_g"]     = RULES["fibres_g"]
    out["sel_g"]        = RULES["sel_g"]
    return out

def get_profile_targets_cached() -> dict:
    p = st.session_state["profile"]
    base = excel_like_targets(p)
    prof = {
        "energie_kcal": round1(base["energie_kcal"]),
        "proteines_g":  round1(base["proteines_g"]),
        "glucides_g":   round1(base["glucides_g"]),
        "lipides_g":    round1(base["lipides_g"]),
        "fibres_g":     round1(base["fibres_g"]),
        "sucres_g":     round1(base["sucres_g"]),
        "agsatures_g":  round1(base["agsatures_g"]),
        "omega9_g":     round1(base["omega9_g"]),
        "omega6_g":     round1(base["omega6_g"]),
        "ala_w3_g":     round1(base["ala_w3_g"]),
        "epa_g":        round1(base["epa_g"]),
        "dha_g":        round1(base["dha_g"]),
        "sel_g":        round1(base["sel_g"]),
    }
    st.session_state["profile_targets"] = prof
    return prof

# ============ SQLite ============
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id=1),
            sexe TEXT, age INTEGER, taille_cm REAL, poids_kg REAL,
            activite TEXT, prot_pct INTEGER, gluc_pct INTEGER, lip_pct INTEGER
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            repas TEXT NOT NULL,
            nom TEXT NOT NULL,
            quantite_g REAL NOT NULL,
            nutrients_json TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn

def load_profile():
    conn = init_db()
    cur = conn.execute("SELECT sexe,age,taille_cm,poids_kg,activite,prot_pct,gluc_pct,lip_pct FROM profile WHERE id=1;")
    row = cur.fetchone()
    if row:
        return {"sexe":row[0],"age":row[1],"taille_cm":row[2],"poids_kg":row[3],
                "activite":row[4],"repartition_macros":(row[5],row[6],row[7])}
    return {"sexe":"Homme","age":40,"taille_cm":181.0,"poids_kg":72.0,"activite":"Sédentaire","repartition_macros":(30,55,15)}

def save_profile(p):
    conn = init_db()
    conn.execute("""
        INSERT INTO profile (id,sexe,age,taille_cm,poids_kg,activite,prot_pct,gluc_pct,lip_pct)
        VALUES (1,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            sexe=excluded.sexe, age=excluded.age, taille_cm=excluded.taille_cm, poids_kg=excluded.poids_kg,
            activite=excluded.activite, prot_pct=excluded.prot_pct, gluc_pct=excluded.gluc_pct, lip_pct=excluded.lip_pct;
    """, (p["sexe"], int(p["age"]), float(p["taille_cm"]), float(p["poids_kg"]),
          p["activite"], int(p["repartition_macros"][0]), int(p["repartition_macros"][1]), int(p["repartition_macros"][2])))
    conn.commit()

def insert_journal(date_iso, repas, nom, quantite_g, nutrients: dict):
    conn = init_db()
    conn.execute("INSERT INTO journal (date,repas,nom,quantite_g,nutrients_json) VALUES (?,?,?,?,?)",
                 (date_iso, repas, nom, float(quantite_g), json.dumps(nutrients, ensure_ascii=False)))
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

def fetch_last_date_with_rows() -> str | None:
    conn = init_db()
    cur = conn.execute("SELECT date, COUNT(*) c FROM journal GROUP BY date ORDER BY date DESC;")
    r = cur.fetchone()
    return r[0] if r else None

# ============ Objectifs & extraction générique ============
def build_objectif_robuste(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    candidates = [c for c in ["Objectif","Ojectifs","Cible","Objectifs","Objectif (jour)","Target","Cible (jour)"] if c in df.columns]
    out = pd.Series(0.0, index=df.index, dtype=float)
    for c in candidates:
        v = coerce_num_col(df[c])
        out = out.where(out > 0, v.fillna(0.0))
    out = pd.Series([round1(x) for x in out], index=df.index, dtype=float)
    return out

def macro_base_name(label: str) -> str:
    name, _ = parse_name_unit(label)
    nc = canon(name)
    nc_nospace = nc.replace(" ", "")
    if nc.startswith("energie"): return "energie"
    if nc.startswith("proteine"): return "proteines"
    if nc.startswith("glucide"): return "glucides"
    if nc.startswith("lipide"): return "lipides"
    if nc.startswith("sucres"): return "sucres"
    if "acides grassatures" in nc or "acides gras satures" in nc or "ag satures" in nc or "agsatures" in nc: return "agsatures"
    if "omega9" in nc_nospace: return "omega9"
    if "omega6" in nc_nospace: return "omega6"
    if "oleique" in nc and "w9" in nc: return "omega9"
    if "linoleique" in nc and ("w6" in nc or "la" in nc): return "omega6"
    if "epa" in nc: return "epa"
    if "dha" in nc: return "dha"
    if "omega3" in nc_nospace or "w3" in nc_nospace or ("alpha" in nc and "linolenique" in nc) or "ala" in nc: return "ala"
    if nc.startswith("fibres"): return "fibres"
    if nc.startswith("sel"): return "sel"
    return name

# ============ Session ============
if "foods" not in st.session_state: st.session_state["foods"] = pd.DataFrame(columns=["nom"])
if "targets_micro" not in st.session_state: st.session_state["targets_micro"] = pd.DataFrame()
if "targets_macro" not in st.session_state: st.session_state["targets_macro"] = pd.DataFrame()
if "logo_bytes" not in st.session_state: st.session_state["logo_bytes"] = None
if "logo_source" not in st.session_state: st.session_state["logo_source"] = "default"  # default|upload
if "profile" not in st.session_state: st.session_state["profile"] = load_profile()
if "last_added_date" not in st.session_state: st.session_state["last_added_date"] = None
if "profile_targets" not in st.session_state: st.session_state["profile_targets"] = get_profile_targets_cached()
if "mobile" not in st.session_state: st.session_state["mobile"] = False
if "ultra" not in st.session_state: st.session_state["ultra"] = False

# -- Logo : recharge automatiquement si source = default
def _reload_default_logo():
    if DEFAULT_LOGO_PATH.exists():
        st.session_state["logo_bytes"] = DEFAULT_LOGO_PATH.read_bytes()
        st.session_state["logo_source"] = "default"

if st.session_state["logo_source"] == "default":
    _reload_default_logo()

def _logo_b64() -> str | None:
    data = st.session_state.get("logo_bytes")
    if not data and DEFAULT_LOGO_PATH.exists():
        data = DEFAULT_LOGO_PATH.read_bytes()
    if data:
        return base64.b64encode(data).decode()
    return None

# ============ HERO HEADER ============
MOBILE = st.session_state["mobile"]
ULTRA  = st.session_state["ultra"]
apply_mobile_css(MOBILE, ULTRA)

logo_b64 = _logo_b64()
logo_w = 132 if not MOBILE else (96 if not ULTRA else 88)
hero_html = f"""
<div class="hero-band">
  <div class="hero-content">
    <div>
      {"<span class='hero-pill'>Totum</span>"}
      <div class="hero-title">Suivi nutritionnel intelligent</div>
      <div class="hero-sub">Visualise tes apports, atteins tes objectifs — simplement.</div>
    </div>
    <div></div>
    <img class="hero-logo" src="data:image/png;base64,{logo_b64}" alt="Totum logo" style="width:{logo_w}px;"/>
  </div>
</div>
""" if logo_b64 else f"""
<div class="hero-band">
  <div class="hero-content">
    <div>
      <span class='hero-pill'>Totum</span>
      <div class="hero-title">Suivi nutritionnel intelligent</div>
      <div class="hero-sub">Visualise tes apports, atteins tes objectifs — simplement.</div>
    </div>
  </div>
</div>
"""
st.markdown(hero_html, unsafe_allow_html=True)
st.caption(f"Build {VERSION}")

# ============ Toolbar (petits réglages) ============
tb1, tb2, tb3, tb4 = st.columns([2,2,2,6])
with tb1:
    st.session_state["mobile"] = st.checkbox("📱 Texte compact", value=st.session_state["mobile"], key="ck_mobile")
with tb2:
    st.session_state["ultra"] = st.checkbox("📱 Ultra (2 col.)", value=st.session_state["ultra"], key="ck_ultra")
with tb3:
    if st.button("💾 Sauver profil & journal"):
        save_profile(st.session_state["profile"])
        st.success("Données sauvegardées (SQLite : totum.db)")

# ============ Sidebar : logo + source Excel + état des assets ============
with st.sidebar:
    st.header("📥 Fichiers & source des données")

    # État des assets packagés (diagnostic simple)
    colA, colB = st.columns(2)
    with colA:
        st.metric("Logo packagé", "✅" if DEFAULT_LOGO_PATH.exists() else "❌")
    with colB:
        st.metric("Excel packagé", "✅" if DEFAULT_EXCEL_PATH.exists() else "❌")
    st.caption(f"Logo: {DEFAULT_LOGO_PATH}")
    st.caption(f"Excel: {DEFAULT_EXCEL_PATH}")

    # Choix logo : upload ou par défaut (assets)
    logo_upl = st.file_uploader("Logo TOTUM (PNG/JPG)", type=["png","jpg","jpeg"])
    if logo_upl is not None:
        st.session_state["logo_bytes"] = logo_upl.read()
        st.session_state["logo_source"] = "upload"
        st.success("Logo chargé (session).")
    if st.button("♻️ Logo par défaut (assets)"):
        _reload_default_logo()
        st.success("Logo par défaut rechargé.")
        st.rerun()

    st.divider()

    # Choix de la source pour la Liste/Cibles
    data_src = st.radio(
        "Source des données (Liste + Cibles)",
        options=["Excel packagé (assets)", "Fichier uploadé"],
        index=0 if DEFAULT_EXCEL_PATH.exists() else 1,
        help="Excel packagé = assets/TOTUM-Suivi nutritionnel.xlsx dans le repo GitHub"
    )

    def _load_all_from_excel(reader_func, src):
        df_liste = reader_func(src, "Liste")
        if df_liste is not None and not df_liste.empty:
            st.session_state["foods"] = clean_liste(df_liste)

        sex = st.session_state["profile"]["sexe"]
        micro_sheet = "Cible micro Homme" if canon(sex).startswith("homme") else "Cible micro Femme"
        df_micro = reader_func(src, micro_sheet)
        if df_micro is not None and "Nutriment" in df_micro.columns:
            tm = drop_parasite_columns(df_micro.copy())
            tm["Objectif"] = build_objectif_robuste(tm)
            keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tm.columns]
            st.session_state["targets_micro"] = tm[keep]

        df_macro_raw = reader_func(src, "Cible Macro")
        if df_macro_raw is not None and "Nutriment" in df_macro_raw.columns:
            tmac = drop_parasite_columns(df_macro_raw.copy())
            tmac["Objectif"] = build_objectif_robuste(tmac)
            keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tmac.columns]
            st.session_state["targets_macro"] = tmac[keep]

    if data_src == "Fichier uploadé":
        upl = st.file_uploader("Charger votre Excel TOTUM (.xlsx)", type=["xlsx"])
        if upl:
            _load_all_from_excel(read_sheet_values, upl)
    else:
        if DEFAULT_EXCEL_PATH.exists():
            _load_all_from_excel(read_sheet_values_path, DEFAULT_EXCEL_PATH)
            st.info("Source: Excel packagé (assets).")
        else:
            st.error("Excel packagé introuvable. Placez-le dans assets/TOTUM-Suivi nutritionnel.xlsx (casse exacte).")

# ==================== Pages (moteur conservé) ====================
def render_profile_page():
    st.subheader("👤 Profil")
    p = st.session_state["profile"]
    c1, c2, c3, c4 = st.columns(4)
    p["sexe"] = c1.selectbox("Sexe", ["Homme","Femme"], index=0 if canon(p["sexe"]).startswith("homme") else 1)
    p["age"]       = int(c2.number_input("Âge",        min_value=10,  max_value=100,  value=int(p["age"]),       step=1))
    p["taille_cm"] = int(c3.number_input("Taille (cm)",min_value=120, max_value=230,  value=int(p["taille_cm"]),  step=1))
    p["poids_kg"]  = int(c4.number_input("Poids (kg)", min_value=30,  max_value=250,  value=int(p["poids_kg"]),   step=1))
    p["activite"] = st.selectbox(
        "Activité",
        ["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"],
        index=["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"].index(p["activite"])
    )
    st.caption("Répartition P/G/L affichée pour info (objectifs = Excel : 35 % L, 55 % G, Prot = g/kg).")
    cP, cG, cL = st.columns(3)
    pr = cP.slider("Protéines (%)", 0, 100, int(p["repartition_macros"][0]), 1)
    gc = cG.slider("Glucides (%)",  0, 100, int(p["repartition_macros"][1]), 1)
    lp = cL.slider("Lipides (%)",   0, 100, int(p["repartition_macros"][2]), 1)
    p["repartition_macros"] = (pr, gc, lp)
    st.session_state["profile"] = p

    if st.button("💾 Sauver le profil"):
        save_profile(p); st.success("Profil enregistré.")

    profile_targets = get_profile_targets_cached()
    prof_rows = [{
        "Énergie (kcal)": profile_targets["energie_kcal"],
        "Protéines (g)":  profile_targets["proteines_g"],
        "Glucides (g)":   profile_targets["glucides_g"],
        "Lipides (g)":    profile_targets["lipides_g"],
        "Fibres (g)":     profile_targets["fibres_g"],
        "Sucres (g)":     profile_targets["sucres_g"],
        "AG saturés (g)": profile_targets["agsatures_g"],
        "Oméga-9 (g)":    profile_targets["omega9_g"],
        "Oméga-6 (g)":    profile_targets["omega6_g"],
        "Oméga-3 (ALA) (g)": profile_targets["ala_w3_g"],
        "EPA (g)":        profile_targets["epa_g"],
        "DHA (g)":        profile_targets["dha_g"],
        "Sel (g)":        profile_targets["sel_g"],
    }]
    st.markdown("#### 🎯 Objectifs (1 déc.)")
    st.write(pd.DataFrame(prof_rows).T.rename(columns={0:"Objectif"}))

def render_journal_page():
    st.subheader("🧾 Journal")
    foods = st.session_state["foods"]
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    date_sel = c1.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY", key="date_input_journal")
    repas = c2.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"])
    qty = c3.number_input("Quantité (g)", min_value=1, value=150, step=10)
    nom = c4.selectbox("Aliment", options=foods["nom"].astype(str).tolist() if not foods.empty else ["(liste vide)"])
    if st.button("➕ Ajouter"):
        if not foods.empty and nom != "(liste vide)":
            row = foods.loc[foods["nom"] == nom]
            if not row.empty:
                row = row.iloc[0]
                calc = calc_from_food_row(row, qty)
                insert_journal(date_sel.isoformat(), repas, nom, qty, calc)
                st.session_state["last_added_date"] = date_sel.isoformat()
                st.success(f"Ajouté : {qty} g de {nom} ({repas})")
    st.markdown("### Lignes du jour")
    df_day = fetch_journal_by_date(date_sel.isoformat())
    if not df_day.empty:
        numcols = df_day.select_dtypes(include=[np.number]).columns
        df_show = df_day.copy()
        df_show[numcols] = df_show[numcols].applymap(round1)
        st.dataframe(df_show.drop(columns=["id"]), use_container_width=True)
    else:
        st.dataframe(df_day, use_container_width=True)

    if not df_day.empty:
        st.markdown("#### Supprimer une ligne")
        options = df_day[["id","repas","nom","quantite_g"]].copy()
        options["label"] = options.apply(lambda r: f'#{int(r["id"])} — {r["repas"]}: {r["nom"]} ({round1(r["quantite_g"])} g)', axis=1)
        sel_label = st.selectbox("Ligne à supprimer", options["label"].tolist())
        sel_id = int(options.loc[options["label"].eq(sel_label), "id"].iloc[0])
        if st.button("🗑️ Supprimer cette ligne"):
            delete_journal_row(sel_id)
            st.success(f"Ligne #{sel_id} supprimée.")
            st.rerun()

def unify_totals_for_date(date_iso: str) -> pd.Series:
    df_today = fetch_journal_by_date(date_iso)
    if not df_today.empty:
        base_exclude = ["id","date","repas","nom","quantite_g"]
        df_clean = drop_parasite_columns(df_today)
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
            try:
                default_bilan_date = pd.to_datetime(st.session_state["last_added_date"]).date()
            except Exception:
                default_bilan_date = pd.to_datetime(last_with).date()
        else:
            default_bilan_date = pd.to_datetime(last_with).date()

    date_bilan = st.date_input("Date", value=default_bilan_date, format="DD/MM/YYYY", key="date_bilan")
    totals = unify_totals_for_date(date_bilan.isoformat())

    targets_macro = st.session_state["targets_macro"].copy()
    targets_micro = st.session_state["targets_micro"].copy()
    profile_targets = st.session_state.get("profile_targets", get_profile_targets_cached())

    MACRO_KEYS = {
        "Énergie":   ["Énergie_kcal","Energie_kcal","kcal","energie_kcal"],
        "Protéines": ["Protéines_g","Proteines_g"],
        "Glucides":  ["Glucides_g"],
        "Lipides":   ["Lipides_g"],
        "Fibres":    ["Fibres_g","Fibre_g"],
        "Sucres":    ["Sucres_g"],
        "AG saturés":["AG_saturés_g","Acides_gras_saturés_g","AG_satures_g"],
        "Oméga-9":   ["Acide_oléique_W9_g","Acide_oleique_W9_g"],
        "Oméga-6":   ["Acide_linoléique_W6_LA_g","Acide_linoleique_W6_LA_g"],
        "Oméga-3 ALA":[
            "Acide_alpha-linolénique_W3_ALA_g","Acide_alphalinolénique_W3_ALA_g","Acide_alpha_linolenique_W3_ALA_g",
            "Omega3_ALA_g","ALA_g"
        ],
        "Omega3_total": ["Omega3_g","Omega3_total_g","Oméga-3_g","Oméga_3_g","W3_total_g"],
        "EPA":       ["EPA_g"],
        "DHA":       ["DHA_g"],
        "Sel":       ["Sel_g"],
    }

    def _any_of(keys) -> float:
        for key in keys:
            if key in totals.index and pd.notna(totals[key]):
                return float(totals[key])
        target_keys = [canon_key(k) for k in keys]
        for idx in totals.index:
            if canon_key(idx) in target_keys and pd.notna(totals[idx]):
                return float(totals[idx])
        return 0.0

    def consumed_value_for(label: str) -> float:
        if not isinstance(totals, pd.Series) or totals.empty: return 0.0
        base = macro_base_name(label)
        if base == "energie":
            p = float(totals.get("Protéines_g", totals.get("Proteines_g", 0.0)))
            g = float(totals.get("Glucides_g", 0.0))
            l = float(totals.get("Lipides_g", 0.0))
            return p*4 + g*4 + l*9
        if base == "ala":
            ala = _any_of(MACRO_KEYS["Oméga-3 ALA"])
            epa = _any_of(MACRO_KEYS["EPA"])
            dha = _any_of(MACRO_KEYS["DHA"])
            total = ala + epa + dha
            if total > 0:
                return total
            return _any_of(MACRO_KEYS.get("Omega3_total", []))
        map_name = None
        if base == "proteines": map_name = "Protéines"
        elif base == "glucides": map_name = "Glucides"
        elif base == "lipides": map_name = "Lipides"
        elif base == "fibres": map_name = "Fibres"
        elif base == "sucres": map_name = "Sucres"
        elif base == "agsatures": map_name = "AG saturés"
        elif base == "omega9": map_name = "Oméga-9"
        elif base == "omega6": map_name = "Oméga-6"
        elif base == "epa": map_name = "EPA"
        elif base == "dha": map_name = "DHA"
        elif base == "sel": map_name = "Sel"
        if map_name:
            return _any_of(MACRO_KEYS.get(map_name, []))
        if label in totals.index and pd.notna(totals[label]): return float(totals[label])
        for idx in totals.index:
            if canon_key(idx) == canon_key(label):
                return float(totals[idx])
        return 0.0

    def build_macros_df():
        p = st.session_state["profile"]
        xlt = excel_like_targets(p)
        df = targets_macro.copy()
        if df is None or df.empty or "Nutriment" not in df.columns:
            rows = [
                {"Nutriment":"Énergie (calories)-kcal","Icône":"🔥","Fonction":"Source vitale","Bénéfice Santé":"Maintien poids & vitalité"},
                {"Nutriment":"Lipides-g","Icône":"🥑","Fonction":"Énergie & hormones","Bénéfice Santé":"Cœur"},
                {"Nutriment":"AG saturés-g","Icône":"🥓","Fonction":"Énergie rapide","Bénéfice Santé":"Éviter excès"},
                {"Nutriment":"Acide_oléique_W9-g","Icône":"🫒","Fonction":"Mono-insaturé","Bénéfice Santé":"Cœur"},
                {"Nutriment":"Acide_linoléique_W6_LA-g","Icône":"🌻","Fonction":"Polyinsaturé","Bénéfice Santé":"Peau"},
                {"Nutriment":"Oméga-3 (ALA)-g","Icône":"🌱","Fonction":"Essentiel","Bénéfice Santé":"Cerveau"},
                {"Nutriment":"EPA-g","Icône":"🐟","Fonction":"Oméga-3 marin","Bénéfice Santé":"Anti-inflammatoire"},
                {"Nutriment":"DHA-g","Icône":"🧠","Fonction":"Oméga-3 marin","Bénéfice Santé":"Cerveau"},
                {"Nutriment":"Glucides-g","Icône":"🍞","Fonction":"Carburant","Bénéfice Santé":"Énergie"},
                {"Nutriment":"Sucres-g","Icône":"🍬","Fonction":"Énergie rapide","Bénéfice Santé":"Limiter"},
                {"Nutriment":"Fibres-g","Icône":"🌾","Fonction":"Digestion","Bénéfice Santé":"Métabolisme"},
                {"Nutriment":"Protéines-g","Icône":"💪","Fonction":"Construction","Bénéfice Santé":"Récup"},
                {"Nutriment":"Sel-g","Icône":"🧂","Fonction":"Sodium","Bénéfice Santé":"Équilibre"},
            ]
            df = pd.DataFrame(rows)
        if "Objectif" not in df.columns: df["Objectif"] = np.nan

        def excel_objective_for_row(nutr_label: str) -> float | None:
            base = macro_base_name(str(nutr_label))
            if base == "energie":   return xlt["energie_kcal"]
            if base == "lipides":   return xlt["lipides_g"]
            if base == "agsatures": return xlt["agsatures_g"]
            if base == "omega9":    return xlt["omega9_g"]
            if base == "omega6":    return xlt["omega6_g"]
            if base == "ala":       return xlt["ala_w3_g"]
            if base == "epa":       return xlt["epa_g"]
            if base == "dha":       return xlt["dha_g"]
            if base == "glucides":  return xlt["glucides_g"]
            if base == "sucres":    return xlt["sucres_g"]
            if base == "fibres":    return xlt["fibres_g"]
            if base == "proteines": return xlt["proteines_g"]
            if base == "sel":       return xlt["sel_g"]
            return None

        df["Objectif"] = df["Nutriment"].apply(lambda n: excel_objective_for_row(str(n)) if str(n) else np.nan)

        # Copie exacte depuis Profil pour Oméga-3 (objectif ALA)
        profile_targets = st.session_state.get("profile_targets", get_profile_targets_cached())
        is_ala_row = df["Nutriment"].apply(lambda n: macro_base_name(str(n)) == "ala")
        omega3_from_profile = float(profile_targets.get("ala_w3_g", xlt["ala_w3_g"]))
        df.loc[is_ala_row, "Objectif"] = omega3_from_profile

        df["Consommée"] = df["Nutriment"].apply(consumed_value_for)
        df["Objectif"]  = pd.to_numeric(df["Objectif"], errors="coerce").fillna(omega3_from_profile)
        df["Consommée"] = pd.to_numeric(df["Consommée"], errors="coerce").fillna(0.0)
        df["Objectif"]   = df["Objectif"].apply(round1)
        df["Consommée"]  = df["Consommée"].apply(round1)
        df["% objectif"] = percent(df["Consommée"], df["Objectif"]).apply(round1)

        for c in ["Icône","Fonction","Bénéfice Santé"]:
            if c not in df.columns: df[c] = ""
            df[c] = df[c].fillna("")
        return df

    macros_df = build_macros_df()

    def render_donuts_grid(items, cols_desktop=5, height=210):
        cfg = {"displaylogo": False, "responsive": True}
        cols = 2 if (st.session_state["mobile"] and st.session_state["ultra"]) else cols_desktop
        for i in range(0, len(items), cols):
            row_items = items[i:i+cols]
            row_cols = st.columns(len(row_items))
            for col, it in zip(row_cols, row_items):
                with col:
                    st.markdown(f"<div class='donut-title'>{it['title']}</div>", unsafe_allow_html=True)
                    fig = donut(it["cons"], it["target"], it["title"], it.get("color","energie"), height=height)
                    st.plotly_chart(fig, config=cfg, use_container_width=True)

    donut_h = 180 if (st.session_state["mobile"] and st.session_state["ultra"]) else (190 if st.session_state["mobile"] else 220)

    def donut_vals(base_label: str, df_macros: pd.DataFrame, fallback: float):
        if df_macros.empty or "Nutriment" not in df_macros.columns:
            return 0.0, round1(fallback)
        md = df_macros.copy()
        md["_base"] = md["Nutriment"].apply(macro_base_name)
        sel = md[md["_base"].eq(base_label)]
        if sel.empty:
            return 0.0, round1(fallback)
        row = sel.iloc[0]
        cons = pd.to_numeric(pd.Series([row.get("Consommée", 0)]), errors="coerce").fillna(0).iloc[0]
        obj  = pd.to_numeric(pd.Series([row.get("Objectif",  fallback)]), errors="coerce").fillna(fallback).iloc[0]
        return float(cons), round1(obj)

    xlt = excel_like_targets(st.session_state["profile"])
    title_energy   = short_title("Énergie (kcal)", "Énergie", st.session_state["mobile"])
    title_prot     = short_title("Protéines (g)",   "Prot.",   st.session_state["mobile"])
    title_gluc     = short_title("Glucides (g)",    "Gluc.",   st.session_state["mobile"])
    title_lip      = short_title("Lipides (g)",     "Lip.",    st.session_state["mobile"])
    title_fib      = short_title("Fibres (g)",      "Fibres",  st.session_state["mobile"])

    c1,t1 = donut_vals("energie",   macros_df, xlt["energie_kcal"])
    c2,t2 = donut_vals("proteines", macros_df, xlt["proteines_g"])
    c3,t3 = donut_vals("glucides",  macros_df, xlt["glucides_g"])
    c4,t4 = donut_vals("lipides",   macros_df, xlt["lipides_g"])
    c5,t5 = donut_vals("fibres",    macros_df, xlt["fibres_g"])

    st.markdown("### 🔥 Macros")
    render_donuts_grid([
        {"title": title_energy, "cons": c1, "target": t1, "color": "energie"},
        {"title": title_prot,   "cons": c2, "target": t2, "color": "proteines"},
        {"title": title_gluc,   "cons": c3, "target": t3, "color": "glucides"},
        {"title": title_lip,    "cons": c4, "target": t4, "color": "lipides"},
        {"title": title_fib,    "cons": c5, "target": t5, "color": "fibres"},
    ], cols_desktop=5, height=donut_h)

    st.markdown("### 🫒 Omégas")
    a_c,  a_t  = donut_vals("ala",    macros_df, xlt["ala_w3_g"])
    epa_c,epa_t= donut_vals("epa",    macros_df, xlt["epa_g"])
    dha_c,dha_t= donut_vals("dha",    macros_df, xlt["dha_g"])
    la_c, la_t = donut_vals("omega6", macros_df, xlt["omega6_g"])
    o9_c, o9_t = donut_vals("omega9", macros_df, xlt["omega9_g"])
    title_omega3 = short_title("Oméga-3 (objectif ALA) (g)", "Oméga-3 (ALA)", st.session_state["mobile"])
    render_donuts_grid([
        {"title": title_omega3, "cons": a_c,   "target": a_t,   "color":"omega3"},
        {"title": "EPA (g)",    "cons": epa_c, "target": epa_t, "color":"epa"},
        {"title": "DHA (g)",    "cons": dha_c, "target": dha_t, "color":"dha"},
        {"title": "Oméga-6",    "cons": la_c,  "target": la_t,  "color":"omega6"},
        {"title": "Oméga-9",    "cons": o9_c,  "target": o9_t,  "color":"omega9"},
    ], cols_desktop=5, height=donut_h)

    st.markdown("### 🧪 Micros")
    if not targets_micro.empty and "Nutriment" in targets_micro.columns:
        tmi = targets_micro.copy()
        if "Objectif" not in tmi.columns or (pd.to_numeric(tmi["Objectif"], errors="coerce").fillna(0.0) == 0).all():
            tmi["Objectif"] = build_objectif_robuste(tmi)

        def consumed_micro(r):
            name, unit = parse_name_unit(str(r["Nutriment"]))
            key = f"{name}_{normalize_unit(unit)}".replace(" ","_")
            if isinstance(totals, pd.Series) and key in totals.index and pd.notna(totals[key]):
                return float(totals[key])
            for idx in totals.index:
                if canon_key(idx) == canon_key(key):
                    return float(totals[idx])
            return 0.0

        tmi["Consommée"]  = tmi.apply(consumed_micro, axis=1)
        tmi["Objectif"]   = tmi["Objectif"].apply(round1)
        tmi["Consommée"]  = tmi["Consommée"].apply(round1)
        tmi["% objectif"] = percent(tmi["Consommée"], tmi["Objectif"]).apply(round1)

        def pct_color(p):
            if pd.isna(p): return COLORS["warn"]
            if p < 50: return COLORS["bad"]
            if p < 100: return COLORS["warn"]
            return COLORS["ok"]

        height = max(300, int((22 if (st.session_state["mobile"] and st.session_state["ultra"]) else 24)*len(tmi)) + (90 if (st.session_state["mobile"] and st.session_state["ultra"]) else 120))
        fig = go.Figure()
        fig.add_bar(
            y=tmi["Nutriment"], x=tmi["Objectif"], name="Objectif", orientation="h",
            marker_color=COLORS["objectif"], opacity=0.30,
            hovertemplate="Objectif: %{x:.1f}<extra></extra>"
        )
        fig.add_bar(
            y=tmi["Nutriment"], x=tmi["Consommée"], name="Ingéré", orientation="h",
            marker_color=[pct_color(v) for v in tmi["% objectif"]],
            text=[f"{c:.1f}/{o:.1f} ({p:.0f}%)" for c,o,p in zip(tmi["Consommée"], tmi["Objectif"], tmi["% objectif"])],
            textposition="outside", cliponaxis=False,
            hovertemplate="Ingéré: %{x:.1f}<extra></extra>"
        )
        fig.update_layout(
            barmode="overlay",
            title="Micros — objectif vs ingéré" if not st.session_state["mobile"] else "Micros",
            xaxis_title="Quantité", yaxis_title="",
            height=height, margin=dict(l=6,r=6,t=36,b=8),
            legend=dict(orientation="h", y=-0.18),
            font=dict(size=12 if (st.session_state["mobile"] and st.session_state["ultra"]) else (13 if st.session_state["mobile"] else 14))
        )
        st.plotly_chart(fig, config={"displaylogo": False, "responsive": True}, use_container_width=True)

        tmi2 = tmi.copy()
        cols = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif","Consommée","% objectif"] if c in tmi2.columns]
        st.dataframe(tmi2[cols], use_container_width=True)
    else:
        st.info("Aucune ‘Cible micro’ chargée (onglet Excel manquant ou vide).")

    st.markdown("#### ⚡ Macros (1 déc.)")
    if 'macros_df' in locals() and not macros_df.empty:
        macros_df_show = macros_df.copy()
        cols = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif","Consommée","% objectif"] if c in macros_df_show.columns]
        st.dataframe(macros_df_show[cols], use_container_width=True)
    else:
        st.info("Aucune ‘Cible Macro’ chargée. Les donuts utilisent les objectifs calculés (Excel-like).")

    st.markdown("#### Totaux par repas")
    df_today2 = fetch_journal_by_date(date_bilan.isoformat())
    if not df_today2.empty:
        per_meal = df_today2.groupby("repas")[[c for c in df_today2.columns if c not in ["id","date","repas","nom","quantite_g"]]].sum(numeric_only=True).reset_index()
        numcols = per_meal.select_dtypes(include=[np.number]).columns
        per_meal[numcols] = per_meal[numcols].applymap(round1)
        per_meal = per_meal.rename(columns={"Énergie_kcal":"Calories","Energie_kcal":"Calories"})
        st.dataframe(per_meal, use_container_width=True)
    else:
        st.caption("Aucune ligne sur cette date. Ajoute des aliments dans l’onglet Journal.")

# ============ Onglets en haut ============
tab_profile, tab_journal, tab_bilan = st.tabs(["👤 Profil", "🧾 Journal", "📊 Bilan"])
with tab_profile: render_profile_page()
with tab_journal: render_journal_page()
with tab_bilan:   render_bilan_page()

# ============ Export/Import journal ============
st.markdown("### 💾 Export / Import")
def fetch_all_journal() -> pd.DataFrame:
    conn = init_db()
    cur = conn.execute("SELECT id,date,repas,nom,quantite_g,nutrients_json FROM journal ORDER BY date, id;")
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["date","repas","nom","quantite_g"])
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

cE, cI = st.columns(2)
if cE.button("📥 Exporter le journal (.xlsx)"):
    all_j = fetch_all_journal()
    if all_j.empty:
        st.warning("Journal vide.")
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

# ============ Diagnostic ============
with st.expander("🛠️ Diagnostic (ouvrir seulement si besoin)"):
    st.write("Working dir:", os.getcwd())
    st.write("Assets dir:", str(ASSETS_DIR), "exists:", ASSETS_DIR.exists())
    try:
        st.write("Assets list:", os.listdir(ASSETS_DIR) if ASSETS_DIR.exists() else "—")
    except Exception as e:
        st.write("Assets list error:", e)
    st.write("DEFAULT_LOGO_PATH:", str(DEFAULT_LOGO_PATH), "exists:", DEFAULT_LOGO_PATH.exists())
    st.write("DEFAULT_EXCEL_PATH:", str(DEFAULT_EXCEL_PATH), "exists:", DEFAULT_EXCEL_PATH.exists())

    foods = st.session_state["foods"]
    st.write("Colonnes Liste (foods) :", list(foods.columns)[:30], "…")
    if not foods.empty:
        st.write("Exemples nutriments 100g :", [c for c in foods.columns if str(c).endswith("_100g")][:10])
    st.write("Cible Macro : colonnes :", list(st.session_state["targets_macro"].columns))
    st.write(st.session_state["targets_macro"].head(10))
    st.write("Cible Micro : colonnes :", list(st.session_state["targets_micro"].columns))
    st.write(st.session_state["targets_micro"].head(10))
