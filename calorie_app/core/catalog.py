# calorie_app/core/catalog.py
from typing import List, Dict

# --- Recettes intégrées (images + étapes) ---
RECIPES: List[Dict] = [
    # Petit-déj
    {"name":"Porridge protéiné", "tag":"Petit-déj",
     "items":[("Flocons d’avoine",50),("Lait (ou boisson soja)",200),("Yaourt grec",100),("Graines de lin moulues",10)],
     "goals":["fibres","proteines","ala"],
     "image_url":"https://images.unsplash.com/photo-1490474418585-ba9bad8fd0ea",
     "steps":[
        "Chauffer le lait et l’avoine 3–5 min (texture onctueuse).",
        "Hors du feu, ajouter le yaourt grec.",
        "Parsemer de lin moulu. Option: fruits rouges."
     ]},
    {"name":"Smoothie vert", "tag":"Petit-déj",
     "items":[("Épinards",60),("Banane",80),("Pomme",100),("Graines de chia",10),("Eau",200)],
     "goals":["fibres","micros"],
     "image_url":"https://images.unsplash.com/photo-1514996937319-344454492b37",
     "steps":[
        "Mixer tous les ingrédients 30–60 s.",
        "Ajuster l’eau selon l’épaisseur souhaitée."
     ]},

    # Collation / Pré
    {"name":"Skyr + noix", "tag":"Collation",
     "items":[("Skyr",150),("Noix",20)], "goals":["proteines","ala"],
     "image_url":"https://images.unsplash.com/photo-1512621776951-a57141f2eefd",
     "steps":[ "Mélanger le skyr et les noix. Option: cannelle/miel." ]},
    {"name":"Toast beurre d’amande", "tag":"Pré-workout",
     "items":[("Pain complet",60),("Beurre d’amande",20)], "goals":["glucides","lipides"],
     "image_url":"https://images.unsplash.com/photo-1512621776951-7d3b0d5f0b8a",
     "steps":[ "Griller le pain, tartiner le beurre d’amande." ]},

    # Déjeuner
    {"name":"Buddha bowl", "tag":"Déjeuner",
     "items":[("Quinoa",120),("Pois chiches",120),("Avocat",70),("Légumes variés",200),("Huile d’olive",10)],
     "goals":["fibres","proteines","lipides"],
     "image_url":"https://images.unsplash.com/photo-1540189549336-e6e99c3679fe",
     "steps":[
        "Cuire le quinoa.",
        "Assembler avec pois chiches, légumes, avocat.",
        "Arroser d’huile d’olive, saler/poivrer légèrement."
     ]},
    {"name":"Poulet & patate douce", "tag":"Déjeuner",
     "items":[("Poulet",140),("Patate douce",200),("Brocoli",150),("Huile d’olive",10)],
     "goals":["proteines","glucides"],
     "image_url":"https://images.unsplash.com/photo-1512621776951-4b4d1d2e1a1e",
     "steps":[
        "Cuire le poulet.",
        "Rôtir patate douce en cubes 25 min.",
        "Vapeur de brocoli 6–8 min. Assembler."
     ]},

    # Dîner
    {"name":"Saumon & riz complet", "tag":"Dîner",
     "items":[("Saumon",150),("Riz complet",150),("Courgette",150),("Huile d’olive",8)],
     "goals":["epa_dha","proteines"],
     "image_url":"https://images.unsplash.com/photo-1504674900247-0877df9cc836",
     "steps":[
        "Cuire le riz complet.",
        "Poêler le saumon (côté peau d’abord).",
        "Sauter courgette, finir avec filet d’huile."
     ]},
    {"name":"Tofu sauté & légumes", "tag":"Dîner",
     "items":[("Tofu",160),("Légumes variés",250),("Nouilles sarrasin",120),("Huile de colza",8)],
     "goals":["proteines","ala","fibres"],
     "image_url":"https://images.unsplash.com/photo-1512058564366-18510be2db19",
     "steps":[
        "Sauter tofu et légumes à feu moyen.",
        "Cuire nouilles, mélanger, ajouter huile de colza."
     ]},

    # Post
    {"name":"Bol cacao-banane (post)", "tag":"Post-workout",
     "items":[("Banane",120),("Lait (ou boisson soja)",250),("Cacao non sucré",8),("Avoine",40)],
     "goals":["glucides","proteines"],
     "image_url":"https://images.unsplash.com/photo-1493770348161-369560ae357d",
     "steps":[
        "Mixer banane, lait, cacao.",
        "Ajouter l’avoine, mixer à nouveau."
     ]},
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

# --- Encyclopédie micronutriments (exhaustif courant) ---
MICROS = [
    # VITAMINES
    {"name":"Vitamine A — µg RAE", "why":"Vision, immunité, peau", "sources":"Foie, carotte, patate douce", "rdi":"700–900 µg/j"},
    {"name":"Vitamine B1 (Thiamine) — mg", "why":"Énergie glucidique, nerfs", "sources":"Céréales complètes, porc", "rdi":"1.1–1.2 mg/j"},
    {"name":"Vitamine B2 (Riboflavine) — mg", "why":"Énergie, peau/yeux", "sources":"Laitages, œufs, amandes", "rdi":"1.1–1.3 mg/j"},
    {"name":"Vitamine B3 (Niacine) — mg", "why":"Énergie, peau", "sources":"Volaille, thon, cacahuète", "rdi":"14–16 mg/j"},
    {"name":"Vitamine B5 (Ac. pantothénique) — mg", "why":"Énergie, synthèse hormones", "sources":"Champignons, poulet", "rdi":"5 mg/j"},
    {"name":"Vitamine B6 — mg", "why":"Métabolisme AA, système nerveux", "sources":"Banane, volaille, pomme de terre", "rdi":"1.3–1.7 mg/j"},
    {"name":"Vitamine B7 (Biotine) — µg", "why":"Cheveux/ongles, énergie", "sources":"Œufs (cuits), noix", "rdi":"30 µg/j"},
    {"name":"Vitamine B9 (Folates) — µg", "why":"Synthèse ADN, grossesse", "sources":"Légumes verts, légumineuses", "rdi":"400 µg/j"},
    {"name":"Vitamine B12 — µg", "why":"Nerfs, globules rouges", "sources":"Produits animaux / B12 végétale", "rdi":"2–4 µg/j"},
    {"name":"Vitamine C — mg", "why":"Antioxydant, immunité, collagène", "sources":"Agrumes, kiwi, poivron", "rdi":"75–110 mg/j"},
    {"name":"Vitamine D — µg", "why":"Os, immunité", "sources":"Poissons gras, soleil, D3", "rdi":"10–20 µg/j"},
    {"name":"Vitamine E — mg", "why":"Antioxydant lipides", "sources":"Huiles végétales, amandes", "rdi":"12–15 mg/j"},
    {"name":"Vitamine K — µg", "why":"Coagulation, os", "sources":"Choux, épinards, huiles", "rdi":"90–120 µg/j"},

    # MINÉRAUX
    {"name":"Calcium — mg", "why":"Os, contraction musculaire", "sources":"Laitages, choux, eaux riches", "rdi":"900–1200 mg/j"},
    {"name":"Fer — mg", "why":"Transport O₂, énergie", "sources":"Viande rouge, légumineuses + vit C", "rdi":"11–16 mg/j"},
    {"name":"Magnésium — mg", "why":"Fatigue, nerveux", "sources":"Oléagineux, cacao, céréales complètes", "rdi":"350–420 mg/j"},
    {"name":"Zinc — mg", "why":"Immunité, peau", "sources":"Huîtres, viande, graines", "rdi":"8–12 mg/j"},
    {"name":"Iode — µg", "why":"Thyroïde", "sources":"Poissons, algues, sel iodé", "rdi":"150 µg/j"},
    {"name":"Sélénium — µg", "why":"Antioxydant", "sources":"Noix du Brésil, poisson", "rdi":"55–70 µg/j"},
    {"name":"Potassium — mg", "why":"Pression artérielle, nerfs", "sources":"Fruits/légumes, légumineuses", "rdi":"3500–4700 mg/j"},
    {"name":"Sodium — mg", "why":"Équilibre hydrique", "sources":"Sel de table, aliments transformés", "rdi":"< 2300 mg/j (~6 g sel)"},
    {"name":"Phosphore — mg", "why":"Os, énergie cellulaire", "sources":"Viandes, laitages, fruits à coque", "rdi":"700–1000 mg/j"},
    {"name":"Manganèse — mg", "why":"Cofacteur enzymes", "sources":"Noix, céréales, thé", "rdi":"2–3 mg/j"},
    {"name":"Cuivre — mg", "why":"Fer, collagène", "sources":"Foie, fruits de mer, noix", "rdi":"1–1.5 mg/j"},
    {"name":"Chrome — µg", "why":"Métabolisme glucides", "sources":"Céréales complètes, brocoli", "rdi":"25–35 µg/j"},
    {"name":"Molybdène — µg", "why":"Enzymes", "sources":"Légumineuses, céréales", "rdi":"45–75 µg/j"},
    {"name":"Chlorure — mg", "why":"Équilibre acido-basique", "sources":"Sel (NaCl), aliments salés", "rdi":"2300 mg/j"},
]
