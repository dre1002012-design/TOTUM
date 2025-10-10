# debug_stripe.py — debug temporaire, supprimer après usage
import streamlit as st
import stripe

st.title("DEBUG Stripe (temporaire)")

# lister les clés présentes
st.write("Clés présentes dans st.secrets :", list(st.secrets.keys()))

# afficher les 4 derniers caractères de la clé (NE PAS révéler la clé entière)
if "STRIPE_SECRET_KEY" in st.secrets:
    k = st.secrets["STRIPE_SECRET_KEY"]
    st.write("STRIPE_SECRET_KEY endswith:", k[-6:])
else:
    st.write("STRIPE_SECRET_KEY absent")

# tester la récupération du price
if "STRIPE_SECRET_KEY" in st.secrets:
    stripe.api_key = st.secrets["STRIPE_SECRET_KEY"]
    try:
        price = stripe.Price.retrieve("price_1SGcQeQvwZymPO1MOWT1uizM")
        st.success("Stripe OK — price found: " + price["id"])
        st.write("amount:", price.get("unit_amount"), price.get("currency"), "type:", price.get("type"))
    except Exception as e:
        st.error("Stripe API error: " + str(e))
else:
    st.error("Impossible de tester Stripe : STRIPE_SECRET_KEY manquante")
