import streamlit as st
from supabase import create_client
import stripe

# --- Configuration Supabase & Stripe ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
STRIPE_API_KEY = st.secrets["STRIPE_API_KEY"]
STRIPE_PRICE_ID = st.secrets["STRIPE_PRICE_ID"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
stripe.api_key = STRIPE_API_KEY

st.set_page_config(page_title="Totum - Connexion", page_icon="🌿")

# --- Interface principale ---
st.title("🌿 Bienvenue sur Totum")
st.write("Connecte-toi ou crée un compte pour continuer.")

# --- Choix : connexion ou inscription ---
choice = st.radio("Que veux-tu faire ?", ["Se connecter", "Créer un compte"])

email = st.text_input("Email")
password = st.text_input("Mot de passe", type="password")

if choice == "Créer un compte":
    if st.button("Créer mon compte"):
        try:
            response = supabase.auth.sign_up({"email": email, "password": password})
            st.success("✅ Compte créé ! Vérifie ton email pour activer ton compte.")
        except Exception as e:
            st.error(f"Erreur : {e}")

elif choice == "Se connecter":
    if st.button("Se connecter"):
        try:
            user = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if user:
                st.success(f"Bienvenue {email} 👋")

                # Vérification abonnement Stripe (à venir)
                st.write("Ton espace utilisateur s'affichera ici.")
            else:
                st.error("Identifiants incorrects.")
        except Exception as e:
            st.error(f"Erreur : {e}")

st.write("---")
st.caption("Version test — connexion Supabase uniquement pour l'instant.")
