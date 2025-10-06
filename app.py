# app.py — WebApp nutrition complète : 3500 aliments (depuis Excel), profil, repas, logo, rapport journalier
# Lancer :
#   pip install streamlit pandas openpyxl numpy
#   streamlit run app.py

import io
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="TOTEM – Suivi Nutrition", page_icon="🥗", layout="wide")

# ==========================
# Helpers
# ==========================
def coerce_num(s):
    """Convertit textes '1 234,5 mg' -> 1234.5 (tolère virgules, unités, espaces insécables)."""
    if s is None:
        return s
    s = s.astype(str).str.replace("\u00A0", " ", regex=False).str.replace(",", ".", regex=False)
    ext = s.str.extract(r"([-+]?\d*\.?\d+)")[0]
    return pd.to_numeric(ext, errors="coerce")

def safe_parse(xls, sheet):
    try: return xls.parse(sheet)
    except Exception: return None

def nutrient_cols(df):
    """Colonnes nutriments au format *_100g."""
    return [c for c in df.columns if str(c).endswith("_100g")]

def per100_to_name(c):  # "Proteines_g_100g" -> "Protéines_g"
    base = c.replace("_100g", "")
    return base.replace("Proteines", "Protéines").replace("Energie", "Énergie")

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
    """Calcul TDEE simple si l'utilisateur veut des cibles auto (sinon on lit la feuille Cible)."""
    if sex.lower().startswith("h"):  # homme
        bmr = 10*weight_kg + 6.25*height_cm - 5*age + 5
    else:  # femme
        bmr = 10*weight_kg + 6.25*height_cm - 5*age - 161
    factors = {
        "Sédentaire": 1.2,
        "Léger (1-3x/sem)": 1.375,
        "Modéré (3-5x/sem)": 1.55,
        "Intense (6-7x/sem)": 1.725,
        "Athlète (2x/jour)": 1.9,
    }
    return bmr * factors.get(activity, 1.2)

# ==========================
# Session init
# ==========================
if "foods" not in st.session_state:
    st.session_state["foods"] = pd.DataFrame(columns=["nom"])  # sera alimenté par Excel

if "targets_macro" not in st.session_state:
    st.session_state["targets_macro"] = pd.DataFrame(columns=["Nutriment","Objectif"])

if "targets_micro" not in st.session_state:
    st.session_state["targets_micro"] = pd.DataFrame(columns=["Nutriment","Unité","Objectif"])

if "log" not in st.session_state:
    st.session_state["log"] = pd.DataFrame(columns=["date","repas","nom","quantite_g"])  # + nutriments calculés

if "profile" not in st.session_state:
    st.session_state["profile"] = {
        "sexe": "Homme",
        "age": 30,
        "taille_cm": 175,
        "poids_kg": 70,
        "activite": "Modéré (3-5x/sem)",
        "cibles_auto": False,  # si True, calcule TDEE & macros depuis profil
        "repartition_macros": (30, 40, 30),  # P/G/L en %
    }

if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = None

# ==========================
# Barre de titre avec logo
# ==========================
col_logo, col_title = st.columns([1, 6])
with col_logo:
    if st.session_state["logo_bytes"] is not None:
        st.image(st.session_state["logo_bytes"], width=96)
with col_title:
    st.title("TOTEM – Suivi nutrition")

# ==========================
# Sidebar : Import Excel & Logo
# ==========================
st.sidebar.header("📥 Données")
uploaded = st.sidebar.file_uploader("Importe ton Excel (.xlsx)", type=["xlsx"], help="Feuilles attendues : Liste, Cible Macro, Cible micro H/F, Profils (optionnel)")
logo_file = st.sidebar.file_uploader("Logo TOTEM (PNG/JPG)", type=["png","jpg","jpeg"], help="Affiché en haut à gauche")

if logo_file is not None:
    st.session_state["logo_bytes"] = logo_file.read()

if uploaded:
    xls = pd.ExcelFile(uploaded)

    # 1) Liste aliments (3 500 lignes)
    df_liste = safe_parse(xls, "Liste")
    if df_liste is not None and "nom" in df_liste.columns:
        cols = ["nom"] + nutrient_cols(df_liste)
        st.session_state["foods"] = df_liste[cols].copy()
    else:
        st.warning("Feuille 'Liste' non trouvée ou colonne 'nom' absente : utilisation d'une liste vide.")

    # 2) Cibles Macro
    df_macro = safe_parse(xls, "Cible Macro")
    if df_macro is not None and set(["Nutriment","Ojectifs"]).issubset(df_macro.columns):
        tmac = df_macro[["Nutriment","Ojectifs"]].rename(columns={"Ojectifs":"Objectif"}).copy()
        tmac["Objectif"] = coerce_num(tmac["Objectif"])
        st.session_state["targets_macro"] = tmac
    else:
        st.info("Feuille 'Cible Macro' absente — tu peux activer 'Cibles automatiques' via le Profil.")

    # 3) Cibles Micro (selon sexe)
    df_micro_h = safe_parse(xls, "Cible micro H")
    df_micro_f = safe_parse(xls, "Cible micro F")
    df_profile = safe_parse(xls, "Profils")

    # Profil depuis l'onglet (facultatif)
    if df_profile is not None:
        # On essaie de piocher quelques infos standard en ligne 1
        try:
            p = st.session_state["profile"]
            if "sexe" in df_profile.columns:
                p["sexe"] = str(df_profile.loc[0, "sexe"])
            if "age" in df_profile.columns:
                p["age"] = int(coerce_num(df_profile.loc[:, "age"]).iloc[0])
            if "taille_cm" in df_profile.columns:
                p["taille_cm"] = float(coerce_num(df_profile.loc[:, "taille_cm"]).iloc[0])
            if "poids_kg" in df_profile.columns:
                p["poids_kg"] = float(coerce_num(df_profile.loc[:, "poids_kg"]).iloc[0])
            st.session_state["profile"] = p
        except Exception:
            pass

    # On choisira plus bas la bonne feuille micro selon le profil/sexe

# ==========================
# Profil & Cibles
# ==========================
st.sidebar.header("👤 Profil & Cibles")
p = st.session_state["profile"]
p["sexe"] = st.sidebar.selectbox("Sexe", ["Homme","Femme"], index=0 if p["sexe"].lower().startswith("h") else 1)
p["age"] = st.sidebar.number_input("Âge", min_value=10, max_value=100, value=int(p["age"]))
p["taille_cm"] = st.sidebar.number_input("Taille (cm)", min_value=120.0, max_value=230.0, value=float(p["taille_cm"]))
p["poids_kg"] = st.sidebar.number_input("Poids (kg)", min_value=30.0, max_value=250.0, value=float(p["poids_kg"]))
p["activite"] = st.sidebar.selectbox("Activité", ["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"], index=["Sédentaire","Léger (1-3x/sem)","Modéré (3-5x/sem)","Intense (6-7x/sem)","Athlète (2x/jour)"].index(p["activite"]))
p["cibles_auto"] = st.sidebar.checkbox("Utiliser des cibles automatiques (TDEE + % macros)", value=p["cibles_auto"])
st.session_state["profile"] = p

# Si cibles automatiques activées, on écrase targets_macro par un calcul TDEE simple
if p["cibles_auto"]:
    kcal = tdee_mifflin(p["sexe"], p["age"], p["taille_cm"], p["poids_kg"], p["activite"])
    pr, gc, ft = p["repartition_macros"]  # ex 30/40/30
    prot_g = kcal * (pr/100) / 4
    carb_g = kcal * (gc/100) / 4
    fat_g  = kcal * (ft/100) / 9
    st.session_state["targets_macro"] = pd.DataFrame([
        {"Nutriment":"Énergie_kcal","Objectif": round(kcal)},
        {"Nutriment":"Protéines_g","Objectif": round(prot_g)},
        {"Nutriment":"Glucides_g","Objectif": round(carb_g)},
        {"Nutriment":"Lipides_g","Objectif": round(fat_g)},
    ])

# Choix de la table micro selon le sexe (si fichier chargé)
if uploaded:
    xls = pd.ExcelFile(uploaded)
    df_micro = safe_parse(xls, "Cible micro H" if p["sexe"]=="Homme" else "Cible micro F")
    if df_micro is not None and "Nutriment" in df_micro.columns and "Ojectifs" in df_micro.columns:
        tm = df_micro[["Nutriment","Ojectifs"] + (["Unité"] if "Unité" in df_micro.columns else [])].copy()
        tm = tm.rename(columns={"Ojectifs":"Objectif"})
        tm["Objectif"] = coerce_num(tm["Objectif"])
        if "Unité" not in tm.columns: tm["Unité"] = ""
        st.session_state["targets_micro"] = tm

# ==========================
# UI : Saisie Journal (repas)
# ==========================
st.subheader("🧾 Journal du jour (par repas)")

foods = st.session_state["foods"]
targets_macro = st.session_state["targets_macro"]
targets_micro = st.session_state["targets_micro"]

col_filters = st.columns([2, 3, 2, 1, 1])
with col_filters[0]:
    today = st.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY")
with col_filters[1]:
    repas = st.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"])
with col_filters[2]:
    search = st.text_input("Rechercher un aliment (3 500+)", placeholder="ex: yaourt, poulet, riz...")
with col_filters[3]:
    qty = st.number_input("Quantité (g)", min_value=1, value=150, step=10)
with col_filters[4]:
    add_btn = st.button("➕ Ajouter")

# Filtre rapide sur la liste d'aliments (très grande)
if not foods.empty:
    food_list = foods["nom"].astype(str)
    if search:
        mask = food_list.str.contains(search, case=False, na=False)
        filtered = food_list[mask].tolist()
    else:
        filtered = food_list.head(2000).tolist()  # évite un menu déroulant trop lourd
    chosen = st.selectbox("Sélectionne l’aliment", options=filtered if filtered else ["(aucun résultat)"], index=0)
else:
    chosen = st.selectbox("Sélectionne l’aliment", options=["(liste vide)"])

if add_btn and foods is not None and chosen not in ["(aucun résultat)", "(liste vide)"]:
    row = foods.loc[foods["nom"] == chosen]
    if not row.empty:
        row = row.iloc[0]
        calc = calc_from_food_row(row, qty)
        entry = {"date": today, "repas": repas, "nom": chosen, "quantite_g": qty}
        entry.update(calc)
        st.session_state["log"] = pd.concat([st.session_state["log"], pd.DataFrame([entry])], ignore_index=True)
        st.success(f"Ajouté : {qty} g de {chosen} ({repas})")

# Aliment personnalisé
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
# Synthèse & Rapport journalier (par repas)
# ==========================
st.subheader("📊 Rapport journalier")
log = st.session_state["log"]
if not log.empty:
    day_log = log.loc[log["date"] == today].copy()
    if day_log.empty:
        st.caption("Aucune saisie aujourd’hui.")
    else:
        # Totaux par repas
        nutr_cols = [c for c in day_log.columns if c not in ["date","repas","nom","quantite_g"]]
        per_meal = day_log.groupby("repas")[nutr_cols].sum(numeric_only=True).reset_index()
        per_meal_display = per_meal.rename(columns={"Énergie_kcal":"Calories"})
        st.markdown("#### Totaux par repas")
        st.dataframe(per_meal_display, width="stretch")

        # Totaux du jour
        totals = day_log[nutr_cols].sum(numeric_only=True)

        # Récup cibles
        def target_for(nm_regex):
            if targets_macro.empty: return np.nan
            m = targets_macro.loc[targets_macro["Nutriment"].str.contains(nm_regex, case=False, na=False)]
            return float(m["Objectif"].iloc[0]) if not m.empty else np.nan

        kcal = totals.get("Énergie_kcal", np.nan) or totals.get("Energie_kcal", np.nan)
        prot = totals.filter(like="Protéines_g").sum() if "Protéines_g" in totals.index else totals.get("Proteines_g", np.nan)
        carb = totals.get("Glucides_g", np.nan)
        fat  = totals.get("Lipides_g", np.nan)

        t_kcal = target_for("énergie|energie|kcal")
        t_p = target_for("protéines|proteines")
        t_c = target_for("glucides|carb")
        t_f = target_for("lipides|fat|gras")

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Calories", f"{kcal:.0f}" if pd.notna(kcal) else "-", f"/ {t_kcal:.0f}" if pd.notna(t_kcal) else "")
        c2.metric("Protéines (g)", f"{prot:.0f}" if pd.notna(prot) else "-", f"/ {t_p:.0f}" if pd.notna(t_p) else "")
        c3.metric("Glucides (g)", f"{carb:.0f}" if pd.notna(carb) else "-", f"/ {t_c:.0f}" if pd.notna(t_c) else "")
        c4.metric("Lipides (g)", f"{fat:.0f}" if pd.notna(fat) else "-", f"/ {t_f:.0f}" if pd.notna(t_f) else "")

        # Classements (top 5) par repas — par calories
        st.markdown("#### Classements par repas (Top 5 kcal)")
        for rlab in ["Petit-déjeuner","Déjeuner","Dîner","Collation"]:
            sub = day_log.loc[day_log["repas"] == rlab].copy()
            if sub.empty:
                st.caption(f"— {rlab} : (aucune entrée)")
                continue
            sub["kcal"] = sub.get("Énergie_kcal", sub.get("Energie_kcal", 0))
            top = sub.sort_values("kcal", ascending=False)[["nom","quantite_g","kcal"]].head(5)
            st.markdown(f"**{rlab}**")
            st.dataframe(top, width="stretch")

        # Tableaux % objectifs
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
        st.download_button(
            "Télécharger maintenant",
            data=to_excel_bytes(st.session_state["log"]),
            file_name="journal_nutrition.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

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
st.caption("Astuce : importe ton Excel pour remplacer la base d’aliments (feuille 'Liste') et tes cibles ('Cible Macro', 'Cible micro H/F'). "
           "Tu peux aussi activer des cibles automatiques via le Profil.")
