# components/journal_embed.py
# Journal compact "prêt-à-brancher" dans app.py, sans toucher au Bilan.
from __future__ import annotations
from datetime import date
import streamlit as st

from components.food_search import render_food_search, Choice
from db_journal import (
    add_journal_entry, read_totals_for_day, delete_last_for_day,
    add_favorite, remove_favorite, list_favorites, read_entries_for_day,
)

# --- outils internes ---
def _handle_choice(rep: str, choice: Choice):
    add_journal_entry(
        repas=rep,
        nom=choice.food.name,
        quantite_g=int(choice.grams),
        kcal100=float(choice.food.kcal),
        carbs100=float(choice.food.carbs),
        prot100=float(choice.food.prot),
        fat100=float(choice.food.fat),
        jour_iso=date.today().isoformat(),
    )
    st.success(f"✅ {choice.food.name} → {rep} ({choice.grams} g)")
    st.rerun()

def _render_favorites():
    st.subheader("⭐ Favoris")
    favs = list_favorites()
    if not favs:
        st.caption("Aucun favori pour le moment.")
        return

    repas_quick = st.selectbox("Ajouter dans :", ["Petit-déj", "Déjeuner", "Dîner", "Collation"], index=1, key="embed_fav_meal")
    cols = st.columns(2)
    for i, name in enumerate(favs):
        with cols[i % 2]:
            if st.button(f"➕ {name}", key=f"embed_fav_add_{i}"):
                # On réutilisera l’ajout rapide via recherche
                # (le module food_search lit déjà les valeurs depuis foods.csv)
                # Ici on ajoute 100 g par défaut.
                add_journal_entry(repas_quick, name, 100, 0, 0, 0, 0, date.today().isoformat())
                # NB: les vraies valeurs (kcal/macros) arrivent quand on passe par la recherche;
                # si tu veux des favoris "riches", on pourra stocker kcal/carbs/prot/fat dans la table favorites.
                st.success(f"✅ {name} → {repas_quick} (100 g)")
                st.rerun()

def _render_custom_creator():
    st.subheader("🧪 Créer un aliment personnalisé")
    st.caption("Exemple : Smoothie maison, Salade poulet… (valeurs /100 g)")
    with st.form("embed_custom_food"):
        c1,c2 = st.columns([2,1])
        name  = c1.text_input("Nom de l’aliment")
        grams = c2.number_input("Quantité (g)", 10, 2000, 200, 10)
        cc1,cc2,cc3,cc4 = st.columns(4)
        kcal100 = cc1.number_input("Énergie (kcal/100g)", 0.0, 2000.0, 60.0, 1.0)
        carb100 = cc2.number_input("Glucides (g/100g)",    0.0, 1000.0, 12.0, 0.5)
        prot100 = cc3.number_input("Protéines (g/100g)",   0.0, 1000.0, 2.0, 0.5)
        fat100  = cc4.number_input("Lipides (g/100g)",     0.0, 1000.0, 1.0, 0.5)
        meal = st.selectbox("Ajouter à :", ["Petit-déj","Déjeuner","Dîner","Collation"], index=1, key="embed_custom_meal")
        ok = st.form_submit_button("➕ Ajouter (perso)")
        if ok:
            if not name.strip():
                st.warning("Donne un nom à l’aliment.")
            else:
                add_journal_entry(meal, name.strip(), float(grams), float(kcal100), float(carb100), float(prot100), float(fat100), date.today().isoformat())
                st.success(f"✅ {name} → {meal} ({int(grams)} g)")
                st.rerun()

def _render_today_list():
    st.subheader("🧾 Journal du jour")
    rows = read_entries_for_day(date.today().isoformat())
    if not rows:
        st.info("Aucune ligne enregistrée aujourd’hui.")
        return
    for e in rows:
        st.write(f"• [{e['repas']}] {e['nom']} — {int(e['q'])} g — {int(e['k'])} kcal")

# --- API exposée : à appeler depuis app.py ---
def render_journal_embed():
    st.markdown("""
    <style>
    div.stButton > button {
      background-color:#ff8c00 !important; color:#fff !important; border:0 !important;
      border-radius:8px !important; font-weight:700 !important; padding:.28rem .7rem !important;
    }
    .compact-row { padding: 4px 0; border-bottom: 1px dashed #eee; font-size:.95rem; }
    .compact-row:last-child { border-bottom: none; }
    </style>
    """, unsafe_allow_html=True)

    # Barre “résumé” ultra-légère (kcal/macros du jour) — lecture DB seulement
    tot = read_totals_for_day(date.today().isoformat())
    k, c, p, f = int(round(tot["kcal"])), round(tot["carbs"],1), round(tot["prot"],1), round(tot["fat"],1)
    st.caption(f"🗓️ Aujourd’hui — {k} kcal • {p} g prot • {c} g gluc • {f} g lip")

    # 4 onglets de repas avec recherche “compacte”
    tab1, tab2, tab3, tab4 = st.tabs(["🥐 Petit-déj", "🍽️ Déjeuner", "🍲 Dîner", "🍎 Collation"])
    with tab1:
        choice = render_food_search("embed_pdj")
        if choice: _handle_choice("Petit-déj", choice)
    with tab2:
        choice = render_food_search("embed_dej")
        if choice: _handle_choice("Déjeuner", choice)
    with tab3:
        choice = render_food_search("embed_din")
        if choice: _handle_choice("Dîner", choice)
    with tab4:
        choice = render_food_search("embed_col")
        if choice: _handle_choice("Collation", choice)

    # Annuler le dernier ajout
    if st.button("↩ Annuler le dernier ajout", key="embed_undo"):
        if delete_last_for_day(date.today().isoformat()):
            st.success("Dernier ajout supprimé.")
        else:
            st.info("Aucun ajout aujourd’hui.")
        st.rerun()

    # Favoris + création personnalisée + liste du jour
    _render_favorites()
    _render_custom_creator()
    _render_today_list()
