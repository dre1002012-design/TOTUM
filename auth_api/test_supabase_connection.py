# auth_api/test_supabase_connection.py
"""
Test simple de connexion à Supabase.
Il liste 1 enregistrement (si présent) dans la table 'profiles'
et affiche la version du service pour vérifier la connexion.
"""

import os
from supabase import create_client
from dotenv import load_dotenv

# Charger .env local
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERREUR: SUPABASE_URL ou SUPABASE_KEY manquant(e) dans .env")
    print("Vérifie que tu as bien ajouté SUPABASE_URL et SUPABASE_KEY dans auth_api/.env")
    raise SystemExit(1)

print("Tentative de connexion à Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    # Requête simple : récupérer jusqu'à 1 profil pour tester l'accès
    resp = supabase.table("profiles").select("*").limit(1).execute()
    # resp est un objet avec .data et .status_code selon la lib
    print("Réponse status code:", getattr(resp, "status_code", "N/A"))
    print("Données reçues (profiles) :", resp.data if hasattr(resp, "data") else resp)
except Exception as e:
    print("Erreur lors de la requête Supabase :", str(e))
    raise SystemExit(1)

print("Test de connexion Supabase terminé avec succès.")
