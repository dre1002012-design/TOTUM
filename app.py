# Totum — Suivi nutritionnel (version stable finale : donuts OK, macros lipidiques OK)
# - Conserve l'interface et les comportements validés
# - Corrige les donuts (mise à jour fiable)
# - Corrige la récupération des lipides (AGS / Oméga-9 / Oméga-6 / ALA / EPA / DHA)
# - Objectifs robustes depuis Excel + fallback profil
# - Saisie profil en entiers (âge/taille/poids)
# - SQLite pour journal (persistance)

from __future__ import annotations
import os, io, re, json, sqlite3, unicodedata, datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import openpyxl

st.set_page_config(page_title="Totum, suivi nutritionnel", page_icon="🥗", layout="wide")
DB_PATH = os.path.join(os.getcwd(), "totum.db")

# ====================== Utils ======================
def strip_accents(text: str) -> str:
    text = str(text or "")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

def canon(s: str) -> str:
    s = strip_accents(str(s)).lower().replace("_", " ").replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()

def canon_key(s: str) -> str:
    # Clé canonique tolérante (accents, espaces, ponctuation ignorés)
    return canon(s).replace("(", "").replace(")", "").replace("’", "'").replace(" ", "").replace("__", "_")

def normalize_unit(u: str) -> str:
    u = (u or "").strip()
    u = u.replace("mcg", "µg").replace("ug", "µg").replace("μg", "µg")
    return u

def parse_name_unit(label: str) -> tuple[str, str]:
    # "Calcium-mg" -> ("Calcium","mg") ; tolère -, – , —
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
    return (n / d * 100).round(1).fillna(0.0)

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
    # lecture openpyxl -> fallback pandas
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

def clean_liste(df_liste: pd.DataFrame) -> pd.DataFrame:
    df_liste = drop_parasite_columns(df_liste)
    assert "nom" in df_liste.columns, "La feuille 'Liste' doit contenir la colonne 'nom'."
    if "Energie_kcal_100g" in df_liste.columns and "Énergie_kcal_100g" not in df_liste.columns:
        df_liste = df_liste.rename(columns={"Energie_kcal_100g": "Énergie_kcal_100g"})
    keep = ["nom"] + [c for c in df_liste.columns if c.endswith("_100g")]
    df = df_liste[keep].copy()
    for c in [x for x in df.columns if x.endswith("_100g")]:
        df[c] = coerce_num_col(df[c]).fillna(0.0)

    # anti-doublons colonnes quasi identiques (avec/sans accent/trait/etc.)
    dup_groups = {}
    for c in [x for x in df.columns if x.endswith("_100g")]:
        key = canon_key(c)
        dup_groups.setdefault(key, []).append(c)
    for cols in dup_groups.values():
        if len(cols) > 1:
            base = sorted(cols, key=len)[0]  # garde la plus courte
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

COLORS = {
    "energie": "#ff8c00",
    "proteines": "#2ca02c",
    "glucides": "#1f77b4",
    "lipides": "#d62728",
    "fibres": "#9467bd",
    "restant": "#e0e0e0",
    "objectif": "#bdbdbd",
    "ok": "#5cb85c",
    "warn": "#f0ad4e",
    "bad": "#d9534f",
}

def donut(cons, target, title, color_key="energie"):
    cons = float(cons or 0.0); target = float(target or 0.0)
    if target <= 0:
        fig = go.Figure(data=[go.Pie(values=[1], labels=["Objectif manquant"], hole=0.6,
                                     textinfo="label", marker_colors=[COLORS["objectif"]])])
        fig.update_layout(title=title, margin=dict(l=0, r=0, t=40, b=0), height=220, showlegend=False)
        return fig
    rest = max(target - cons, 0.0)
    fig = go.Figure(data=[
        go.Pie(values=[cons, rest], labels=["Ingéré", "Restant"], hole=0.6,
               textinfo="percent+label",
               marker_colors=[COLORS.get(color_key, "#1f77b4"), COLORS["restant"]])
    ])
    fig.update_layout(title=f"{title} — {cons:.0f}/{target:.0f}",
                      margin=dict(l=0, r=0, t=40, b=0), height=220, showlegend=False)
    return fig

def round_by_unit(unit: str, label: str, val):
    if pd.isna(val): return np.nan
    u = (unit or "").lower().strip()
    name = str(label or "")
    x = float(val)
    if "kcal" in u or name.startswith("Énergie"): return float(np.round(x, 0))
    if (name == "Sel") and u == "mg":            return float(np.round(x, 0))
    return float(np.round(x, 1))

# ====================== Mapping préférés (fusion totaux) ======================
PREFERRED_NAMES = {
    "energiekcal": "Énergie_kcal",
    "proteinesg": "Protéines_g",
    "glucidesg": "Glucides_g",
    "lipidesg": "Lipides_g",
    "fibresg": "Fibres_g",
    "agsaturesg": "AG_saturés_g",
    "acideoleiquew9g": "Acide_oléique_W9_g",
    "acidelinoleiquew6lag": "Acide_linoléique_W6_LA_g",
    "acidealphalinoleniquew3alag": "Acide_alpha-linolénique_W3_ALA_g",
    "acidealpha-linoléniquew3alag": "Acide_alpha-linolénique_W3_ALA_g",
    "epag": "EPA_g",
    "dhag": "DHA_g",
    "sucresg": "Sucres_g",
    "selg": "Sel_g",
    "cholesterolmg": "Cholestérol_mg",
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

# ====================== Profil / objectifs ======================
def tdee_mifflin(sex, age, height_cm, weight_kg, activity):
    # Formule Mifflin-St Jeor + facteurs activité cohérents
    if canon(sex).startswith("h"):
        bmr = 10*weight_kg + 6.25*height_cm - 5*age + 5
    else:
        bmr = 10*weight_kg + 6.25*height_cm - 5*age - 161
    factors = {
        "sédentaire": 1.2,
        "léger (1 3x sem)": 1.375, "leger (1 3x sem)": 1.375,
        "modéré (3 5x sem)": 1.55,  "modere (3 5x sem)": 1.55,
        "intense (6 7x sem)": 1.725,
        "athlète (2x/jour)": 1.9,   "athlete (2x jour)": 1.9,
    }
    return bmr * factors.get(canon(activity), 1.2)

def profile_targets(p):
    # Objectifs journaliers de base (kcal + répartition P/G/L + fibres 30g)
    kcal = tdee_mifflin(p["sexe"], int(p["age"]), float(p["taille_cm"]), float(p["poids_kg"]), p["activite"])
    pr, gc, ft = p["repartition_macros"]
    return {
        "energie":   round(kcal),
        "proteines": round(kcal * (pr/100) / 4),
        "glucides":  round(kcal * (gc/100) / 4),
        "lipides":   round(kcal * (ft/100) / 9),
        "fibres":    30,
    }

# ====================== SQLite ======================
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
    return {"sexe":"Homme","age":30,"taille_cm":175.0,"poids_kg":70.0,"activite":"Modéré (3-5x/sem)","repartition_macros":(30,40,30)}

def save_profile(p):
    conn = init_db()
    conn.execute("""
        INSERT INTO profile (id,sexe,age,taille_cm,poids_kg,activite,prot_pct,gluc_pct,lip_pct)
        VALUES (1,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            sexe=excluded.sexe, age=excluded.age, taille_cm=excluded.taille_cm, poids_kg=excluded.poids_kg,
            activite=excluded.activite, prot_pct=excluded.prot_pct, gluc_pct=excluded.gluc_pct, lip_pct=excluded.lip_pct;
    """, (p["sexe"], int(p["age"]), float(p["taille_cm"]), float(p["poids_kg"]),
          p["activite"], int(p["repartition_macros"][0]), int(p["repartition_macros"][1]), int(p["repartition_macros"][2])) )
    conn.commit()

def insert_journal(date_iso, repas, nom, quantite_g, nutrients: dict):
    conn = init_db()
    conn.execute("INSERT INTO journal (date,repas,nom,quantite_g,nutrients_json) VALUES (?,?,?,?,?)",
                 (date_iso, repas, nom, float(quantite_g), json.dumps(nutrients, ensure_ascii=False)))
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

# ====================== Objectifs (robuste) ======================
def build_objectif_robuste(df: pd.DataFrame, is_macro=False) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)

    # 1) colonnes candidates directes
    candidates = [c for c in ["Objectif","Cible","Objectifs","Objectif (jour)","Target","Cible (jour)"] if c in df.columns]
    out = pd.Series(0.0, index=df.index, dtype=float)
    for c in candidates:
        v = coerce_num_col(df[c])
        out = out.where(out > 0, v.fillna(0.0))

    # 2) si encore vides, tente toute colonne numérique
    if (out <= 0).any():
        num_cols = []
        for c in df.columns:
            if c in ["Nutriment","Icône","Fonction","Bénéfice Santé"]: 
                continue
            v = coerce_num_col(df[c])
            if v is not None and v.notna().any():
                num_cols.append((c, v))
        if num_cols:
            for idx in df.index[(out <= 0)]:
                for _, v in num_cols:
                    val = v.loc[idx]
                    if pd.notna(val) and float(val) > 0:
                        out.loc[idx] = float(val); break

    # 3) arrondi par unité
    def unit_from_nutr(nutr: str) -> str:
        _, unit = parse_name_unit(str(nutr))
        return normalize_unit(unit)
    units = df["Nutriment"].apply(unit_from_nutr) if "Nutriment" in df.columns else pd.Series("", index=df.index)
    names = df["Nutriment"] if "Nutriment" in df.columns else pd.Series("", index=df.index)
    out = pd.Series([round_by_unit(u, str(n), x) for u, n, x in zip(units, names, out)], index=df.index, dtype=float)

    # 4) fallback profil (macros de base si toujours 0)
    if is_macro and "Nutriment" in df.columns:
        base = profile_targets(st.session_state["profile"])
        def maybe_profile(nutr, val):
            if float(val or 0) > 0: return val
            name, _ = parse_name_unit(str(nutr))
            nclean = re.sub(r"\s*\(.*?\)\s*", "", name).strip()
            c = canon(nclean)
            if c.startswith("energie"):  return base["energie"]
            if c.startswith("proteine"): return base["proteines"]
            if c.startswith("glucide"):  return base["glucides"]
            if c.startswith("lipide"):   return base["lipides"]
            if c.startswith("fibre"):    return base["fibres"]
            return val
        out = out.combine(df["Nutriment"], func=lambda v, n: maybe_profile(n, v))
        out = pd.to_numeric(out, errors="coerce").fillna(0.0)
    return out

# ====================== Session init ======================
if "foods" not in st.session_state: st.session_state["foods"] = pd.DataFrame(columns=["nom"])
if "targets_micro" not in st.session_state: st.session_state["targets_micro"] = pd.DataFrame()
if "targets_macro" not in st.session_state: st.session_state["targets_macro"] = pd.DataFrame()
if "logo_bytes" not in st.session_state: st.session_state["logo_bytes"] = None
if "profile" not in st.session_state: st.session_state["profile"] = load_profile()

# ====================== Header ======================
left, mid, right = st.columns([1,6,2])
with left:
    if st.session_state["logo_bytes"]:
        st.image(st.session_state["logo_bytes"], width=70)
with mid:
    st.title("Totum, suivi nutritionnel")
with right:
    if st.button("💾 Sauver profil & journal"):
        save_profile(st.session_state["profile"])
        st.success("Données sauvegardées (SQLite : totum.db)")

# ====================== Import Excel (sidebar) ======================
with st.sidebar:
    st.header("📥 Import Excel")
    upl = st.file_uploader("Sélectionne ton fichier TOTUM-Suivi nutritionnel.xlsx", type=["xlsx"])
    logo = st.file_uploader("Logo TOTUM (PNG/JPG)", type=["png","jpg","jpeg"])
    if logo is not None:
        st.session_state["logo_bytes"] = logo.read()

    if upl:
        df_liste = read_sheet_values(upl, "Liste")
        if df_liste is not None:
            st.session_state["foods"] = clean_liste(df_liste)

        sex = st.session_state["profile"]["sexe"]
        micro_sheet = "Cible micro Homme" if canon(sex).startswith("homme") else "Cible micro Femme"
        df_micro = read_sheet_values(upl, micro_sheet)
        if df_micro is not None and "Nutriment" in df_micro.columns:
            tm = drop_parasite_columns(df_micro.copy())
            tm["Objectif"] = build_objectif_robuste(tm, is_macro=False)
            keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tm.columns]
            st.session_state["targets_micro"] = tm[keep]

        df_macro = read_sheet_values(upl, "Cible Macro")
        if df_macro is not None and "Nutriment" in df_macro.columns:
            tmac = drop_parasite_columns(df_macro.copy())
            tmac["Objectif"] = build_objectif_robuste(tmac, is_macro=True)
            keep = [c for c in ["Nutriment","Icône","Fonction","Bénéfice Santé","Objectif"] if c in tmac.columns]
            st.session_state["targets_macro"] = tmac[keep]

# ====================== Onglets ======================
tab_profile, tab_journal, tab_bilan = st.tabs(["👤 Profil", "🧾 Journal", "📊 Bilan"])

# ----------------- Profil -----------------
with tab_profile:
    st.subheader("Paramètres du profil (objectifs auto)")
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
    st.markdown("**Répartition des macros (P/G/L)** – la somme doit faire 100%")
    cP, cG, cL = st.columns(3)
    pr = cP.slider("Protéines (%)", 0, 100, int(p["repartition_macros"][0]), 1)
    gc = cG.slider("Glucides (%)", 0, 100, int(p["repartition_macros"][1]), 1)
    lp = cL.slider("Lipides (%)", 0, 100, int(p["repartition_macros"][2]), 1)
    if pr + gc + lp != 100:
        lp = max(0, min(100, 100 - pr - gc))
    p["repartition_macros"] = (pr, gc, lp)
    st.caption(f"Somme = {sum(p['repartition_macros'])}%  –  P/G/L = {p['repartition_macros']}")
    st.session_state["profile"] = p
    if st.button("💾 Sauver le profil"):
        save_profile(p)
        st.success("Profil enregistré.")
    base_vals = profile_targets(p)
    st.markdown("#### Objectifs journaliers (calculés)")
    st.write(
        pd.DataFrame([{
            "Énergie (kcal)": base_vals["energie"],
            "Protéines (g)": base_vals["proteines"],
            "Glucides (g)":  base_vals["glucides"],
            "Lipides (g)":   base_vals["lipides"],
            "Fibres (g)":    base_vals["fibres"],
        }]).T.rename(columns={0: "Objectif"}).astype("Int64", errors="ignore")
    )

# ----------------- Journal -----------------
with tab_journal:
    st.subheader("Ajouter une consommation")
    foods = st.session_state["foods"]
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    date_sel = c1.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY")
    repas = c2.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"])
    qty = c3.number_input("Quantité (g)", min_value=1, value=150, step=10)
    nom = c4.selectbox("Aliment (taper pour chercher)", options=foods["nom"].astype(str).tolist() if not foods.empty else ["(liste vide)"])
    if st.button("➕ Ajouter au journal"):
        if not foods.empty and nom != "(liste vide)":
            row = foods.loc[foods["nom"] == nom]
            if not row.empty:
                row = row.iloc[0]
                calc = calc_from_food_row(row, qty)
                insert_journal(date_sel.isoformat(), repas, nom, qty, calc)
                st.success(f"Ajouté : {qty} g de {nom} ({repas})")
    st.markdown("### Lignes du jour")
    df_day = fetch_journal_by_date(date_sel.isoformat())
    st.dataframe(df_day.drop(columns=["id"]) if not df_day.empty else df_day, use_container_width=True)

# ----------------- Bilan -----------------
with tab_bilan:
    st.subheader("Vue d’ensemble du jour")
    date_bilan = st.date_input("Date du bilan", value=dt.date.today(), format="DD/MM/YYYY", key="date_bilan")
    df_today = fetch_journal_by_date(date_bilan.isoformat())

    # Totaux du jour (fusion colonnes quasi identiques)
    if not df_today.empty:
        base_exclude = ["id","date","repas","nom","quantite_g"]
        df_clean = drop_parasite_columns(df_today)
        df_num = df_clean.drop(columns=[c for c in base_exclude if c in df_clean.columns], errors="ignore")
        raw = df_num.sum(numeric_only=True)
        totals = unify_totals_series(raw)
    else:
        totals = pd.Series(dtype=float)

    targets_macro = st.session_state["targets_macro"].copy()
    targets_micro = st.session_state["targets_micro"].copy()

    # ===== Clés macros robustes (toutes variantes) =====
    MACRO_KEYS = {
        "Énergie": ["Énergie_kcal","Energie_kcal","kcal","energie_kcal"],
        "Protéines": ["Protéines_g","Proteines_g","proteines"],
        "Glucides": ["Glucides_g","glucides"],
        "Lipides": ["Lipides_g","lipides"],
        "Fibres": ["Fibres_g","fibres"],
        "Acides gras saturés": ["AG_saturés_g","AG_satures_g","Acides_gras_saturés_g","acides_gras_satures_g"],
        # Oméga-9 : accepte soit colonne spécifique, soit AG_monoinsaturés comme proxy
        "Oméga-9": ["Acide_oléique_W9_g","Acide_oleique_W9_g","AG_monoinsaturés_g","AG_monoinsatures_g"],
        # Oméga-6 : accepte spécifique ou AG_polyinsaturés (proxy)
        "Oméga-6": ["Acide_linoléique_W6_LA_g","Acide_linoleique_W6_LA_g","AG_polyinsaturés_g","AG_polyinsatures_g"],
        # Oméga-3 (ALA) : normalise toutes les variantes d’écriture
        "Oméga-3": ["Acide_alpha-linolénique_W3_ALA_g","Acide_alphalinolénique_W3_ALA_g","Acide_alpha_linolenique_W3_ALA_g"],
        "EPA": ["EPA_g"], "DHA": ["DHA_g"],
        "Sucres": ["Sucres_g"], "Sel": ["Sel_g"], "Cholestérol": ["Cholestérol_mg","Cholesterol_mg"],
    }

    def _canon(s: str) -> str:
        return canon_key(s)

    def _all_total_keys_canon(tot: pd.Series) -> dict[str, str]:
        d = {}
        if not isinstance(tot, pd.Series): return d
        for idx in tot.index:
            d[_canon(idx)] = idx
        return d

    def find_total_value(aliases: list[str], tot: pd.Series) -> float:
        if not isinstance(tot, pd.Series) or tot.empty:
            return 0.0
        # direct
        for a in aliases:
            if a in tot.index and pd.notna(tot[a]):
                return float(tot[a])
        # canonique
        alias_keys = [_canon(a) for a in aliases]
        canon_map = _all_total_keys_canon(tot)
        for ak in alias_keys:
            if ak in canon_map:
                v = tot[canon_map[ak]]
                if pd.notna(v): return float(v)
        # "contient"
        for ak in alias_keys:
            for ck, orig in canon_map.items():
                if ak in ck or ck in ak:
                    v = tot[orig]
                    if pd.notna(v): return float(v)
        return 0.0

    def macro_base_name(label: str) -> str:
        name, _ = parse_name_unit(label)
        return re.sub(r"\s*\(.*?\)\s*", "", name).strip()

    def consumed_macro(label: str, tot: pd.Series) -> float:
        base = macro_base_name(label)
        aliases = MACRO_KEYS.get(base, [])
        v = find_total_value(aliases, tot)
        if v > 0: return v
        # fallback énergie calculée
        if base == "Énergie" and isinstance(tot, pd.Series):
            p = float(tot.get("Protéines_g", tot.get("Proteines_g", 0.0)))
            g = float(tot.get("Glucides_g", 0.0))
            l = float(tot.get("Lipides_g", 0.0))
            return p*4 + g*4 + l*9
        return 0.0

    def build_macros_df():
        df = targets_macro.copy()
        if df is None or df.empty or "Nutriment" not in df.columns:
            base = profile_targets(st.session_state["profile"])
            rows = [
                {"Nutriment":"Énergie (calories)-kcal","Icône":"🔥","Fonction":"Source vitale","Bénéfice Santé":"Maintien poids & vitalité","Objectif":base["energie"]},
                {"Nutriment":"Protéines (conso min)-g","Icône":"💪","Fonction":"Construisent muscles","Bénéfice Santé":"Récupération","Objectif":base["proteines"]},
                {"Nutriment":"Glucides (conso min)-g","Icône":"🍞","Fonction":"Carburant","Bénéfice Santé":"Énergie","Objectif":base["glucides"]},
                {"Nutriment":"Lipides (conso min)-g","Icône":"🥑","Fonction":"Hormones","Bénéfice Santé":"Cœur","Objectif":base["lipides"]},
                {"Nutriment":"Fibres-g","Icône":"🌾","Fonction":"Digestion","Bénéfice Santé":"Métabolisme","Objectif":base["fibres"]},
            ]
            df = pd.DataFrame(rows)

        # objectifs robustes si vides
        if "Objectif" not in df.columns or (pd.to_numeric(df["Objectif"], errors="coerce").fillna(0.0) == 0).all():
            df["Objectif"] = build_objectif_robuste(df, is_macro=True)

        # unité / nom
        def unit_of(r): return normalize_unit(parse_name_unit(str(r["Nutriment"]))[1])
        def name_of(r): return parse_name_unit(str(r["Nutriment"]))[0]
        df["Unité"] = df.apply(unit_of, axis=1)
        df["Nom"]   = df.apply(name_of, axis=1)

        # conso + arrondis
        df["Consommée"] = df["Nutriment"].apply(lambda lab: consumed_macro(lab, totals))
        df["Objectif"]  = df.apply(lambda r: round_by_unit(r["Unité"], str(r["Nutriment"]), r["Objectif"]), axis=1)
        df["Consommée"] = df.apply(lambda r: round_by_unit(r["Unité"], str(r["Nutriment"]), r["Consommée"]), axis=1)
        df["% objectif"] = percent(df["Consommée"], df["Objectif"]).round(0)

        for c in ["Icône","Fonction","Bénéfice Santé"]:
            if c not in df.columns: df[c] = ""
            df[c] = df[c].fillna("")
        return df

    macros_df = build_macros_df()

    # ===== Donuts =====
    cfg = {"displaylogo": False, "responsive": True}
    d1, d2, d3, d4, d5 = st.columns(5)

    def donut_vals(prefix: str, fallback: float):
        if macros_df.empty:
            return 0.0, fallback
        # recherche robuste sur la colonne Nom (sans unité)
        sel = macros_df[macros_df["Nom"].astype(str).str.match(rf"^{re.escape(prefix)}\b", case=False)]
        if sel.empty:
            # fallback sur Nutriment (avec unité)
            sel = macros_df[macros_df["Nutriment"].astype(str).str.match(rf"^{re.escape(prefix)}\b", case=False)]
        if sel.empty:
            return 0.0, fallback
        row = sel.iloc[0]
        return float(row.get("Consommée", 0.0) or 0.0), float(row.get("Objectif", fallback) or fallback)

    base_vals = profile_targets(st.session_state["profile"])
    c1,t1 = donut_vals("Énergie",  base_vals["energie"]);   d1.plotly_chart(donut(c1,t1,"Énergie (kcal)","energie"),   config=cfg)
    c2,t2 = donut_vals("Protéines",base_vals["proteines"]); d2.plotly_chart(donut(c2,t2,"Protéines (g)","proteines"), config=cfg)
    c3,t3 = donut_vals("Glucides", base_vals["glucides"]);  d3.plotly_chart(donut(c3,t3,"Glucides (g)","glucides"),   config=cfg)
    c4,t4 = donut_vals("Lipides",  base_vals["lipides"]);   d4.plotly_chart(donut(c4,t4,"Lipides (g)","lipides"),     config=cfg)
    c5,t5 = donut_vals("Fibres",   base_vals["fibres"]);    d5.plotly_chart(donut(c5,t5,"Fibres (g)","fibres"),       config=cfg)

    # ===== Micros — barres + tableau =====
    st.markdown("### 🧪 Micros — progression vers l’objectif")
    if not targets_micro.empty and "Nutriment" in targets_micro.columns:
        tmi = targets_micro.copy()
        if "Objectif" not in tmi.columns or (pd.to_numeric(tmi["Objectif"], errors="coerce").fillna(0.0) == 0).all():
            tmi["Objectif"] = build_objectif_robuste(tmi, is_macro=False)

        def unit_only(r):  return normalize_unit(parse_name_unit(str(r["Nutriment"]))[1])
        def name_only(r):  return parse_name_unit(str(r["Nutriment"]))[0]

        def consumed_micro(r):
            name, unit = parse_name_unit(str(r["Nutriment"]))
            key = f"{name}_{normalize_unit(unit)}".replace(" ","_")
            if isinstance(totals, pd.Series) and key in totals.index and pd.notna(totals[key]):
                return float(totals[key])
            for idx in totals.index:
                if canon_key(idx) == canon_key(key):
                    return float(totals[idx])
            return 0.0

        tmi["Unité"] = tmi.apply(unit_only, axis=1)
        tmi["Nom"]   = tmi.apply(name_only, axis=1)
        tmi["Consommée"] = tmi.apply(consumed_micro, axis=1)
        tmi["% objectif"] = percent(tmi["Consommée"], tmi["Objectif"])

        def pct_color(p):
            if pd.isna(p): return COLORS["warn"]
            if p < 50: return COLORS["bad"]
            if p < 100: return COLORS["warn"]
            return COLORS["ok"]

        height = max(340, int(26*len(tmi)) + 120)
        fig = go.Figure()
        fig.add_bar(y=tmi["Nom"], x=tmi["Objectif"], name="Objectif", orientation="h",
                    marker_color=COLORS["objectif"], opacity=0.30,
                    hovertemplate="Objectif: %{x}<extra></extra>")
        fig.add_bar(y=tmi["Nom"], x=tmi["Consommée"], name="Ingéré", orientation="h",
                    marker_color=[pct_color(v) for v in tmi["% objectif"]],
                    text=[f"{c:.1f}/{o:.1f} ({p:.0f}%)" for c,o,p in zip(tmi["Consommée"], tmi["Objectif"], tmi["% objectif"])],
                    textposition="outside", cliponaxis=False,
                    hovertemplate="Ingéré: %{x}<extra></extra>")
        fig.update_layout(barmode="overlay", title="Micronutriments — Objectif vs Ingéré",
                          xaxis_title="Quantité", yaxis_title="", height=height,
                          margin=dict(l=10,r=10,t=50,b=10), legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, config={"displaylogo": False, "responsive": True})

        tmi2 = tmi.copy()
        tmi2["% objectif"] = tmi2["% objectif"].round(0).astype("Int64")
        cols = [c for c in ["Nom","Unité","Icône","Fonction","Bénéfice Santé","Objectif","Consommée","% objectif"] if c in tmi2.columns]
        st.dataframe(tmi2[cols], use_container_width=True)
    else:
        st.info("Aucune ‘Cible micro’ chargée (onglet Excel manquant ou vide).")

    # ===== Tableau Macros =====
    st.markdown("#### ⚡ % Objectifs – Macros")
    if not macros_df.empty:
        macros_df_show = macros_df.copy()
        macros_df_show["% objectif"] = macros_df_show["% objectif"].round(0).astype("Int64")
        order_cols = [c for c in ["Nom","Unité","Icône","Fonction","Bénéfice Santé","Objectif","Consommée","% objectif"] if c in macros_df_show.columns]
        st.dataframe(macros_df_show[order_cols], use_container_width=True)
    else:
        st.info("Aucune ‘Cible Macro’ chargée. Les donuts utilisent les objectifs du profil.")

    # Totaux par repas
    st.markdown("#### Totaux par repas")
    if not df_today.empty:
        per_meal = df_today.groupby("repas")[[c for c in df_today.columns if c not in ["id","date","repas","nom","quantite_g"]]].sum(numeric_only=True).reset_index()
        per_meal = per_meal.rename(columns={"Énergie_kcal":"Calories","Energie_kcal":"Calories"})
        st.dataframe(per_meal, use_container_width=True)
    else:
        st.caption("Ajoute des aliments dans l’onglet Journal pour voir les totaux par repas.")

# ====================== Export/Import journal ======================
st.markdown("### 💾 Export / Import du journal (toutes dates)")
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
if cE.button("📥 Exporter le journal en Excel"):
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

# ====================== Diagnostic ======================
with st.expander("🛠️ Diagnostic (ouvrir seulement si besoin)"):
    foods = st.session_state["foods"]
    st.write("Colonnes Liste (foods) :", list(foods.columns)[:30], "…")
    if not foods.empty:
        st.write("Exemples nutriments 100g :", [c for c in foods.columns if c.endswith("_100g")][:10])
    st.write("Cible Macro : colonnes :", list(st.session_state["targets_macro"].columns))
    st.write(st.session_state["targets_macro"].head(10))
    st.write("Cible Micro : colonnes :", list(st.session_state["targets_micro"].columns))
    st.write(st.session_state["targets_micro"].head(10))
