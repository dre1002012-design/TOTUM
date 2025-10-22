# pages/01_Statut_abonnement.py
# Page Statut qui lit automatiquement le user_id mémorisé (00_Connexion).
# Si absent, utilise un user_id de démo et permet de le saisir.

import time
import requests
import streamlit as st

st.set_page_config(page_title="Statut abonnement", page_icon="💳", layout="centered")
st.title("💳 Statut de votre abonnement Totum")

# 👉 API en ligne (Render)
AUTH_API_BASE = "https://totum.onrender.com"

# Si un user_id est mémorisé (via 00_Connexion), on l'utilise
session_uid = st.session_state.get("user_id")

# Sinon on propose un champ + une valeur de démo
DEFAULT_USER_ID = "d583cd6f-649f-41f3-8186-ba4073f2fb03"

if session_uid:
    st.caption(f"Utilisateur mémorisé : `{session_uid}`")
    user_id = session_uid
else:
    st.info("Aucun utilisateur mémorisé. Collez un user_id ou utilisez la page « 00_Connexion ».")
    with st.form("user_form"):
        user_id = st.text_input("Identifiant utilisateur (user_id)", value=DEFAULT_USER_ID)
        st.form_submit_button("Vérifier le statut")

TIMEOUT_S = 40
RETRY_DELAY = 3

def _safe_get(url: str):
    try:
        r = requests.get(url, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except Exception:
        time.sleep(RETRY_DELAY)
        r = requests.get(url, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()

def _safe_post(url: str, json_payload: dict):
    try:
        r = requests.post(url, json=json_payload, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except Exception:
        time.sleep(RETRY_DELAY)
        r = requests.post(url, json=json_payload, timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()

def get_status(uid: str):
    try:
        return _safe_get(f"{AUTH_API_BASE}/subscription-status/{uid}")
    except Exception as e:
        st.error(f"Impossible de récupérer le statut pour le moment. Réessayez dans quelques secondes.\nDétail: {e}")
        return {"is_lifetime": False, "lifetime_since": None}

def create_checkout(uid: str):
    try:
        return _safe_post(f"{AUTH_API_BASE}/create-checkout-session", {"user_id": uid})
    except Exception as e:
        st.error(f"Création du lien de paiement impossible. Réessayez dans quelques secondes.\nDétail: {e}")
        return None

status = get_status(user_id)

if status.get("is_lifetime"):
    st.success("🎉 Abonnement à vie actif ✅")
    since = status.get("lifetime_since")
    if since:
        st.caption(f"Activé le : {since}")
else:
    st.warning("Abonnement non actif.")
    st.write("Clique ci-dessous pour acheter l’abonnement à vie (2,99 € – mode test).")
    if st.button("Générer le lien de paiement"):
        data = create_checkout(user_id)
        if data and data.get("url"):
            st.markdown(f"[➡️ Ouvrir la page de paiement Stripe]({data['url']})", unsafe_allow_html=True)
            st.info("Utilise la carte test 4242 4242 4242 4242 — date future — CVC 123.")
        else:
            st.error("Pas d’URL de paiement reçue.")
