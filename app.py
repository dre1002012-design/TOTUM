# Totum, suivi nutritionnel — WebApp complète (profil, objectifs, repas, graphiques donut)
# Lancer :
#   pip install -r requirements.txt
#   streamlit run app.py

import io
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Totum, suivi nutritionnel", page_icon="🥗", layout="wide")

# ==========================
# Helpers
# ==========================
def coerce_num(s):
    if s is None:
        return s
    s = s.astype(str).str.replace("\u00A0"," ", regex=False).str.replace(",",".", regex=False)
    ext = s.str.extract(r"([-+]?\d*\.?\d+)")[0]
    return pd.to_numeric(ext, errors="coerce")

def safe_parse(xls, sheet):
    try: return xls.parse(sheet)
    except Exception: return None

def nutrient_cols(df):
    return [c for c in df.columns if str(c).endswith("_100g")]

def per100_to_name(c):  # "Proteines_g_100g" -> "Protéines_g"
    base = c.replace("_100g","")
    return base.replace("Proteines","Protéines").replace("Energie","Énergie")

def calc_from_food_row(row: pd.Series, qty_g: float) -> dict:
    out = {}
    for c in nutrient_cols(row.to_frame().T):
        out[per100_to_name(c)] = float(qty_g)/100.0 * float(row[c])
    return out

def percent(num, den):
    num = pd.to_numeric(num, errors="coerce").fillna(0.0)
    den = pd.to_numeric(den, errors="coerce").replace(0, np.nan)
    return (num/den*100).round(1)

def tdee_mifflin(sex, age, height_cm, weight_kg, activity):
    if sex.lower().startswith("h"):
        bmr = 10*weight_kg + 6.25*height_cm - 5*age + 5
    else:
        bmr = 10*weight_kg + 6.25*height_cm - 5*age - 161
    factors = {"Sédentaire":1.2,"Léger (1-3x/sem)":1.375,"Modéré (3-5x/sem)":1.55,"Intense (6-7x/sem)":1.725,"Athlète (2x/jour)":1.9}
    return bmr * factors.get(activity, 1.2)

def donut(cons, target, title):
    cons = float(cons) if pd.notna(cons) else 0.0
    target = float(target) if pd.notna(target) and target>0 else 0.0
    rest = max(target - cons, 0.0)
    vals = [cons, rest] if target>0 else [cons]
    labels = ["Ingesté", "Restant"] if target>0 else ["Ingesté"]
    fig = go.Figure(data=[go.Pie(values=vals, labels=labels, hole=0.6, textinfo="percent+label")])
    fig.update_layout(title=title, margin=dict(l=0,r=0,t=40,b=0), height=260)
    return fig

# ==========================
# Session init
# ==========================
if "foods" not in st.session_state:
    st.session_state["foods"] = pd.DataFrame(columns=["nom"])

if "targets_macro" not in st.session_state:
    st.session_state["targets_macro"] = pd.DataFrame(columns=["Nutriment","Objectif"])

if "targets_micro" not in st.session_state:
    st.session_state["targets_micro"] = pd.DataFrame(columns=["Nutriment","Unité","Objectif"])

if "log" not in st.session_state:
    st.session_state["log"] = pd.DataFrame(columns=["date","repas","nom","quantite_g"])

if "profile" not in st.session_state:
    st.session_state["profile"] = {
        "sexe": "Homme","age": 30,"taille_cm": 175.0,"poids_kg": 70.0,
        "activite": "Modéré (3-5x/sem)","cibles_auto": False,"repartition_macros": (30,40,30)
    }

if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = None

# ==========================
# Header (logo + titre)
# ==========================
col_logo, col_title = st.columns([1, 6])
with col_logo:
    if st.session_state["logo_bytes"] is not None:
        st.image(st.session_state["logo_bytes"], width=80)
with col_title:
    st.title("Totum, suivi nutritionnel")

# ==========================
# Sidebar : imports + profil
# ==========================
st.sidebar.header("📥 Données")
uploaded = st.sidebar.file_uploader("Importe ton Excel (.xlsx)", type=["xlsx"], help="Feuilles: Liste, Cible Macro, Cible micro H/F, Profils (optionnel)")
logo_file = st.sidebar.file_uploader("Logo TOTUM (PNG/JPG)", type=["png","jpg","jpeg"])

if logo_file is not None:
    st.session_state["logo_bytes"] = logo_file.read()

p = st.session_state["profile"]

st.sidebar.header("👤 Profil")
p["sexe"] = st.sidebar.selectbox("Sexe", ["Homme","Femme"], index=0 if p["sexe"].lower().startswith("h") else 1)
p["age"] = st.sidebar.number_input("Âge", min_value=10, max_value=100, value=int(p["age"]))
p["taille_cm"] = st.sidebar.number_input("Taille (cm)", min_value=120.0, max_value=230.0, value=float(p["taille_cm"]))
p["poids_kg"] = st.sidebar.number_input("Poids (kg)", min_value=30.0, max_value=250.0, value=float(p["poids_kg"]))
p["activite"] = st.sidebar.selectbox("Activité", ["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"],
                                     index=["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"].index(p["activite"]))
p["cibles_auto"] = st.sidebar.checkbox("Cibles automatiques (TDEE + % macros)", value=p["cibles_auto"])
st.session_state["profile"] = p

# Import Excel (alim + cibles depuis fichier)
if uploaded:
    xls = pd.ExcelFile(uploaded)

    # Liste aliments (3 500)
    df_liste = safe_parse(xls, "Liste")
    if df_liste is not None and "nom" in df_liste.columns:
        cols = ["nom"] + nutrient_cols(df_liste)
        st.session_state["foods"] = df_liste[cols].copy()

    # Cibles Macro (prioritaires si présentes)
    df_macro = safe_parse(xls, "Cible Macro")
    if df_macro is not None and set(["Nutriment","Ojectifs"]).issubset(df_macro.columns):
        tmac = df_macro[["Nutriment","Ojectifs"]].rename(columns={"Ojectifs":"Objectif"}).copy()
        tmac["Objectif"] = coerce_num(tmac["Objectif"])
        st.session_state["targets_macro"] = tmac

    # Cibles Micro selon sexe
    df_micro = safe_parse(xls, "Cible micro H" if p["sexe"]=="Homme" else "Cible micro F")
    if df_micro is not None and "Nutriment" in df_micro.columns and "Ojectifs" in df_micro.columns:
        tm = df_micro[["Nutriment","Ojectifs"] + (["Unité"] if "Unité" in df_micro.columns else [])].copy()
        tm = tm.rename(columns={"Ojectifs":"Objectif"})
        tm["Objectif"] = coerce_num(tm["Objectif"])
        if "Unité" not in tm.columns: tm["Unité"] = ""
        st.session_state["targets_micro"] = tm

# Si l’utilisateur veut des cibles auto (et pas de feuille Cible Macro), on calcule depuis le profil
if p["cibles_auto"] and (st.session_state["targets_macro"].empty or not uploaded):
    kcal = tdee_mifflin(p["sexe"], p["age"], p["taille_cm"], p["poids_kg"], p["activite"])
    pr, gc, ft = p["repartition_macros"]
    st.session_state["targets_macro"] = pd.DataFrame([
        {"Nutriment":"Énergie_kcal","Objectif": round(kcal)},
        {"Nutriment":"Protéines_g","Objectif": round(kcal*(pr/100)/4)},
        {"Nutriment":"Glucides_g","Objectif": round(kcal*(gc/100)/4)},
        {"Nutriment":"Lipides_g","Objectif":  round(kcal*(ft/100)/9)},
    ])

foods = st.session_state["foods"]
targets_macro = st.session_state["targets_macro"]
targets_micro = st.session_state["targets_micro"]

# ==========================
# Saisie (mobile-friendly) : date/repas → recherche → quantité → ajouter
# ==========================
st.subheader("🧾 Journal du jour")
c_date, c_repas = st.columns(2)
today = c_date.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY")
repas = c_repas.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"])

search = st.text_input("Rechercher un aliment (saisis quelques lettres)")
if not foods.empty:
    base_list = foods["nom"].astype(str)
    if search:
        opts = base_list[base_list.str.contains(search, case=False, na=False)].tolist()
    else:
        opts = base_list.head(1000).tolist()
    chosen = st.selectbox("Aliment", options=opts if opts else ["(aucun résultat)"])
else:
    chosen = st.selectbox("Aliment", options=["(liste vide)"])

col_qty, col_add = st.columns([1,1])
qty = col_qty.number_input("Quantité (g)", min_value=1, value=150, step=10)
if col_add.button("➕ Ajouter"):
    if chosen not in ["(aucun résultat)","(liste vide)"] and not foods.empty:
        row = foods.loc[foods["nom"]==chosen]
        if not row.empty:
            row = row.iloc[0]
            calc = calc_from_food_row(row, qty)
            entry = {"date": today, "repas": repas, "nom": chosen, "quantite_g": qty}
            entry.update(calc)
            st.session_state["log"] = pd.concat([st.session_state["log"], pd.DataFrame([entry])], ignore_index=True)
            st.success(f"Ajouté : {qty} g de {chosen} ({repas})")

with st.expander("➕ Créer un aliment personnalisé"):
    c1,c2,c3,c4 = st.columns(4)
    new_name = c1.text_input("Nom de l’aliment")
    new_kcal = c2.number_input("Énergie (kcal) /100g", min_value=0.0, value=0.0)
    new_p    = c3.number_input("Protéines (g) /100g", min_value=0.0, value=0.0)
    new_c    = c4.number_input("Glucides (g) /100g",  min_value=0.0, value=0.0)
    new_fat  = c1.number_input("Lipides (g) /100g",   min_value=0.0, value=0.0)
    new_fiber= c2.number_input("Fibres (g) /100g",    min_value=0.0, value=0.0)
    new_vc   = c3.number_input("Vitamine C (mg) /100g", min_value=0.0, value=0.0)
    if st.button("Enregistrer cet aliment"):
        if new_name.strip():
            new_row = {
                "nom": new_name.strip(),
                "Energie_kcal_100g": new_kcal,
                "Proteines_g_100g": new_p,
                "Glucides_g_100g": new_c,
                "Lipides_g_100g": new_fat,
                "Fibres_g_100g": new_fiber,
                "Vitamine C_mg_100g": new_vc,
            }
            st.session_state["foods"] = pd.concat([st.session_state["foods"], pd.DataFrame([new_row])], ignore_index=True)
            st.success(f"Aliment ajouté : {new_name}")

# ==========================
# Journal affichage
# ==========================
st.markdown("### 📓 Lignes du journal")
if not st.session_state["log"].empty:
    st.dataframe(st.session_state["log"].sort_values(["date","repas"]), width="stretch")
else:
    st.info("Ajoute des aliments pour remplir le journal.")

# ==========================
# Rapport du jour + Objectifs (avec donuts)
# ==========================
st.subheader("📊 Rapport journalier & % objectifs")
log = st.session_state["log"]
if not log.empty:
    day = log.loc[log["date"]==today].copy()

    if day.empty:
        st.caption("Aucune saisie aujourd’hui.")
    else:
        nutr_cols = [c for c in day.columns if c not in ["date","repas","nom","quantite_g"]]
        per_meal = day.groupby("repas")[nutr_cols].sum(numeric_only=True).reset_index()

        st.markdown("#### Totaux par repas")
        show_meal = per_meal.rename(columns={"Énergie_kcal":"Calories","Energie_kcal":"Calories"})
        st.dataframe(show_meal, width="stretch")

        totals = day[nutr_cols].sum(numeric_only=True)

        # Récup cibles
        def target_for(nm_regex):
            if targets_macro.empty: return np.nan
            m = targets_macro.loc[targets_macro["Nutriment"].str.contains(nm_regex, case=False, na=False)]
            return float(m["Objectif"].iloc[0]) if not m.empty else np.nan

        kcal = totals.get("Énergie_kcal", np.nan)
        if pd.isna(kcal): kcal = totals.get("Energie_kcal", np.nan)
        prot = totals.get("Protéines_g", totals.get("Proteines_g", np.nan))
        carb = totals.get("Glucides_g", np.nan)
        fat  = totals.get("Lipides_g", np.nan)

        t_kcal = target_for("énergie|energie|kcal")
        t_p = target_for("protéines|proteines")
        t_c = target_for("glucides|carb")
        t_f = target_for("lipides|fat|gras")

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Calories", f"{(kcal or 0):.0f}", f"/ {t_kcal:.0f}" if pd.notna(t_kcal) else "")
        c2.metric("Protéines (g)", f"{(prot or 0):.0f}", f"/ {t_p:.0f}" if pd.notna(t_p) else "")
        c3.metric("Glucides (g)", f"{(carb or 0):.0f}", f"/ {t_c:.0f}" if pd.notna(t_c) else "")
        c4.metric("Lipides (g)", f"{(fat or 0):.0f}", f"/ {t_f:.0f}" if pd.notna(t_f) else "")

        # Donuts % d'objectifs
        st.markdown("#### 🎯 % d’objectifs atteints (anneaux)")
        d1,d2,d3,d4 = st.columns(4)
        d1.plotly_chart(donut(kcal or 0, t_kcal or 0, "Énergie (kcal)"), use_container_width=True)
        d2.plotly_chart(donut(prot or 0, t_p or 0, "Protéines (g)"), use_container_width=True)
        d3.plotly_chart(donut(carb or 0, t_c or 0, "Glucides (g)"), use_container_width=True)
        d4.plotly_chart(donut(fat or 0,  t_f or 0, "Lipides (g)"), use_container_width=True)

        # % objectifs Tableaux (texte)
        if not targets_macro.empty:
            cons = []
            for _, r in targets_macro.iterrows():
                n = str(r["Nutriment"])
                match = [k for k in totals.index if n.split("_")[0].lower() in k.lower()]
                cons_val = float(totals[match[0]]) if match else 0.0
                cons.append({"Nutriment": n, "Objectif": float(r["Objectif"]), "Consommée": cons_val})
            dfM = pd.DataFrame(cons)
            dfM["% objectif"] = percent(dfM["Consommée"], dfM["Objectif"])
            st.markdown("#### ⚡ % Objectifs – Macros")
            st.dataframe(dfM, width="stretch")

        if not targets_micro.empty:
            cons = []
            for _, r in targets_micro.iterrows():
                n = str(r["Nutriment"])
                match = [k for k in totals.index if n.split("_")[0].lower() in k.lower()]
                cons_val = float(totals[match[0]]) if match else 0.0
                cons.append({"Nutriment": n, "Unité": r.get("Unité",""), "Objectif": float(r["Objectif"]), "Consommée": cons_val})
            dfm = pd.DataFrame(cons)
            dfm["% objectif"] = percent(dfm["Consommée"], dfm["Objectif"])
            st.markdown("#### 🧪 % Objectifs – Micros")
            st.dataframe(dfm, width="stretch")
else:
    st.caption("Aucune saisie aujourd’hui.")

# ==========================
# Export / Import journal
# ==========================
st.markdown("### 💾 Export / Import du journal")
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Journal")
    return out.getvalue()

colE, colI = st.columns(2)
if colE.button("📥 Exporter le journal (.xlsx)"):
    if st.session_state["log"].empty:
        st.warning("Le journal est vide.")
    else:
        st.download_button("Télécharger maintenant", data=to_excel_bytes(st.session_state["log"]),
                           file_name="journal_nutrition.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

imp_file = colI.file_uploader("Importer un journal existant (.xlsx)", type=["xlsx"])
if imp_file is not None:
    try:
        j = pd.read_excel(imp_file)
        if set(["date","repas","nom","quantite_g"]).issubset(j.columns):
            st.session_state["log"] = j
            st.success("Journal importé.")
        else:
            st.error("Colonnes attendues : date, repas, nom, quantite_g (+ colonnes nutriments).")
    except Exception as e:
        st.error(f"Import impossible : {e}")

st.markdown("---")
st.caption("Astuce : pour que les objectifs viennent de ton fichier, fournis la feuille 'Cible Macro'. Sinon coche 'Cibles automatiques' (profil).")
