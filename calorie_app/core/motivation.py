# calorie_app/core/motivation.py
import datetime as dt
import hashlib

QUOTES = [
    "Le progrès, pas la perfection. Un bon choix à la fois.",
    "Bouge un peu +, mange un peu mieux, dors un peu plus — chaque % compte.",
    "L’assiette d’aujourd’hui construit ton énergie de demain.",
    "Petit-déj riche en protéines = fringales en moins.",
    "L’eau est ta meilleure boisson d’abord.",
    "La clé, c’est la régularité. Même les petites actions répétées gagnent.",
    "Plus de couleurs dans l’assiette = plus de micronutriments.",
    "Respire profond 1 min avant de manger — apaise & digère mieux.",
]

def quote_of_the_day(name: str | None = None) -> str:
    base = (name or "") + dt.date.today().isoformat()
    h = hashlib.sha256(base.encode()).hexdigest()
    idx = int(h, 16) % len(QUOTES)
    return QUOTES[idx]
