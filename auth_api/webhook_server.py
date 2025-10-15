import stripe
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# 🔒 Ta clé secrète Stripe (mode test)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Le secret du webhook (celui que tu m’as donné)
WEBHOOK_SECRET = "whsec_1cd0a27d981ca9ff970847c903816ba4eacd62711343aa78452ae74d64aceb91"

@app.route("/webhook", methods=["POST"])
def webhook_received():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    # ✅ Ici, on détecte le paiement réussi
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print("✅ Paiement réussi :", session.get("customer_email"))

    return jsonify(success=True)

if __name__ == "__main__":
    app.run(port=4242)
