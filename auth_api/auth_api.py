# auth_api.py
# API simple pour créer la session de paiement et lire l'état d'abonnement.
# Cette version :
# - envoie l'user_id à Stripe (client_reference_id + metadata)
# - ajoute /success comme filet de sécurité pour mettre à jour Supabase après paiement
# - lit toutes les clés dans .env (PAS de clé en dur)

import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv
import stripe

from supabase import create_client

load_dotenv()  # lit auth_api/.env

# Récupération des variables d'environnement
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:5001")  # page de retour
PORT = int(os.getenv("PORT", "5001"))
PRICE_ID = os.getenv("PRICE_ID")  # optionnel : si tu as créé un Price Stripe fixe

# Vérifs minimum pour éviter les surprises
missing = []
if not SUPABASE_URL: missing.append("SUPABASE_URL")
if not SUPABASE_SERVICE_ROLE_KEY: missing.append("SUPABASE_SERVICE_ROLE_KEY (ou SUPABASE_KEY)")
if not STRIPE_SECRET_KEY: missing.append("STRIPE_SECRET_KEY")
if missing:
    raise RuntimeError("Variables manquantes dans .env : " + ", ".join(missing))

# Init clients
stripe.api_key = STRIPE_SECRET_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = Flask(__name__)

def _update_profile_lifetime(user_id: str):
    """Met is_lifetime=True + lifetime_since maintenant pour le profil donné."""
    lifetime_since = datetime.now(timezone.utc).isoformat()
    try:
        resp = supabase.table("profiles").update({
            "is_lifetime": True,
            "lifetime_since": lifetime_since
        }).eq("id", user_id).execute()

        data = getattr(resp, "data", resp)
        if isinstance(data, list) and len(data) > 0:
            app.logger.info(f"[SUPABASE] Profil {user_id} mis à jour.")
            return True
        else:
            app.logger.warning(f"[SUPABASE] Aucune ligne modifiée pour {user_id}. Réponse: {data}")
            return False
    except Exception as e:
        app.logger.error(f"[SUPABASE] Erreur maj profil {user_id}: {e}")
        return False

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    """Crée la session Stripe en y joignant l'user_id."""
    try:
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id")
        if not user_id:
            return jsonify(error="user_id manquant"), 400

        # URLs de retour (succès et annulation)
        success_url = f"{APP_DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{APP_DOMAIN}/cancel"

        # Ligne d'achat : au choix un PRICE_ID existant, sinon un prix inline à 2,99 €
        if PRICE_ID:
            line_items = [{"price": PRICE_ID, "quantity": 1}]
        else:
            line_items = [{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": "Totum – abonnement à vie"},
                    "unit_amount": 299  # 2,99 € (centimes)
                },
                "quantity": 1
            }]

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=user_id,         # 🔑 passe l'user_id ici
            metadata={"user_id": user_id}        # 🔑 et aussi ici (double filet)
        )

        return jsonify({"id": session.id, "url": session.url})
    except Exception as e:
        app.logger.error(f"[STRIPE] Erreur création session: {e}")
        return jsonify(error=str(e)), 500

@app.route("/subscription-status/<user_id>", methods=["GET"])
def subscription_status(user_id):
    """Retourne is_lifetime et lifetime_since pour l'utilisateur."""
    try:
        resp = supabase.table("profiles") \
            .select("is_lifetime,lifetime_since") \
            .eq("id", user_id) \
            .execute()
        data = getattr(resp, "data", [])
        if isinstance(data, list) and data:
            row = data[0]
            return jsonify(
                is_lifetime=bool(row.get("is_lifetime")),
                lifetime_since=row.get("lifetime_since")
            )
        else:
            return jsonify(is_lifetime=False, lifetime_since=None)
    except Exception as e:
        app.logger.error(f"[SUPABASE] Erreur lecture statut: {e}")
        return jsonify(error="lecture_statut_impossible"), 500

@app.route("/success", methods=["GET"])
def success():
    """
    Page de succès.
    Filet de sécurité : on relit la session Stripe, on récupère user_id,
    et on met à jour Supabase ici aussi (en plus du webhook).
    """
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return "Session_id manquant", 400

        session = stripe.checkout.Session.retrieve(session_id)
        user_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")

        if not user_id:
            return "Paiement OK, mais impossible d’identifier l’utilisateur (user_id manquant).", 200

        _update_profile_lifetime(user_id)
        return "Paiement confirmé. Abonnement activé. Vous pouvez fermer cette page.", 200
    except Exception as e:
        app.logger.error(f"[SUCCESS] Erreur: {e}")
        return f"Erreur: {e}", 200

@app.route("/cancel", methods=["GET"])
def cancel():
    return "Paiement annulé. Vous pouvez fermer cette page.", 200

if __name__ == "__main__":
    print(f"Lancement auth_api sur le port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
