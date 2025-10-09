# test_connections.py
# Petit test temporaire : vérifie que Streamlit lit bien les secrets,
# que Stripe peut retrouver le price_id et que Supabase répond via service_role.
# -> NE PAS laisser ce fichier en production plus longtemps ; c'est uniquement un test.

import streamlit as st
from supabase import create_client
import stripe

st.set_page_config(page_title="Test Connexions - Totum", layout="centered")

st.title("Test connexions : Supabase & Stripe (temporaire)")

# 1) lecture sécurisée des secrets (ne pas afficher les valeurs)
missing = []
for key in ["SUPABASE_URL","SUPABASE_ANON_KEY","SUPABASE_SERVICE_ROLE_KEY","STRIPE_SECRET_KEY","STRIPE_PRICE_ID"]:
    if key not in st.secrets:
        missing.append(key)
if missing:
    st.error("Il manque ces secrets dans Streamlit Cloud : " + ", ".join(missing))
    st.stop()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
STRIPE_SECRET_KEY = st.secrets["STRIPE_SECRET_KEY"]
STRIPE_PRICE_ID = st.secrets["STRIPE_PRICE_ID"]

st.write("Secrets trouvés — lancement des tests (les clés ne sont pas affichées).")

# Test Stripe : récupérer le Price (utilise la clé secrète)
stripe.api_key = STRIPE_SECRET_KEY
try:
    price = stripe.Price.retrieve(STRIPE_PRICE_ID)
    st.success(f"Stripe OK — Price trouvé : {price.get('id')}")
    # afficher quelques métadonnées utiles mais sans rien de sensible :
    st.write("Montant (display):", price.get("unit_amount") or price.get("unit_amount_decimal") or "non disponible")
    st.write("Devise :", price.get("currency"))
except Exception as e:
    st.error("Erreur Stripe : " + str(e))

# Test Supabase : connexion avec service_role (server-side)
try:
    svc = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    # on exécute une requête simple (ne renvoie pas de données sensibles ici)
    res = svc.from_("purchases").select("id").limit(1).execute()
    # Le client supabase renvoie un objet; on inspecte pour état sans afficher de secrets
    if hasattr(res, "error") and res.error:
        st.error("Supabase : erreur dans la requête (response.error) : " + str(res.error))
    else:
        st.success("Supabase OK — connexion établie (service_role fonctionne).")
except Exception as e:
    st.error("Erreur connexion Supabase : " + str(e))

st.info("Quand tout est OK, supprime ce fichier `test_connections.py` et/ou retire ce test du déploiement.")
