"""
core/state.py — initialisation douce de st.session_state (aucun effet visuel)
"""

from pathlib import Path
import streamlit as st
import pandas as pd

# Chemin du dossier assets (logo, etc.)
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_LOGO_PATH = ASSETS_DIR / "logo.png"

def reload_default_logo():
    """Charge le logo par défaut dans la session si disponible."""
    try:
        if DEFAULT_LOGO_PATH.exists():
            st.session_state["logo_bytes"] = DEFAULT_LOGO_PATH.read_bytes()
    except Exception:
        # on ignore toute erreur de lecture ici
        pass

def get_logo_b64() -> str | None:
    """Retourne le logo en base64 si présent dans la session (sinon None)."""
    try:
        import base64
        data = st.session_state.get("logo_bytes", None)
        if not data and DEFAULT_LOGO_PATH.exists():
            data = DEFAULT_LOGO_PATH.read_bytes()
        return base64.b64encode(data).decode() if data else None
    except Exception:
        return None

def ensure_session_defaults(load_profile_func):
    """
    Initialise proprement les clés de session.
    - load_profile_func: fonction à appeler pour charger le profil (ex: core.data.load_profile)
    """
    if "foods" not in st.session_state:
        st.session_state["foods"] = pd.DataFrame(columns=["nom"])
    if "targets_micro" not in st.session_state:
        st.session_state["targets_micro"] = pd.DataFrame()
    if "targets_macro" not in st.session_state:
        st.session_state["targets_macro"] = pd.DataFrame()
    if "logo_bytes" not in st.session_state:
        st.session_state["logo_bytes"] = None
    if "profile" not in st.session_state:
        try:
            st.session_state["profile"] = load_profile_func()
        except Exception:
            # fallback très simple
            st.session_state["profile"] = {
                "sexe":"Homme","age":40,"taille_cm":181.0,"poids_kg":72.0,
                "activite":"Sédentaire","repartition_macros":(30,55,15)
            }
    if "last_added_date" not in st.session_state:
        st.session_state["last_added_date"] = None
