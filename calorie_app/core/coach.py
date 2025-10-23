# calorie_app/core/coach.py
import datetime as dt
import pandas as pd
from typing import Dict, List

# --- Clés et labels lisibles ---
NUTRI_LIMIT_KEYS = {
    "Sucres_g": "🍬 Sucres",
    "AG_saturés_g": "🥓 AG saturés",
    "AG_satures_g": "🥓 AG saturés",
    "Sel_g": "🧂 Sel",
    "Sodium_g": "🧂 Sel",
}
NUTRI_TARGET_KEYS = {
    "Protéines_g": "💪 Protéines",
    "Proteines_g": "💪 Protéines",
    "Fibres_g": "🌾 Fibres",
    "Glucides_g": "🍞 Glucides",
    "Lipides_g": "🥑 Lipides",
    "Acide_alpha-linolénique_W3_ALA_g": "🌱 Oméga-3 ALA",
    "EPA_g": "🐟 EPA",
    "DHA_g": "🧠 DHA",
    "Acide_linoléique_W6_LA_g": "🫒 Oméga-6",
    "Acide_linoleique_W6_LA_g": "🫒 Oméga-6",
    "Acide_oléique_W9_g": "🫒 Oméga-9",
    "Acide_oleique_W9_g": "🫒 Oméga-9",
}

def _sum_numeric(df: pd.DataFrame, drop_cols=None) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    drop_cols = set(drop_cols or [])
    num = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    num = num.apply(pd.to_numeric, errors="coerce")
    return num.sum(numeric_only=True)

def week_dates(end_date: dt.date, days: int = 7):
    return [(end_date - dt.timedelta(days=i)).isoformat() for i in range(days)][::-1]

def weekly_totals(end_date: dt.date, fetch_journal_by_date_fn) -> pd.Series:
    totals = pd.Series(dtype=float)
    for d in week_dates(end_date):
        df = fetch_journal_by_date_fn(d)
        day = _sum_numeric(df, drop_cols={"id","date","repas","nom","quantite_g"})
        totals = (totals.add(day, fill_value=0) if not totals.empty else day)
    return totals

def today_totals(fetch_journal_by_date_fn) -> pd.Series:
    return _sum_numeric(fetch_journal_by_date_fn(dt.date.today().isoformat()),
                        drop_cols={"id","date","repas","nom","quantite_g"})

def coverage(value: float, target: float) -> float | None:
    target = float(target or 0.0)
    return (value/target*100.0) if target>0 else None

def _map_target_key(col: str) -> str:
    c = col.lower()
    if "proteines" in c: return "proteines_g"
    if "glucides"  in c: return "glucides_g"
    if "lipides"   in c: return "lipides_g"
    if "fibres"    in c: return "fibres_g"
    if "sucres"    in c: return "sucres_g"
    if "sodium" in c or "sel" in c: return "sel_g"
    if "epa" in c: return "epa_g"
    if "dha" in c: return "dha_g"
    if "w6" in c or "linoleique" in c: return "omega6_g"
    if "oleique" in c or "w9" in c: return "omega9_g"
    if "alpha" in c or "ala" in c or "omega3" in c: return "ala_w3_g"
    return col

def weekly_targets_from_daily(daily: Dict[str, float]) -> Dict[str, float]:
    return {k: float(v or 0.0) * 7.0 for k, v in daily.items()}

# ---------------- Core analyses ----------------
def analyze_week(week: pd.Series, week_targets: Dict[str, float]) -> Dict:
    """Diagnostic semaine : forces, manques, excès."""
    strengths, gaps, limits_excess = [], [], []

    # À viser (couverture %)
    for k, label in NUTRI_TARGET_KEYS.items():
        v = float(week.get(k, 0.0) or 0.0)
        t = float(week_targets.get(_map_target_key(k), 0.0) or 0.0)
        cov = coverage(v, t)
        if cov is None: 
            continue
        if cov >= 100:
            strengths.append(f"{label} : {cov:.0f}% ✅")
        elif cov < 80:   # seuil relevé (plus sensible)
            gaps.append((label, cov))

    # À limiter (dépassements)
    for k, label in NUTRI_LIMIT_KEYS.items():
        v = float(week.get(k, 0.0) or 0.0)
        t = float(week_targets.get(_map_target_key(k), 0.0) or 0.0)
        if t and v > t:
            limits_excess.append((label, v, t))

    # top 3 manques / top 3 excès
    gaps = sorted(gaps, key=lambda x: (x[1] if x[1] is not None else 999))[:3]
    limits_excess = limits_excess[:3]
    return {"strengths": strengths[:3], "gaps": gaps, "limits": limits_excess}

def analyze_today(today: pd.Series, daily_targets: Dict[str, float]) -> Dict:
    """Analyses du jour (réagit immédiatement: pizza/salé/sucré)."""
    alerts = []
    def over(k_col, name, factor=1.2):
        v = float(today.get(k_col, 0.0) or 0.0)
        t = float(daily_targets.get(_map_target_key(k_col), 0.0) or 0.0)
        if t and v >= factor * t:
            alerts.append(f"{name} aujourd’hui au-dessus des repères ({v:.1f} vs {t:.1f})")

    # Détections “pizza like” : AG saturés, sel, lipides, énergie (indirect via macro)
    over("AG_saturés_g", "🥓 AG saturés", 1.1)
    over("AG_satures_g", "🥓 AG saturés", 1.1)
    over("Sel_g", "🧂 Sel", 1.1)
    over("Sodium_g", "🧂 Sel", 1.1)
    over("Lipides_g", "🥑 Lipides", 1.2)
    over("Sucres_g", "🍬 Sucres", 1.2)
    return {"alerts": alerts[:4]}
    
# ---------------- Plans d’action ----------------
def build_actions(diagnostic: Dict) -> Dict[str, List[str]]:
    actions_nutri, actions_limit, lifestyle = [], [], []

    for label, cov in diagnostic.get("gaps", []):
        if "Protéines" in label:
            actions_nutri.append("Ajoute une portion de **protéines maigres** (poulet, tofu, yaourt grec).")
        elif "Fibres" in label:
            actions_nutri.append("Ajoute **légumineuses**, **fruits rouges** ou **graines de chia/lin**.")
        elif "Oméga-3 ALA" in label:
            actions_nutri.append("Saupoudre **1 càs de lin moulu** ou **noix** au petit-déj.")
        elif "Glucides" in label:
            actions_nutri.append("Privilégie **IG bas** (avoine, quinoa, patate douce).")
        elif "Lipides" in label:
            actions_nutri.append("Favorise **huile d’olive** et **poissons gras** 2×/semaine.")
        else:
            actions_nutri.append(f"Renforce l’apport en **{label}** via des aliments sources.")

    for label, v, t in diagnostic.get("limits", []):
        if "Sucres" in label:
            actions_limit.append("Remplace **sodas/pâtisseries** par **eau pétillante** / **fruits entiers**.")
        elif "AG saturés" in label:
            actions_limit.append("Réduis **charcuteries/fromages gras/fritures**; cuisine à l’**huile d’olive**.")
        elif "Sel" in label:
            actions_limit.append("Utilise **herbes/épices**; surveille **plats industriels/sauces**.")
        else:
            actions_limit.append(f"Réduis l’excès de **{label}** au prochain plein de courses.")

    weekday = dt.date.today().weekday()
    lifestyle_bank = [
        "🛏️ Vise **7–9 h** de sommeil (heure de coucher régulière).",
        "🚶 **20–30 min** d’activité modérée (marche active).",
        "💧 **1,5–2 L** d’eau (citron/menthe).",
        "🧘 2× **3 min** respiration 5-5.",
        "📵 **Écran off** 45 min avant dormir.",
        "🌞 **Lumière du matin** (rythme circadien).",
        "🍽️ **Mastique +** (satiété/digestion).",
    ]
    lifestyle.append(lifestyle_bank[weekday]); lifestyle.append(lifestyle_bank[(weekday+3) % len(lifestyle_bank)])

    return {"to_add": actions_nutri[:3], "to_limit": actions_limit[:3], "lifestyle": lifestyle[:2]}
