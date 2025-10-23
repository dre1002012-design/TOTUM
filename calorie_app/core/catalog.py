# calorie_app/core/catalog.py
from typing import List, Dict

# --- Recettes "intégrées" (démo, faciles à étendre) ---
RECIPES: List[Dict] = [
    # Petit-déj
    {"name":"Porridge protéiné", "tag":"Petit-déj",
     "items":[("Flocons d’avoine",50),("Lait (ou boisson soja)",200),("Yaourt grec",100),("Graines de lin moulues",10)],
     "goals":["fibres","proteines","ala"]},
    {"name":"Smoothie vert", "tag":"Petit-déj",
     "items":[("Épinards",60),("Banane",80),("Pomme",100),("Graines de chia",10),("Eau",200)],
     "goals":["fibres","micros"]},

    # Collation / Pré
    {"name":"Skyr + noix", "tag":"Collation",
     "items":[("Skyr",150),("Noix",20)], "goals":["proteines","ala"]},
    {"name":"Toast beurre d’amande", "tag":"Pré-workout",
     "items":[("Pain complet",60),("Beurre d’amande",20)], "goals":["glucides","lipides"]},

    # Déjeuner
    {"name":"Buddha bowl", "tag":"Déjeuner",
     "items":[("Quinoa",120),("Pois chiches",120),("Avocat",70),("Légumes variés",200),("Huile d’olive",10)],
     "goals":["fibres","proteines","lipides"]},
    {"name":"Poulet & patate douce", "tag":"Déjeuner",
     "items":[("Poulet",140),("Patate douce",200),("Brocoli",150),("Huile d’olive",10)],
     "goals":["proteines","glucides"]},

    # Dîner
    {"name":"Saumon & riz complet", "tag":"Dîner",
     "items":[("Saumon",150),("Riz complet",150),("Courgette",150),("Huile d’olive",8)],
     "goals":["epa_dha","proteines"]},
    {"name":"Tofu sauté & légumes", "tag":"Dîner",
     "items":[("Tofu",160),("Légumes variés",250),("Nouilles sarrasin",120),("Huile de colza",8)],
     "goals":["proteines","ala","fibres"]},

    # Post
    {"name":"Bol cacao-banane (post)", "tag":"Post-workout",
     "items":[("Banane",120),("Lait (ou boisson soja)",250),("Cacao non sucré",8),("Avoine",40)],
     "goals":["glucides","proteines"]},
]

GOAL_MAP = {
    "proteines":"💪 Protéines",
    "fibres":"🌾 Fibres",
    "glucides":"🍞 Glucides",
    "lipides":"🥑 Lipides",
    "ala":"🌱 Oméga-3 ALA",
    "epa_dha":"🐟 EPA/DHA",
    "micros":"🍊 Micronutriments",
}

def suggest_recipes(top_needs: list[str], tag_filter: str | None = None, limit: int = 6) -> List[Dict]:
    """Retourne des recettes alignées avec les besoins (gaps/limits inversées)."""
    needs = set(top_needs or [])
    out = []
    for r in RECIPES:
        if tag_filter and tag_filter != "Toutes" and r["tag"] != tag_filter:
            continue
        score = len(needs.intersection(r["goals"]))
        out.append((score, r))
    out.sort(key=lambda x: x[0], reverse=True)
    return [r for s, r in out if s>0][:limit] or [r for _, r in out][:limit]

# --- Encyclopédie micronutriments (démo) ---
MICROS = [
    {"name":"Vitamine C — mg", "why":"Antioxydant, immunité, collagène", "sources":"Agrumes, kiwi, poivron", "rdi":"75–110 mg/j"},
    {"name":"Vitamine D — µg", "why":"Os, immunité", "sources":"Poissons gras, soleil, D3", "rdi":"10–20 µg/j"},
    {"name":"Vitamine B12 — µg", "why":"Système nerveux, globules rouges", "sources":"Produits animaux / B12 végétale", "rdi":"2–4 µg/j"},
    {"name":"Calcium — mg", "why":"Os, contraction musculaire", "sources":"Laitages, choux, eaux riches", "rdi":"900–1200 mg/j"},
    {"name":"Fer — mg", "why":"Transport O₂, énergie", "sources":"Viande rouge, légumineuses + vit C", "rdi":"11–16 mg/j"},
    {"name":"Magnésium — mg", "why":"Fatigue, système nerveux", "sources":"Oléagineux, cacao, céréales complètes", "rdi":"350–420 mg/j"},
    {"name":"Zinc — mg", "why":"Immunité, peau", "sources":"Huîtres, viande, graines", "rdi":"8–12 mg/j"},
    {"name":"Iode — µg", "why":"Thyroïde", "sources":"Poissons, algues, sel iodé", "rdi":"150 µg/j"},
]
