# pages/00_Connexion.py
# Page très simple : l'utilisateur colle son user_id Supabase.
# On le mémorise dans st.session_state['user_id'] pour l'utiliser partout.

import requests
import streamlit as st

st.set_page_config(page_title="Connexion", page_icon="👤", layout="centered")
st.title("👤 Connexion à Totum (simple)")

API_BASE = "https://totum.onrender.com"  # ton API en ligne

# Champ pour coller un user_id (depuis Supabase → Authentication → Users)
user_id_input = st.text_input("Votre identifiant (user_id Supabase)")

col1, col2 = st.columns(2)
with col1:
    if st.button("Se connecter"):
        if not user_id_input.strip():
            st.error("Merci de coller un user_id valide (format UUID).")
        else:
            st.session_state["user_id"] = user_id_input.strip()
            st.success("Connecté ! Votre user_id est mémorisé pour cette session.")

with col2:
    if st.button("Se déconnecter"):
        st.session_state.pop("user_id", None)
        st.info("Déconnecté. Aucun user_id en mémoire.")

st.divider()

# Affichage de l'état courant
current = st.session_state.get("user_id")
if current:
    st.success(f"Utilisateur connecté : `{current}`")
    # Petit test de statut pour rassurer :
    try:
        r = requests.get(f"{API_BASE}/subscription-status/{current}", timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get("is_lifetime"):
            st.write("🎉 Abonnement à vie **actif** ✅")
        else:
            st.write("Abonnement **non actif**.")
    except Exception as e:
        st.warning(f"Impossible de vérifier le statut pour le moment : {e}")
else:
    st.info("Collez votre user_id puis cliquez sur **Se connecter**.")
