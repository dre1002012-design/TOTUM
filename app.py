# Totum, suivi nutritionnel — WebApp (profil, objectifs, repas, donuts & barres)
# Dépendances : streamlit pandas openpyxl numpy plotly
# Lancer : streamlit run app.py

import io, re, unicodedata
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Totum, suivi nutritionnel", page_icon="🥗", layout="wide")

# ==========================
# Helpers (robustes aux libellés)
# ==========================
def coerce_num(s):
    if s is None: return s
    s = s.astype(str).str.replace("\u00A0"," ", regex=False).str.replace(",",".", regex=False)
    ext = s.str.extract(r"([-+]?\d*\.?\d+)")[0]
    return pd.to_numeric(ext, errors="coerce")

def safe_parse(xls, sheet):
    try: return xls.parse(sheet)
    except Exception: return None

def strip_accents(text: str) -> str:
    text = str(text or "")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

def canon(s: str) -> str:
    """Canonise un libellé : minuscules, pas d’accents, unités/ponctuation supprimées."""
    s = strip_accents(s).lower()
    s = re.sub(r"\((?:mg|ug|µg|mcg|iu|g|kcal|calories?)\)", "", s)  # enlève unités entre ()
    s = s.replace("_100g","").replace("/100g","")
    s = s.replace("%","")
    # synonymes fréquents
    s = s.replace("calories", "kcal").replace("energie", "energie")
    s = s.replace("proteins", "proteines").replace("protides", "proteines")
    s = s.replace("carbs", "glucides").replace("hydrates de carbone", "glucides")
    s = s.replace("fat", "lipides").replace("gras", "lipides")
    s = re.sub(r"[^a-z0-9]+","", s)  # garde alphanum
    return s

def is_energy(name_canon: str) -> bool:
    return ("energie" in name_canon) or ("kcal" in name_canon)

def is_protein(name_canon: str) -> bool:
    return "proteine" in name_canon

def is_carb(name_canon: str) -> bool:
    return "glucide" in name_canon

def is_fat(name_canon: str) -> bool:
    return "lipide" in name_canon

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

def donut(cons, target, title):
    cons = float(cons) if pd.notna(cons) else 0.0
    target = float(target) if pd.notna(target) else 0.0
    if target <= 0:
        # Pas d’objectif -> anneau “info”
        fig = go.Figure(data=[go.Pie(values=[1], labels=["Objectif manquant"], hole=0.6, textinfo="label")])
        fig.update_layout(title=title, margin=dict(l=0,r=0,t=40,b=0), height=260, showlegend=False)
        return fig
    rest = max(target - cons, 0.0)
    vals = [cons, rest]
    labels = ["Ingesté", "Restant"]
    fig = go.Figure(data=[go.Pie(values=vals, labels=labels, hole=0.6, textinfo="percent+label")])
    fig.update_layout(title=title + f" — {cons:.0f}/{target:.0f}", margin=dict(l=0,r=0,t=40,b=0), height=260, showlegend=False)
    return fig

def first_match(total_index, label):
    """Trouve une colonne des totaux qui correspond à label (tolérant)."""
    want = canon(label)
    for k in total_index:
        ck = canon(k)
        if ck == want:  # match strict canonique
            return k
    # fallback par catégorie
    for k in total_index:
        ck = canon(k)
        if is_energy(want) and is_energy(ck): return k
        if is_protein(want) and is_protein(ck): return k
        if is_carb(want) and is_carb(ck): return k
        if is_fat(want) and is_fat(ck): return k
    # fallback par inclusion
    for k in total_index:
        if canon(label).split("g")[0] in canon(k):
            return k
    return None

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
        "sexe":"Homme","age":30,"taille_cm":175.0,"poids_kg":70.0,
        "activite":"Modéré (3-5x/sem)","cibles_auto":False,"repartition_macros":(30,40,30)
    }
if "logo_bytes" not in st.session_state:
    st.session_state["logo_bytes"] = None

# ==========================
# Header
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

    # 1) Liste aliments
    df_liste = safe_parse(xls, "Liste")
    if df_liste is not None and "nom" in df_liste.columns:
        cols = ["nom"] + nutrient_cols(df_liste)
        st.session_state["foods"] = df_liste[cols].copy()
    else:
        st.warning("Feuille 'Liste' introuvable ou colonne 'nom' absente.")

    # 2) Cibles Macro (prioritaires)
    df_macro = safe_parse(xls, "Cible Macro")
    if df_macro is not None and set(["Nutriment","Ojectifs"]).issubset(df_macro.columns):
        tmac = df_macro[["Nutriment","Ojectifs"]].rename(columns={"Ojectifs":"Objectif"}).copy()
        tmac["Objectif"] = coerce_num(tmac["Objectif"])
        st.session_state["targets_macro"] = tmac

    # 3) Cibles Micro selon sexe
    df_micro = safe_parse(xls, "Cible micro H" if p["sexe"]=="Homme" else "Cible micro F")
    if df_micro is not None and "Nutriment" in df_micro.columns and "Ojectifs" in df_micro.columns:
        tm = df_micro[["Nutriment","Ojectifs"] + (["Unité"] if "Unité" in df_micro.columns else [])].copy()
        tm = tm.rename(columns={"Ojectifs":"Objectif"})
        tm["Objectif"] = coerce_num(tm["Objectif"])
        if "Unité" not in tm.columns: tm["Unité"] = ""
        st.session_state["targets_micro"] = tm

# Si cibles auto (et pas de Cible Macro)
if p["cibles_auto"] and (st.session_state["targets_macro"].empty or not uploaded):
    kcal = (10*float(p["poids_kg"]) + 6.25*float(p["taille_cm"]) - 5*int(p["age"]) + (5 if p["sexe"].lower().startswith("h") else -161))
    factors = {"Sédentaire":1.2,"Léger (1-3x/sem)":1.375,"Modéré (3-5x/sem)":1.55,"Intense (6-7x/sem)":1.725,"Athlète (2x/jour)":1.9}
    kcal *= factors.get(p["activite"],1.2)
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
# Saisie : une seule ligne (selectbox avec saisie)
# ==========================
st.subheader("🧾 Journal du jour")
c_date, c_repas, c_qty, c_add = st.columns([1,1,1,1])
today = c_date.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY")
repas = c_repas.selectbox("Repas", ["Petit-déjeuner","Déjeuner","Dîner","Collation"])
qty = c_qty.number_input("Quantité (g)", min_value=1, value=150, step=10)

if not foods.empty:
    chosen = st.selectbox("Aliment (tape pour chercher puis Entrée)", options=foods["nom"].astype(str).tolist())
else:
    chosen = st.selectbox("Aliment", options=["(liste vide)"])

if c_add.button("➕ Ajouter"):
    if chosen not in ["(liste vide)"] and not foods.empty:
        row = foods.loc[foods["nom"]==chosen]
        if not row.empty:
            row = row.iloc[0]
            calc = calc_from_food_row(row, qty)
            entry = {"date": today, "repas": repas, "nom": chosen, "quantite_g": qty}
            entry.update(calc)
            st.session_state["log"] = pd.concat([st.session_state["log"], pd.DataFrame([entry])], ignore_index=True)
            st.success(f"Ajouté : {qty} g de {chosen} ({repas})")

# Aliment personnalisé (optionnel)
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
# Rapport du jour & % objectifs (DONUTS + TABLES + BARRES MICROS)
# ==========================
st.subheader("📊 Rapport journalier & % objectifs")
log = st.session_state["log"]
if not log.empty:
    day = log.loc[log["date"]==today].copy()
    if day.empty:
        st.caption("Aucune saisie aujourd’hui.")
    else:
        nutr_cols = [c for c in day.columns if c not in ["date","repas","nom","quantite_g"]]
        totals = day[nutr_cols].sum(numeric_only=True)

        # Totaux par repas (table)
        per_meal = day.groupby("repas")[nutr_cols].sum(numeric_only=True).reset_index()
        show_meal = per_meal.rename(columns={"Énergie_kcal":"Calories","Energie_kcal":"Calories"})
        st.markdown("#### Totaux par repas")
        st.dataframe(show_meal, width="stretch")

        # ----- Consommations MACROS (robuste via canon) -----
        # On essaie de trouver directement, sinon fallback 4/4/9
        energy_key = None
        protein_key = None
        carb_key = None
        fat_key = None
        for k in totals.index:
            ck = canon(k)
            if energy_key is None and is_energy(ck): energy_key = k
            if protein_key is None and is_protein(ck): protein_key = k
            if carb_key is None and is_carb(ck): carb_key = k
            if fat_key is None and is_fat(ck): fat_key = k

        kcal = float(totals.get(energy_key, np.nan)) if energy_key else np.nan
        prot = float(totals.get(protein_key, np.nan)) if protein_key else np.nan
        carb = float(totals.get(carb_key, np.nan)) if carb_key else np.nan
        fat  = float(totals.get(fat_key, np.nan)) if fat_key else np.nan

        # Fallback énergie = 4P + 4G + 9L si Énergie absente
        if pd.isna(kcal) and (pd.notna(prot) or pd.notna(carb) or pd.notna(fat)):
            kcal = ( (prot if pd.notna(prot) else 0)*4
                   + (carb if pd.notna(carb) else 0)*4
                   + (fat  if pd.notna(fat)  else 0)*9 )

        # ----- Objectifs (prend Cible Macro, sinon auto déjà calculé) -----
        def target_for(regex):
            if targets_macro.empty: return np.nan
            m = targets_macro.copy()
            m["canon"] = m["Nutriment"].map(canon)
            sel = m.loc[m["canon"].str.contains(regex, na=False)]
            return float(sel["Objectif"].iloc[0]) if not sel.empty else np.nan

        t_kcal = target_for("energie|kcal")
        t_p = target_for("proteine")
        t_c = target_for("glucide")
        t_f = target_for("lipide")

        # Métriques
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Calories", f"{(kcal or 0):.0f}", f"/ {t_kcal:.0f}" if pd.notna(t_kcal) else "")
        c2.metric("Protéines (g)", f"{(prot or 0):.0f}", f"/ {t_p:.0f}" if pd.notna(t_p) else "")
        c3.metric("Glucides (g)", f"{(carb or 0):.0f}", f"/ {t_c:.0f}" if pd.notna(t_c) else "")
        c4.metric("Lipides (g)", f"{(fat or 0):.0f}", f"/ {t_f:.0f}" if pd.notna(t_f) else "")

        # Donuts (% objectifs) — plus de “100% par défaut”
        st.markdown("#### 🎯 % d’objectifs (donuts)")
        d1,d2,d3,d4 = st.columns(4)
        d1.plotly_chart(donut(kcal, t_kcal, "Énergie (kcal)"), use_container_width=True)
        d2.plotly_chart(donut(prot, t_p, "Protéines (g)"), use_container_width=True)
        d3.plotly_chart(donut(carb, t_c, "Glucides (g)"), use_container_width=True)
        d4.plotly_chart(donut(fat,  t_f, "Lipides (g)"), use_container_width=True)

        # ----- Tableau % Objectifs – Macros (join via canon) -----
        if not targets_macro.empty:
            m = targets_macro.copy()
            m["canon"] = m["Nutriment"].map(canon)
            # Conso par canon depuis totals
            totals_map = {canon(k): float(v) for k, v in totals.items()}
            m["Consommée"] = m["canon"].map(lambda c:
                totals_map.get(c, 
                    totals_map.get("energiekcal") if is_energy(c) else
                    totals_map.get("proteinesg") if is_protein(c) else
                    totals_map.get("glucidesg") if is_carb(c) else
                    totals_map.get("lipidesg") if is_fat(c) else 0.0
                )
            ).fillna(0.0)
            m["% objectif"] = percent(m["Consommée"], m["Objectif"])
            showM = m[["Nutriment","Objectif","Consommée","% objectif"]]
            st.markdown("#### ⚡ % Objectifs – Macros")
            st.dataframe(showM, width="stretch")

        # ----- Micros : tableau + barres (join via canon) -----
        if not targets_micro.empty:
            tm = targets_micro.copy()
            tm["canon"] = tm["Nutriment"].map(canon)
            totals_map = {canon(k): float(v) for k, v in totals.items()}
            tm["Consommée"] = tm["canon"].map(lambda c: totals_map.get(c, 0.0)).fillna(0.0)
            tm["% objectif"] = percent(tm["Consommée"], tm["Objectif"])
            showm = tm[["Nutriment","Unité","Objectif","Consommée","% objectif"]]
            st.markdown("#### 🧪 Micros – Consommation vs Objectif")
            st.dataframe(showm, width="stretch")

            fig = go.Figure()
            fig.add_bar(name="Consommée", x=showm["Nutriment"], y=showm["Consommée"], text=showm["Consommée"])
            fig.add_bar(name="Objectif",   x=showm["Nutriment"], y=showm["Objectif"],   text=showm["Objectif"], opacity=0.4)
            fig.update_layout(barmode="group", title="Micronutriments – Consommée vs Objectif", xaxis_tickangle=-30,
                              height=420, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig, use_container_width=True)
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
st.caption("Astuce : pour des objectifs venant de ton fichier, fournis 'Cible Macro'. Sinon, active les cibles automatiques (Profil).")
