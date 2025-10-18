# pages/00_Accueil.py
# Petite page d'accueil qui affiche un bandeau "abonnement actif" (depuis l'API en ligne)
import requests
import streamlit as st

st.set_page_config(page_title="Totum - Accueil", page_icon="🍏", layout="wide")
st.title("🍏 Totum — Accueil")

# ⚠️ ID de test pour l’instant. Plus tard, on mettra l’ID réel de l’utilisateur connecté.
USER_ID = "d583cd6f-649f-41f3-8186-ba4073f2fb03"

AUTH_API_BASE = "https://totum.onrender.com"

# Lecture du statut (avec petit filet de sécurité)
def get_status(uid: str):
    try:
        r = requests.get(f"{AUTH_API_BASE}/subscription-status/{uid}", timeout=40)
        r.raise_for_status()
        return r.json()
    except Exception:
        # 2e essai si Render se réveille
        r = requests.get(f"{AUTH_API_BASE}/subscription-status/{uid}", timeout=40)
        r.raise_for_status()
        return r.json()

status = get_status(USER_ID)

# Bandeau
if status.get("is_lifetime"):
    st.success("🎉 Abonnement à vie actif ✅")
else:
    st.warning("Abonnement non actif. Rendez-vous dans la page **Statut abonnement** pour acheter l’accès à vie (2,99 € – mode test).")

st.divider()
st.caption("Astuce : vous pouvez toujours vérifier/acheter dans la page « Statut abonnement » du menu.")
