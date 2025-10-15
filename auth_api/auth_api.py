# auth_api/auth_api.py
"""
Petit serveur Flask pour :
- créer une session Stripe Checkout (paiement à vie 2,99€)
- recevoir le webhook Stripe et marquer l'utilisateur en 'lifetime' dans Supabase
- vérifier le statut d'abonnement d'un utilisateur

Mode d'emploi rapide :
1) Installer dépendances: pip install -r requirements.txt
2) Créer un fichier .env à partir de .env.example et remplir les clés réelles.
3) Lancer: python auth_api.py
4) Exposer en public (ngrok) pour tester webhooks Stripe si en local.
"""

import os
import json
from datetime import datetime

from flask import Flask, request, jsonify, abort
import stripe
import requests
from dotenv import load_dotenv

# Chargement des variables d'environnement depuis .env (local uniquement)
load_dotenv()

# Variables (remplir dans .env)
SUPABASE_URL = os.getenv("SUPABASE_URL")  # ex: https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:5000")
PORT = int(os.getenv("PORT", 5001))

# Vérifications simples
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Variables SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY doivent être définies dans .env")
if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
    raise RuntimeError("STRIPE_SECRET_KEY et STRIPE_WEBHOOK_SECRET doivent être définies dans .env")

stripe.api_key = STRIPE_SECRET_KEY

app = Flask(__name__)

# ----------------------
# Helper: appeler Supabase (REST)
# ----------------------
def supabase_patch_profile(user_id, patch_data):
    """
    Met à jour la table profiles pour l'utilisateur user_id.
    patch_data doit être un dict avec les champs à mettre à jour.
    """
    url = f"{SUPABASE_URL}/rest/v1/profiles"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        # Demande à Supabase de retourner la ligne modifiée
        "Prefer": "return=representation"
    }
    params = {"id": f"eq.{user_id}"}
    # Supabase REST PATCH : on envoie PATCH vers /profiles?id=eq.<user_id>
    response = requests.patch(url, params=params, headers=headers, json=patch_data)
    if response.status_code not in (200, 201):
        # Si erreur, on renvoie le message pour debug
        raise RuntimeError(f"Erreur Supabase PATCH: {response.status_code} - {response.text}")
    return response.json()

def supabase_insert_payment(payment_row):
    """
    Ajoute une ligne dans la table payments.
    payment_row : dict avec les champs (user_id, stripe_payment_intent_id, amount, currency, status, ...)
    """
    url = f"{SUPABASE_URL}/rest/v1/payments"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    response = requests.post(url, headers=headers, json=payment_row)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Erreur Supabase INSERT payment: {response.status_code} - {response.text}")
    return response.json()

# ----------------------
# Endpoint: créer une session Stripe Checkout
# ----------------------
@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    """
    Attendu JSON en entrée : { "user_id": "<id_supabase_user>" }
    Retourne : { "url": "<stripe_checkout_url>" }
    """
    data = request.get_json(silent=True)
    if not data or "user_id" not in data:
        return jsonify({"error": "Veuillez envoyer JSON avec user_id"}), 400

    user_id = data["user_id"]

    try:
        # Si tu as créé un Price dans Stripe pour 2.99€, tu peux utiliser son ID (recommandé).
        # Ici on crée un line_item avec price_data pour être sûr que ça marche sans ID de price.
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            # Prix en centimes : 2.99 EUR => 299
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": "Totum — Abonnement à vie",
                    },
                    "unit_amount": 299
                },
                "quantity": 1
            }],
            success_url=f"{APP_DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_DOMAIN}/cancel",
            # Renvoyer l'id utilisateur pour relier le paiement à l'utilisateur
            client_reference_id=user_id,
            metadata={"user_id": user_id}
        )
        return jsonify({"url": session.url, "id": session.id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------
# Endpoint: webhook Stripe (pour recevoir l'événement paiement réussi)
# ----------------------
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    # Lire payload brut et header de signature
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", None)
    if sig_header is None:
        return "Missing signature", 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return "Signature verification failed", 400
    except Exception as e:
        return f"Webhook error: {str(e)}", 400

    # Traiter l'événement
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Récupère user_id (on l'a mis dans client_reference_id et/ou metadata)
        user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
        payment_intent = session.get("payment_intent")
        amount_total = session.get("amount_total")  # en centimes
        currency = session.get("currency", "eur")
        status = session.get("payment_status", "unknown")

        # On met à jour Supabase : is_lifetime = true, lifetime_since = now
        try:
            # 1) Insérer la ligne payment pour l'historique (optionnel mais utile)
            payment_row = {
                "user_id": user_id,
                "stripe_payment_intent_id": payment_intent,
                "stripe_checkout_session_id": session.get("id"),
                "amount": (amount_total / 100) if amount_total else None,
                "currency": currency,
                "status": status,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            supabase_insert_payment(payment_row)
        except Exception as e:
            # on continue même si l'insert échoue, mais log l'erreur
            print("Warning: impossible d'insérer payment:", e)

        try:
            patch_data = {
                "is_lifetime": True,
                "lifetime_since": datetime.utcnow().isoformat() + "Z"
            }
            updated = supabase_patch_profile(user_id, patch_data)
            print("Profil mis à jour pour user:", user_id, "->", updated)
        except Exception as e:
            print("Erreur lors de la mise à jour Supabase:", e)
            # Ne pas renvoyer 500 à Stripe : renvons 200 pour éviter re-tentatives infinies.
            return jsonify({"received": True, "error": str(e)}), 200

    # Pour tous les autres événements, on répond simplement 200
    return jsonify({"received": True}), 200

# ----------------------
# Endpoint: vérifier le statut d'abonnement
# ----------------------
@app.route("/subscription-status/<user_id>", methods=["GET"])
def subscription_status(user_id):
    """
    Récupère le profil depuis Supabase pour savoir si is_lifetime est vrai.
    """
    url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
    }
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return jsonify({"error": "Impossible de récupérer le profil", "details": r.text}), 500
    rows = r.json()
    if not rows:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    profile = rows[0]
    is_lifetime = profile.get("is_lifetime", False)
    lifetime_since = profile.get("lifetime_since", None)
    return jsonify({"is_lifetime": bool(is_lifetime), "lifetime_since": lifetime_since}), 200

# ----------------------
# Point d'entrée
# ----------------------
if __name__ == "__main__":
    print("Lancement auth_api sur le port", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=True)
