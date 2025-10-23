"""
tabs/profile_tab.py — UI de l’onglet Profil
"""

import streamlit as st
from calorie_app.core.data import save_profile
from calorie_app.core.calc import excel_like_targets
from calorie_app.core.utils import round1


def render_profile_tab(load_profile_func):
    """Affiche le profil utilisateur et les objectifs clés."""
    st.subheader("👤 Profil")
    p = st.session_state["profile"]

    c1, c2, c3, c4 = st.columns(4)
    p["sexe"] = c1.selectbox("Sexe", ["Homme", "Femme"], index=0 if p["sexe"].startswith("H") else 1)
    p["age"] = int(c2.number_input("Âge", min_value=10, max_value=100, value=int(p["age"]), step=1))
    p["taille_cm"] = int(c3.number_input("Taille (cm)", min_value=120, max_value=230, value=int(p["taille_cm"]), step=1))
    p["poids_kg"] = int(c4.number_input("Poids (kg)", min_value=30, max_value=250, value=int(p["poids_kg"]), step=1))
    p["activite"] = st.selectbox(
        "Activité",
        ["Sédentaire", "Léger (1-3x/sem)", "Modéré (3-5x/sem)", "Intense (6-7x/sem)", "Athlète (2x/jour)"],
        index=["Sédentaire", "Léger (1-3x/sem)", "Modéré (3-5x/sem)", "Intense (6-7x/sem)", "Athlète (2x/jour)"].index(p["activite"])
    )

    st.session_state["profile"] = p

    if st.button("💾 Sauver mon profil"):
        save_profile(p)
        st.success("Profil enregistré.")

    profile_targets = excel_like_targets(p)
    st.markdown("#### 🎯 Objectifs clés (calculés)")
    kc, pr, gl, li, fi = st.columns(5)
    kc.metric("Énergie (kcal)", f"{profile_targets['energie_kcal']:.1f}")
    pr.metric("Protéines (g)", f"{profile_targets['proteines_g']:.1f}")
    gl.metric("Glucides (g)", f"{profile_targets['glucides_g']:.1f}")
    li.metric("Lipides (g)",   f"{profile_targets['lipides_g']:.1f}")
    fi.metric("Fibres (g)",    f"{profile_targets['fibres_g']:.1f}")
