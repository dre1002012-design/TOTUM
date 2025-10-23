"""
core/calc.py — formules nutritionnelles et affichage donuts
"""

import plotly.graph_objects as go
from .utils import norm

COLORS = {
    "energie":"#ff7f3f", "proteines":"#2ca02c", "glucides":"#1f77b4", "lipides":"#d62728",
    "fibres":"#9467bd", "omega3":"#00bcd4", "epa":"#26a69a", "dha":"#7e57c2",
    "omega6":"#ffb300", "omega9":"#8d6e63", "restant":"#e0e0e0", "objectif":"#bdbdbd",
    "ok":"#5cb85c", "warn":"#f0ad4e", "bad":"#d9534f"
}

def donut(cons, target, title, color_key="energie", height=210):
    cons = float(cons or 0.0); target = float(target or 0.0)
    if target <= 0:
        fig = go.Figure(data=[go.Pie(values=[1], labels=["Objectif manquant"], hole=0.68,
                                     textinfo="label", marker_colors=[COLORS["objectif"]])])
        fig.update_layout(title=title, margin=dict(l=0,r=0,t=34,b=0), height=height,
                          showlegend=False, font=dict(size=13),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    pct = 0 if target == 0 else cons / target * 100
    wedge = COLORS["ok"] if pct>=100 else (COLORS["warn"] if pct>=50 else COLORS["bad"])
    rest = max(target - cons, 0.0)
    fig = go.Figure(data=[go.Pie(values=[cons, rest], hole=0.7, textinfo="none",
                                 marker_colors=[wedge, COLORS["restant"]])])
    fig.update_layout(
        title=title,
        annotations=[dict(text=f"{cons:.1f}/{target:.1f}<br>({pct:.0f}%)", x=0.5, y=0.5, showarrow=False)],
        margin=dict(l=0,r=0,t=32,b=0), height=height, showlegend=False, font=dict(size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

# === Objectifs clés (profil) ===

def bmr_harris_benedict_revised(sex, age, height_cm, weight_kg):
    if norm(sex).startswith("h"):
        return 88.362 + 13.397*float(weight_kg) + 4.799*float(height_cm) - 5.677*int(age)
    else:
        return 447.593 + 9.247*float(weight_kg) + 3.098*float(height_cm) - 4.330*int(age)

ACTIVITY_TABLE = {
    "sedentaire":{"factor":1.2,   "prot_min":0.8, "prot_max":1.0},
    "leger":{"factor":1.375,      "prot_min":1.0, "prot_max":1.2},
    "modere":{"factor":1.55,      "prot_min":1.2, "prot_max":1.6},
    "intense":{"factor":1.725,    "prot_min":1.6, "prot_max":2.0},
    "tresintense":{"factor":1.9,  "prot_min":2.0, "prot_max":2.5},
    "athlete":{"factor":1.9,      "prot_min":2.0, "prot_max":2.5},
}
RULES = {
    "lipides_pct":0.35, "agsat_pct":0.10, "omega9_pct":0.15, "omega6_pct":0.04, "ala_pct":0.01,
    "glucides_pct":0.55, "sucres_pct":0.10, "fibres_g":30.0, "epa_g":0.25, "dha_g":0.25, "sel_g":6.0,
}

def _activity_key(a: str) -> str:
    a = "".join(ch for ch in a.lower() if ch.isalnum())
    if "sedentaire" in a: return "sedentaire"
    if "leger" in a: return "leger"
    if "modere" in a: return "modere"
    if "intense" in a and "tres" not in a and "2x" not in a: return "intense"
    if "tresintense" in a or "2x" in a or "athlete" in a: return "tresintense"
    return "sedentaire"

def excel_like_targets(p: dict) -> dict:
    """Reproduit la logique d’objectifs clés (comme dans ton app)."""
    bmr = bmr_harris_benedict_revised(p["sexe"], int(p["age"]), float(p["taille_cm"]), float(p["poids_kg"]))
    af = ACTIVITY_TABLE[_activity_key(p["activite"])]["factor"]
    tdee = bmr * af
    prot_max = ACTIVITY_TABLE[_activity_key(p["activite"])]["prot_max"]
    return {
        "energie_kcal": float(tdee),
        "proteines_g":  float(float(p["poids_kg"]) * prot_max),
        "lipides_g":    float(tdee * RULES["lipides_pct"] / 9.0),
        "agsatures_g":  float(tdee * RULES["agsat_pct"]   / 9.0),
        "omega9_g":     float(tdee * RULES["omega9_pct"]  / 9.0),
        "omega6_g":     float(tdee * RULES["omega6_pct"]  / 9.0),
        "ala_w3_g":     float(tdee * RULES["ala_pct"]     / 9.0),
        "epa_g":        RULES["epa_g"],
        "dha_g":        RULES["dha_g"],
        "glucides_g":   float(tdee * RULES["glucides_pct"]/ 4.0),
        "sucres_g":     float(tdee * RULES["sucres_pct"]  / 4.0),
        "fibres_g":     RULES["fibres_g"],
        "sel_g":        RULES["sel_g"],
    }
# === Conversion "pour 100 g" -> quantité réelle ===
import pandas as pd  # (en bas pour éviter conflits d'import)

def _nutrient_cols(df_or_row):
    cols = list(df_or_row.index if isinstance(df_or_row, pd.Series) else df_or_row.columns)
    return [c for c in cols if str(c).endswith("_100g")]

def _per100_to_name(colname: str) -> str:
    # "Protéines_g_100g" -> "Protéines_g"
    return str(colname)[:-5] if str(colname).endswith("_100g") else str(colname)

def calc_from_food_row(row: pd.Series, qty_g: float) -> dict:
    """Prend une ligne d'aliment (df.loc[i]) et une quantité en g -> dict de nutriments en valeur réelle."""
    out = {}
    for c in _nutrient_cols(row):
        try:
            val100 = pd.to_numeric(pd.Series([row[c]]), errors="coerce").iloc[0]
        except Exception:
            val100 = None
        if pd.notna(val100):
            out[_per100_to_name(c)] = float(qty_g) * float(val100) / 100.0
    return out
