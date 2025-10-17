# auth_api/webhook_server.py
"""
Webhook server sécurisé :
- lit STRIPE_SECRET_KEY et STRIPE_WEBHOOK_SECRET et SUPABASE_SERVICE_ROLE_KEY depuis .env
- écoute POST /webhook
- sur checkout.session.completed : met à jour profiles.is_lifetime = true dans Supabase
"""

import os
import stripe
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime, timezone

# Supabase client
from supabase import create_client

load_dotenv()  # lit auth_api/.env

app = Flask(__name__)

# Charger les clés depuis .env
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Vérifications simples
missing = []
if not STRIPE_SECRET_KEY:
    missing.append("STRIPE_SECRET_KEY")
if not STRIPE_WEBHOOK_SECRET:
    missing.append("STRIPE_WEBHOOK_SECRET")
if not SUPABASE_URL:
    missing.append("SUPABASE_URL")
if not SUPABASE_SERVICE_ROLE_KEY:
    missing.append("SUPABASE_SERVICE_ROLE_KEY")

if missing:
    raise RuntimeError("Variables manquantes dans .env : " + ", ".join(missing))

# Init clients
stripe.api_key = STRIPE_SECRET_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
WEBHOOK_SECRET = STRIPE_WEBHOOK_SECRET

@app.route("/webhook", methods=["POST"])
def webhook_received():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    # vérifier la signature Stripe
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except ValueError:
        app.logger.error("Invalid payload")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        app.logger.error("Invalid signature")
        return "Invalid signature", 400
    except Exception as e:
        app.logger.error(f"Erreur vérif signature: {e}")
        return "Error", 400

    # Traitement pour checkout.session.completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # essayer de récupérer l'user_id envoyé par create-checkout-session
        user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
        session_id = session.get("id")
        customer_email = session.get("customer_email")  # parfois None en mode test

        app.logger.info(f"Webhook reçu: checkout.session.completed session_id={session_id} user_id={user_id}")

        if not user_id:
            app.logger.warning("Aucun user_id trouvé dans la session. Impossible de mettre à jour le profil.")
            return jsonify(success=True), 200  # on retourne 200 pour éviter retries massif

        # Préparer la date actuelle (UTC) pour lifetime_since
        lifetime_since = datetime.now(timezone.utc).isoformat()

        # Tenter de mettre à jour Supabase
        try:
            resp = supabase.table("profiles").update({
                "is_lifetime": True,
                "lifetime_since": lifetime_since
            }).eq("id", user_id).execute()

            # La lib supabase renvoie un objet; on logge ce qui est utile
            status = getattr(resp, "status_code", None)
            data = getattr(resp, "data", resp)

            app.logger.info(f"Supabase update response status={status} data={data}")

            # Vérifier que la mise à jour a bien modifié au moins une ligne
            # resp.data contient la ligne modifiée si ok
            if isinstance(data, list) and len(data) > 0:
                app.logger.info(f"Profil {user_id} mis à jour en is_lifetime=True")
            else:
                # si pas de data, on le log pour investigation
                app.logger.warning(f"Aucune ligne modifiée pour user_id={user_id}. Réponse: {data}")

        except Exception as e:
            app.logger.error(f"Erreur lors de la mise à jour Supabase pour user {user_id} : {e}")
            # On renvoie 200 pour éviter que Stripe répète trop souvent, mais on a log l'erreur
            return jsonify(success=False, error=str(e)), 200

    # Toujours retourner 200 si tout s'est bien passé côté réception (sinon Stripe renverra retries)
    return jsonify(success=True), 200

if __name__ == "__main__":
    # port 4242 (cohérent avec stripe listen --forward-to localhost:4242/webhook)
    app.run(port=4242)
