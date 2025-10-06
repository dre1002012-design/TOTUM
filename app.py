# Totum — Suivi nutritionnel
# UI header sans encadré + ALA encore plus robuste (+ diagnostic)
from __future__ import annotations
import os, io, re, json, sqlite3, unicodedata, datetime as dt, base64
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import openpyxl

VERSION = "v2025-10-06-ui-header-flat-ala-robust-02"

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

def per100_to_name(c):
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

    # fusion colonnes quasi identiques
    dup_groups = {}
    for c in [x for x in df.columns if c.endswith("_100g")]:
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
    "brand":    "#ff7f3f",   # orange Totum
    "brand2":   "#ffb347",
    "ink":      "#0d1b1e",
    "muted":    "#5f6b76",
    "energie":   "#ff7f3f",
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

# ============ Mobile-first CSS + Header plat ============
def apply_mobile_css_and_topbar(logo_b64: str | None):
    st.markdown(f"""
    <style>
    /* Cache les barres Streamlit */
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], header, footer {{
      display: none !important;
    }}

    /* Thème clair par défaut ; dark auto si device en sombre */
    :root {{
      --bg: #ffffff;
      --ink: {COLORS['ink']};
      --muted: {COLORS['muted']};
      --border: rgba(0,0,0,0);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1216; --ink: #f6f7f8; --muted: #b9c0c7; --border: rgba(255,255,255,0);
      }}
    }}

    html, body, .stApp, [data-testid="stAppViewContainer"] {{
      background: var(--bg) !important;
      color: var(--ink);
      font-size: 15.5px;
      min-height: 100vh;
    }}
    .block-container {{ padding-top: .8rem; padding-bottom: .8rem; max-width: 1100px; }}

    /* Header plat, sans encadré ni ombre */
    .topbar {{
      position: sticky; top: 0; z-index: 100;
      padding: .25rem 0 .6rem 0; margin: 0 0 .2rem 0;
      background: transparent; border: 0; box-shadow: none;
    }}
    .topbar-grid {{ display: grid; grid-template-columns: auto 1fr; align-items: center; gap: .8rem; }}
    .topbar-logo {{
      width: 120px; height: 120px; min-width: 120px;
      object-fit: contain; background: transparent; padding: 0;
      border: 0; filter: none; /* aucun relief */
    }}
    .topbar-title {{ font-weight: 900; color: var(--ink); font-size: clamp(22px, 3vw, 30px); margin: 0; line-height: 1.05; }}
    .topbar-sub {{ margin-top: .15rem; color: var(--muted); font-size: .98rem; }}

    /* Tabs larges */
    [data-baseweb="tab-list"] {{
      width: 100%;
      display: grid !important;
      grid-template-columns: 1fr 1fr 1fr 1fr;
      gap: .35rem;
      margin: .6rem 0 .2rem 0;
    }}
    [data-baseweb="tab-list"] button {{
      width: 100%;
      background: #fff; color: var(--ink);
      border-radius: 12px !important;
      border: 1px solid rgba(0,0,0,.08);
      padding: .55rem .6rem !important;
      font-weight: 800;
      box-shadow: none; /* pas de relief */
    }}
    [data-baseweb="tab-highlight"] {{ background: linear-gradient(90deg, {COLORS['brand']}, {COLORS['brand2']}); height: 3px; }}

    /* Boutons d'action — orange Totum conservé */
    .stButton>button {{
      background: linear-gradient(90deg, {COLORS['brand']}, {COLORS['brand2']});
      border: 0; color: #fff; font-weight: 900;
      box-shadow: none; /* pas de relief */
      border-radius: 12px;
    }}

    .donut-title {{ font-size: 14px; font-weight: 800; margin-bottom: 0.15rem; color: var(--ink); }}
    .dot {{ display:inline-block; width:.8em; height:.8em; border-radius:50%; margin-right:.35em; vertical-align: middle; }}
    </style>
    """, unsafe_allow_html=True)

    logo_html = f"<img class='topbar-logo' src='data:image/png;base64,{logo_b64}' alt='logo'/>" if logo_b64 else ""
    # Phrase EXACTE souhaitée + 🍊
    st.markdown(f"""
    <div class="topbar">
      <div class="topbar-grid">
        <div>{logo_html}</div>
        <div>
          <div class="topbar-title">Totum — Mange mieux, vit mieux</div>
          <div class="topbar-sub">🍊 Ton bien-être commence dans ton assiette !</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

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
                          font=dict(size=13), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
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
        margin=dict(l=0, r=0, t=32, b=0), height=height, showlegend=False, font=dict(size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

# ============ Unification totaux ============
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
    "acidealphalinoleniquew3ala":   "Acide_alpha-linolénique_W3_ALA_g",  # <== sans _g
    "omega3alag": "Acide_alpha-linolénique_W3_ALA_g",
    "omega3ala":  "Acide_alpha-linolénique_W3_ALA_g",
    "w3alag":     "Acide_alpha-linolénique_W3_ALA_g",
    "alag":       "Acide_alpha-linolénique_W3_ALA_g",
    "epag": "EPA_g", "dhag": "DHA_g",
    "sucresg":"Sucres_g", "selg":"Sel_g",
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

# ============ Chargement Excel auto ============
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

def load_assets_default():
    if not DEFAULT_EXCEL_PATH.exists():
        return
    # Liste
    df_liste = read_sheet_values_path(DEFAULT_EXCEL_PATH, "Liste")
    if df_liste is not None and not df_liste.empty:
        st.session_state["foods"] = clean_liste(df_liste)
    # Cibles micro
    sex = st.session_state["profile"]["sexe"]
    micro_sheet = "Cible micro Homme" if canon(sex).startswith("homme") else "Cible micro Femme"
    df_micro = read_sheet_values_path(DEFAULT_EXCEL_PATH, micro_sheet)
    if df_micro is not None and "Nutriment" in df_micro.columns:
        tm = drop_parasite_columns(df_micro.copy())
        tm["Objectif"] = build_objectif_robuste(tm)
        keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tm.columns]
        st.session_state["targets_micro"] = tm[keep]
    # Cibles macro
    df_macro_raw = read_sheet_values_path(DEFAULT_EXCEL_PATH, "Cible Macro")
    if df_macro_raw is not None and "Nutriment" in df_macro_raw.columns:
        tmac = drop_parasite_columns(df_macro_raw.copy())
        tmac["Objectif"] = build_objectif_robuste(tmac)
        keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tmac.columns]
        st.session_state["targets_macro"] = tmac[keep]

def macro_base_name(label: str) -> str:
    name, _ = parse_name_unit(label)
    nc = canon(name); ns = nc.replace(" ", "")
    if nc.startswith("energie"): return "energie"
    if nc.startswith("proteine"): return "proteines"
    if nc.startswith("glucide"): return "glucides"
    if nc.startswith("lipide"): return "lipides"
    if nc.startswith("sucres"): return "sucres"
    if "acides grassatures" in nc or "acides gras satures" in nc or "ag satures" in nc or "agsatures" in nc: return "agsatures"
    if "omega9" in ns: return "omega9"
    if "omega6" in ns: return "omega6"
    if "oleique" in nc and "w9" in nc: return "omega9"
    if "linoleique" in nc and ("w6" in nc or "la" in nc): return "omega6"
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
    if data:
        return base64.b64encode(data).decode()
    return None

# ===================== HEADER =====================
apply_mobile_css_and_topbar(_logo_b64())

# ===================== PAGES =====================
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
    p["repartition_macros"] = (30,55,15)
    st.session_state["profile"] = p

    if st.button("💾 Sauver mon profil"):
        save_profile(p); st.success("Profil enregistré.")

    profile_targets = get_profile_targets_cached()
    st.markdown("#### 🎯 Objectifs clés (calculés)")
    kc, pr, gl, li, fi = st.columns(5)
    kc.metric("Énergie (kcal)", f"{profile_targets['energie_kcal']:.1f}")
    pr.metric("Protéines (g)", f"{profile_targets['proteines_g']:.1f}")
    gl.metric("Glucides (g)", f"{profile_targets['glucides_g']:.1f}")
    li.metric("Lipides (g)",   f"{profile_targets['lipides_g']:.1f}")
    fi.metric("Fibres (g)",    f"{profile_targets['fibres_g']:.1f}")

def render_journal_page():
    st.subheader("🧾 Journal")
    foods = st.session_state["foods"]

    # Recherche + suggestions
    q = st.text_input("🔎 Rechercher un aliment", placeholder="Tape 2-3 lettres… (ex: poulet, riz, pomme)")
    suggestions = []
    if not foods.empty:
        base = foods["nom"].astype(str).tolist()
        suggestions = base
        if q:
            qn = canon(q)
            suggestions = [x for x in base if qn in canon(x)]
        suggestions = suggestions[:8]

    if suggestions:
        st.caption("Suggestions : clique pour pré-remplir l’ajout 👇")
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
    if q:
        qn = canon(q)
        options = [x for x in options if qn in canon(x)] or options
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
        prot100 = m1.number_input("Protéines (g/100g)", min_value=0.0, value=0.0, step=0.5)
        gluc100 = m2.number_input("Glucides (g/100g)",  min_value=0.0, value=0.0, step=0.5)
        lip100  = m3.number_input("Lipides (g/100g)",   min_value=0.0, value=0.0, step=0.5)
        fib100  = m4.number_input("Fibres (g/100g)",    min_value=0.0, value=0.0, step=0.5)
        ags100  = m5.number_input("AG saturés (g/100g)",min_value=0.0, value=0.0, step=0.5)

        n1, n2, n3 = st.columns(3)
        ala100 = n1.number_input("Oméga-3 ALA (g/100g)", min_value=0.0, value=0.0, step=0.1)
        epa100 = n2.number_input("EPA (g/100g)",         min_value=0.0, value=0.0, step=0.1)
        dha100 = n3.number_input("DHA (g/100g)",         min_value=0.0, value=0.0, step=0.1)

        o1, o2 = st.columns(2)
        o6100 = o1.number_input("Oméga-6 (LA) (g/100g)", min_value=0.0, value=0.0, step=0.1)
        o9100 = o2.number_input("Oméga-9 (oléique) (g/100g)", min_value=0.0, value=0.0, step=0.1)

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
        base_exclude = {"id","date","repas","nom","quantite_g"}
        df_clean = drop_parasite_columns(df_today).copy()
        # conversion numérique robuste
        for c in df_clean.columns:
            if c not in base_exclude:
                df_clean[c] = pd.to_numeric(df_clean[c], errors="coerce")
        df_num = df_clean.drop(columns=[c for c in base_exclude if c in df_clean.columns], errors="ignore")
        raw = df_num.sum(numeric_only=True)
        return unify_totals_series(raw)
    return pd.Series(dtype=float)

# ===== Helpers Bilan =====
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
    df_day = fetch_journal_by_date(date_bilan.isoformat())
    totals = unify_totals_for_date(date_bilan.isoformat())

    targets_macro = st.session_state["targets_macro"].copy()
    targets_micro = st.session_state["targets_micro"].copy()
    profile_targets = st.session_state.get("profile_targets", get_profile_targets_cached())

    # ---- ALA : détection ultra-robuste ----
    def _find_ala_columns_in(dfcols: list[str]) -> list[str]:
        cols = []
        for c in dfcols:
            ck = canon_key(c)
            if "epa" in ck or "dha" in ck:
                continue
            # plusieurs heuristiques
            if ("ala" in ck and ("omega3" in ck or "w3" in ck)) or \
               ("alpha" in ck and "linolen" in ck) or \
               ck.endswith("alag") or ck.endswith("ala") or \
               "acidealphalinoleniquew3" in ck:
                cols.append(c)
        return cols

    def _ala_consumed_from_day(df: pd.DataFrame, totals_series: pd.Series) -> float:
        # 1) exact (la plus propre)
        if df is not None and not df.empty and "Acide_alpha-linolénique_W3_ALA_g" in df.columns:
            return float(pd.to_numeric(df["Acide_alpha-linolénique_W3_ALA_g"], errors="coerce").fillna(0.0).sum())
        # 2) fuzzy (liste de colonnes candidates)
        if df is not None and not df.empty:
            ala_cols = _find_ala_columns_in(df.columns.tolist())
            if ala_cols:
                s = pd.DataFrame(df[ala_cols]).apply(pd.to_numeric, errors="coerce").fillna(0.0)
                return float(s.sum(numeric_only=True).sum())
        # 3) fallback totaux
        if isinstance(totals_series, pd.Series) and not totals_series.empty:
            cand = _find_ala_columns_in(list(totals_series.index))
            if cand:
                return float(pd.to_numeric(totals_series[cand], errors="coerce").fillna(0.0).sum())
            if "Acide_alpha-linolénique_W3_ALA_g" in totals_series.index:
                return float(pd.to_numeric(pd.Series([totals_series["Acide_alpha-linolénique_W3_ALA_g"]]), errors="coerce").fillna(0.0).iloc[0])
        return 0.0

    ala_from_day = _ala_consumed_from_day(df_day, totals)

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
        "EPA":       ["EPA_g"],
        "DHA":       ["DHA_g"],
        "Sel":       ["Sel_g"],
    }

    def _any_of(keys) -> float:
        for key in keys:
            if key in totals.index and pd.notna(totals[key]):
                return float(totals[key])
        keyset = [canon_key(k) for k in keys]
        for idx in totals.index:
            if canon_key(idx) in keyset and pd.notna(totals[idx]):
                return float(totals[idx])
        return 0.0

    def consumed_value_for_strict(label: str) -> float:
        base = macro_base_name(label)
        if base == "energie":
            p = float(totals.get("Protéines_g", totals.get("Proteines_g", 0.0)))
            g = float(totals.get("Glucides_g", 0.0))
            l = float(totals.get("Lipides_g", 0.0))
            return p*4 + g*4 + l*9
        if base == "ala":
            return ala_from_day
        mapping = {
            "proteines":"Protéines","glucides":"Glucides","lipides":"Lipides","fibres":"Fibres","sucres":"Sucres",
            "agsatures":"AG saturés","omega9":"Oméga-9","omega6":"Oméga-6","epa":"EPA","dha":"DHA","sel":"Sel"
        }
        if base in mapping:
            return _any_of(MACRO_KEYS.get(mapping[base], []))
        if label in totals.index and pd.notna(totals[label]): return float(totals[label])
        for idx in totals.index:
            if canon_key(idx) == canon_key(label):
                return float(totals[idx])
        return 0.0

    def build_macros_df(targets_macro: pd.DataFrame, profile_targets: dict):
        p = st.session_state["profile"]
        xlt = excel_like_targets(p)
        df = targets_macro.copy()
        if df is None or df.empty or "Nutriment" not in df.columns:
            rows = [
                {"Nutriment":"Énergie (calories)-kcal","Icône":"🔥"},
                {"Nutriment":"Lipides-g","Icône":"🥑"},
                {"Nutriment":"AG saturés-g","Icône":"🥓"},
                {"Nutriment":"Acide_oléique_W9-g","Icône":"🫒"},
                {"Nutriment":"Acide_linoléique_W6_LA-g","Icône":"🌻"},
                {"Nutriment":"Oméga-3 (ALA)-g","Icône":"🌱"},
                {"Nutriment":"EPA-g","Icône":"🐟"},
                {"Nutriment":"DHA-g","Icône":"🧠"},
                {"Nutriment":"Glucides-g","Icône":"🍞"},
                {"Nutriment":"Sucres-g","Icône":"🍬"},
                {"Nutriment":"Fibres-g","Icône":"🌾"},
                {"Nutriment":"Protéines-g","Icône":"💪"},
                {"Nutriment":"Sel-g","Icône":"🧂"},
            ]
            df = pd.DataFrame(rows)
        if "Objectif" not in df.columns: df["Objectif"] = np.nan

        def excel_objective_for_row(nutr_label: str) -> float | None:
            base = macro_base_name(str(nutr_label))
            m = {
                "energie":"energie_kcal","lipides":"lipides_g","agsatures":"agsatures_g","omega9":"omega9_g",
                "omega6":"omega6_g","ala":"ala_w3_g","epa":"epa_g","dha":"dha_g","glucides":"glucides_g",
                "sucres":"sucres_g","fibres":"fibres_g","proteines":"proteines_g","sel":"sel_g"
            }.get(base)
            return excel_like_targets(p)[m] if m else None

        df["Objectif"] = df["Nutriment"].apply(lambda n: excel_objective_for_row(str(n)) if str(n) else np.nan)
        omega3_from_profile = float(profile_targets.get("ala_w3_g", excel_like_targets(st.session_state["profile"])["ala_w3_g"]))
        is_ala_row = df["Nutriment"].apply(lambda n: macro_base_name(str(n)) == "ala")
        df.loc[is_ala_row, "Objectif"] = omega3_from_profile

        df["Consommée"] = df["Nutriment"].apply(consumed_value_for_strict)
        df["Objectif"]  = pd.to_numeric(df["Objectif"], errors="coerce").fillna(omega3_from_profile)
        df["Consommée"] = pd.to_numeric(df["Consommée"], errors="coerce").fillna(0.0)
        df["Objectif"]   = df["Objectif"].apply(round1)
        df["Consommée"]  = df["Consommée"].apply(round1)
        df["% objectif"] = percent(df["Consommée"], df["Objectif"]).apply(round1)
        for c in ["Icône"]:
            if c not in df.columns: df[c] = ""
            df[c] = df[c].fillna("")
        return df

    macros_df = build_macros_df(st.session_state["targets_macro"].copy(), profile_targets)

    def render_donuts_grid(items, cols=5, height=205):
        cfg = {"displaylogo": False, "responsive": True, "staticPlot": True}
        for i in range(0, len(items), cols):
            row_items = items[i:i+cols]
            row_cols = st.columns(len(row_items))
            for col, it in zip(row_cols, row_items):
                with col:
                    st.markdown(f"<div class='donut-title'>{it['title']}</div>", unsafe_allow_html=True)
                    fig = donut(it["cons"], it["target"], it["title"], it.get("color","energie"), height=height)
                    st.plotly_chart(fig, config=cfg, use_container_width=True)

    # === Macros
    st.markdown("### 🌾 Macros principaux")
    def val_pair(base_name, fallback):
        md = macros_df.copy()
        md["_base"] = md["Nutriment"].apply(macro_base_name)
        sel = md[md["_base"].eq(base_name)]
        if sel.empty: return 0.0, fallback
        row = sel.iloc[0]
        cons = pd.to_numeric(pd.Series([row.get("Consommée", 0)]), errors="coerce").fillna(0).iloc[0]
        obj  = pd.to_numeric(pd.Series([row.get("Objectif",  fallback)]), errors="coerce").fillna(fallback).iloc[0]
        return float(cons), round1(obj)

    xlt = excel_like_targets(st.session_state["profile"])
    c1,t1 = val_pair("energie",   xlt["energie_kcal"])
    c2,t2 = val_pair("proteines", xlt["proteines_g"])
    c3,t3 = val_pair("glucides",  xlt["glucides_g"])
    c4,t4 = val_pair("lipides",   xlt["lipides_g"])
    c5,t5 = val_pair("fibres",    xlt["fibres_g"])

    render_donuts_grid([
        {"title": "Énergie (kcal)", "cons": c1, "target": t1, "color": "energie"},
        {"title": "Protéines (g)",  "cons": c2, "target": t2, "color": "proteines"},
        {"title": "Glucides (g)",   "cons": c3, "target": t3, "color": "glucides"},
        {"title": "Lipides (g)",    "cons": c4, "target": t4, "color": "lipides"},
        {"title": "Fibres (g)",     "cons": c5, "target": t5, "color": "fibres"},
    ])

    # === Acides gras essentiels
    st.markdown("### 🫒 Acides gras essentiels")
    def donut_vals(base_label: str, fallback: float):
        if macros_df.empty or "Nutriment" not in macros_df.columns:
            return 0.0, round1(fallback)
        md = macros_df.copy()
        md["_base"] = md["Nutriment"].apply(macro_base_name)
        sel = md[md["_base"].eq(base_label)]
        if sel.empty: return 0.0, round1(fallback)
        row = sel.iloc[0]
        cons = pd.to_numeric(pd.Series([row.get("Consommée", 0)]), errors="coerce").fillna(0).iloc[0]
        obj  = pd.to_numeric(pd.Series([row.get("Objectif",  fallback)]), errors="coerce").fillna(fallback).iloc[0]
        return float(cons), round1(obj)

    a_c,  a_t  = donut_vals("ala",    xlt["ala_w3_g"])
    epa_c,epa_t= donut_vals("epa",    xlt["epa_g"])
    dha_c,dha_t= donut_vals("dha",    xlt["dha_g"])
    la_c, la_t = donut_vals("omega6", xlt["omega6_g"])
    o9_c, o9_t = donut_vals("omega9", xlt["omega9_g"])

    render_donuts_grid([
        {"title": "Oméga-3 (ALA)", "cons": a_c,   "target": a_t,   "color":"omega3"},
        {"title": "EPA (g)",       "cons": epa_c, "target": epa_t, "color":"epa"},
        {"title": "DHA (g)",       "cons": dha_c, "target": dha_t, "color":"dha"},
        {"title": "Oméga-6 (g)",   "cons": la_c,  "target": la_t,  "color":"omega6"},
        {"title": "Oméga-9 (g)",   "cons": o9_c,  "target": o9_t,  "color":"omega9"},
    ])

    # === À surveiller
    st.markdown("### ⚠️ À surveiller")
    sugars_c, sugars_t   = val_pair("sucres",    xlt["sucres_g"])
    agsat_c,  agsat_t    = val_pair("agsatures", xlt["agsatures_g"])
    sel_c,    sel_t      = val_pair("sel",       xlt["sel_g"])
    render_donuts_grid([
        {"title": "Sucres (g)",       "cons": sugars_c, "target": sugars_t, "color":"glucides"},
        {"title": "AG saturés (g)",   "cons": agsat_c,  "target": agsat_t,  "color":"lipides"},
        {"title": "Sel (g)",          "cons": sel_c,    "target": sel_t,    "color":"muted"},
    ], cols=3, height=200)

    # ===== Micros
    st.caption(f"<span class='dot' style='background:{COLORS['ok']}'></span>Objectif atteint  "
               f"<span class='dot' style='background:{COLORS['warn']}'></span>En cours  "
               f"<span class='dot' style='background:{COLORS['bad']}'></span>Insuffisant",
               unsafe_allow_html=True)

    if targets_micro.empty or "Nutriment" not in targets_micro.columns:
        st.info("Aucune ‘Cible micro’ chargée.")
        return

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

    def is_vitamin(n: str) -> bool:
        n = strip_accents(n).lower()
        return n.startswith("vit") or "vitamine" in n

    vit = tmi[tmi["Nutriment"].astype(str).apply(is_vitamin)].copy()
    mino= tmi[~tmi["Nutriment"].astype(str).apply(is_vitamin)].copy()

    if not vit.empty:
        vit = vit.sort_values("% objectif", ascending=False)
    if not mino.empty:
        mino = mino.sort_values("% objectif", ascending=False)

    def pct_color(p):
        if pd.isna(p): return COLORS["warn"]
        if p < 50: return COLORS["bad"]
        if p < 100: return COLORS["warn"]
        return COLORS["ok"]

    def micro_bar(df: pd.DataFrame, title: str):
        if df.empty:
            st.info(f"Aucune donnée pour {title.lower()}.")
            return
        df = df.copy()
        xmax = float(max((df["Objectif"].max(), df["Consommée"].max()), default=0.0)) * 1.15 or 1.0
        height = max(320, int(24*len(df)) + 110)
        fig = go.Figure()
        fig.add_bar(
            y=df["Nutriment"], x=df["Objectif"], name="Objectif", orientation="h",
            marker_color=COLORS["objectif"], opacity=0.30,
            hovertemplate="Objectif: %{x:.1f}<extra></extra>"
        )
        fig.add_bar(
            y=df["Nutriment"], x=df["Consommée"], name="Ingéré", orientation="h",
            marker_color=[pct_color(v) for v in df["% objectif"]],
            text=[f"{c:.1f}/{o:.1f} ({p:.0f}%)" for c,o,p in zip(df["Consommée"], df["Objectif"], df["% objectif"])],
            textposition="outside", cliponaxis=False,
            hovertemplate="Ingéré: %{x:.1f}<extra></extra>"
        )
        fig.update_layout(
            barmode="overlay",
            title=title,
            xaxis_title="", yaxis_title="",
            xaxis=dict(range=[0, xmax]),
            height=height, margin=dict(l=6,r=6,t=36,b=8),
            legend=dict(orientation="h", y=-0.18),
            font=dict(size=13),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig, config={"displaylogo": False, "responsive": True, "staticPlot": True}, use_container_width=True)

    st.markdown("### 🍊 Vitamines")
    micro_bar(vit,  "Vitamines — objectif vs ingéré")

    st.markdown("### 🧂 Minéraux")
    micro_bar(mino, "Minéraux — objectif vs ingéré")

# ===================== Onglet 4 — Alimentation =====================
def render_alimentation_page():
    st.subheader("🍽️ Alimentation")

    # Conseil du jour
    last_date = fetch_last_date_with_rows() or dt.date.today().isoformat()
    totals = unify_totals_for_date(last_date)
    prof = st.session_state.get("profile_targets", get_profile_targets_cached())

    def pct(cons, key):
        c = float(cons or 0.0); t = float(prof.get(key, 0.0) or 0.0)
        return 0.0 if t == 0 else c/t*100.0

    sug = float(totals.get("Sucres_g", 0.0))
    ags = float(totals.get("AG_saturés_g", totals.get("AG_satures_g", 0.0)))
    fib = float(totals.get("Fibres_g", 0.0))

    tips = []
    if pct(sug,"sucres_g") >= 110: tips.append("Réduis les boissons sucrées : vise eau/thé/café non sucré au prochain repas.")
    elif pct(sug,"sucres_g") >= 80: tips.append("Proche de la limite de sucres : opte pour un dessert fruité entier.")
    if pct(ags,"agsatures_g") >= 110: tips.append("Trop d’AG saturés : remplace le beurre par l’huile d’olive.")
    elif pct(ags,"agsatures_g") >= 80: tips.append("Attention AG saturés : préfère poisson/volaille à la charcuterie.")
    if pct(fib,"fibres_g") < 60: tips.append("Boost fibres : ajoute légumes verts ou légumineuses au repas suivant.")
    if not tips: tips = ["Belle journée d’équilibre 🎯 Continue sur cette lancée !"]
    idx = dt.date.today().day % len(tips)
    st.success("💡 " + tips[idx])

    st.divider()

    # Tables issues Excel
    targets_macro = st.session_state.get("targets_macro", pd.DataFrame()).copy()
    targets_micro = st.session_state.get("targets_micro", pd.DataFrame()).copy()

    def show_excel_table(df: pd.DataFrame, title: str):
        st.markdown(f"#### {title}")
        if df.empty:
            st.info("Données non disponibles (vérifie l’onglet Excel).")
            return
        cols = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé"] if c in df.columns]
        vis = df[cols].copy()
        st.dataframe(vis, use_container_width=True)

    if not targets_macro.empty:
        show_excel_table(targets_macro, "🌾 Macro — rôles & bénéfices")
    if not targets_micro.empty:
        def is_vitamin(n: str) -> bool:
            n = strip_accents(n).lower()
            return n.startswith("vit") or "vitamine" in n
        vit = targets_micro[targets_micro["Nutriment"].astype(str).apply(is_vitamin)].copy()
        mino= targets_micro[~targets_micro["Nutriment"].astype(str).apply(is_vitamin)].copy()
        if not vit.empty:
            show_excel_table(vit,  "🍊 Vitamines — rôles & bénéfices")
        if not mino.empty:
            show_excel_table(mino, "🧂 Minéraux — rôles & bénéfices")

# ===================== Tabs =====================
tab_profile, tab_journal, tab_bilan, tab_food = st.tabs(["👤 Profil", "🧾 Journal", "📊 Bilan", "🍽️ Alimentation"])
with tab_profile: render_profile_page()
with tab_journal: render_journal_page()
with tab_bilan:   render_bilan_page()
with tab_food:    render_alimentation_page()

# ===================== Export/Import =====================
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

# ===================== Diagnostic léger =====================
with st.expander("🛠️ Diagnostic (ouvrir seulement si besoin)"):
    st.write("Assets dir:", str(ASSETS_DIR), "exists:", ASSETS_DIR.exists())
    try:
        st.write("Assets list:", os.listdir(ASSETS_DIR) if ASSETS_DIR.exists() else "—")
    except Exception as e:
        st.write("Assets list error:", e)
    st.write("Excel:", str(DEFAULT_EXCEL_PATH), "exists:", DEFAULT_EXCEL_PATH.exists())
    st.write("Logo:", str(DEFAULT_LOGO_PATH), "exists:", DEFAULT_LOGO_PATH.exists())
    # --- ALA debug ---
    dflt = dt.date.today().isoformat()
    last = fetch_last_date_with_rows() or dflt
    st.write("Dernière date avec lignes:", last)
    df_dbg = fetch_journal_by_date(last)
    if df_dbg is not None and not df_dbg.empty:
        st.write("Colonnes du journal (dernier jour):", list(df_dbg.columns))
        # colonnes candidates ALA
        def _find_ala_columns_in(cols):  # même logique que plus haut
            out = []
            for c in cols:
                ck = canon_key(c)
                if "epa" in ck or "dha" in ck: continue
                if ("ala" in ck and ("omega3" in ck or "w3" in ck)) or ("alpha" in ck and "linolen" in ck) or \
                   ck.endswith("alag") or ck.endswith("ala") or "acidealphalinoleniquew3" in ck:
                    out.append(c)
            return out
        ala_cols = _find_ala_columns_in(df_dbg.columns.tolist())
        st.write("ALA colonnes détectées:", ala_cols if ala_cols else "—")
        if ala_cols:
            s = pd.DataFrame(df_dbg[ala_cols]).apply(pd.to_numeric, errors="coerce").fillna(0.0)
            st.write("Somme ALA (débug):", float(s.sum(numeric_only=True).sum()))
    st.write("Build:", VERSION)
