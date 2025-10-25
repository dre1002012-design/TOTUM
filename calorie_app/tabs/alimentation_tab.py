import streamlit as st
import pandas as pd
import datetime as dt

from calorie_app.core.calc import excel_like_targets, calc_from_food_row
from calorie_app.core.data import fetch_journal_by_date, insert_journal
from calorie_app.core.load import load_foods
from calorie_app.core.search import build_search_index, search_foods
from calorie_app.core.coach import (
    weekly_targets_from_daily, weekly_totals, analyze_week, analyze_today, build_actions,
    needs_from_diagnostic, portion_hint_from_gap
)
from calorie_app.core.motivation import quote_of_the_day
from calorie_app.core.catalog import suggest_recipes, RECIPES, GOAL_MAP, MICROS

MEALS = ["Petit-déjeuner", "Déjeuner", "Dîner", "Collation"]

# ============ Header nav (pills) ============
def _header_nav():
    st.markdown(
        """
        <style>
        .pill {display:inline-block;padding:8px 14px;margin:4px;border-radius:18px;border:1px solid #ddd;cursor:pointer;}
        .pill.active {background:#ff7f3f;color:white;border-color:#ff7f3f;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    active = st.session_state.get("alim_tab", "Conseils")
    cols = st.columns(5)
    labels = ["Conseils", "Coach IA", "Recettes", "Nutri", "Défis"]
    for i, lab in enumerate(labels):
        # Affiche un petit badge ✅ sur "Défis" si validé aujourd’hui
        label_text = ("✅ " if st.session_state.get("challenge_done") and lab == "Défis" else "") + lab
        if cols[i].button(label_text, key=f"pill_{lab}"):
            st.session_state["alim_tab"] = lab
    st.divider()
    return st.session_state.get("alim_tab", "Conseils")

# ======== Helpers ========
def _sum_numeric(df: pd.DataFrame, drop_cols=None) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    drop_cols = set(drop_cols or [])
    num = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    num = num.apply(pd.to_numeric, errors="coerce")
    return num.sum(numeric_only=True)

def _energy_from_series(s: pd.Series) -> float:
    p = float(pd.to_numeric(pd.Series([s.get("Protéines_g", s.get("Proteines_g", 0))]), errors="coerce").fillna(0).iloc[0])
    g = float(pd.to_numeric(pd.Series([s.get("Glucides_g", 0)]), errors="coerce").fillna(0).iloc[0])
    l = float(pd.to_numeric(pd.Series([s.get("Lipides_g", 0)]), errors="coerce").fillna(0).iloc[0])
    return p*4 + g*4 + l*9

def _ensure_state_defaults():
    st.session_state.setdefault("recipes", [])
    st.session_state.setdefault("recipe_filters", {"q":"", "tag":"Toutes"})
    st.session_state.setdefault("challenge_done", False)
    st.session_state.setdefault("challenge_day", dt.date.today().isoformat())

def _to_series(obj) -> pd.Series:
    """Uniformise un dict/Series/None en pandas.Series[float]."""
    if isinstance(obj, pd.Series):
        return obj.astype(float)
    if isinstance(obj, dict):
        try:
            return pd.Series(obj, dtype=float)
        except Exception:
            return pd.Series({k: pd.to_numeric(v, errors="coerce") for k, v in obj.items()}, dtype=float)
    return pd.Series(dtype=float)

def _nutr_from_recipe_items(foods: pd.DataFrame, index_df: pd.DataFrame, items: list[tuple[str,int]]) -> pd.Series:
    """Calcule macros/micros d’une recette depuis les noms d’ingrédient (match exact puis fuzzy)."""
    total = pd.Series(dtype=float)
    for name, qty in items:
        # 1) essai exact
        row = foods.loc[foods["nom"].astype(str).str.lower() == str(name).lower()]
        if row.empty:
            # 2) fallback fuzzy via index
            res = search_foods(index_df, str(name), limit=1, page=1)
            if isinstance(res, pd.DataFrame) and not res.empty:
                row = foods.loc[foods["nom"].astype(str) == res.iloc[0]["nom"]]
        if not row.empty:
            nutr = calc_from_food_row(row.iloc[0], float(qty))  # peut être dict
            nutr_s = _to_series(nutr).fillna(0)
            total = total.add(nutr_s, fill_value=0)
        # si non trouvé : on ignore proprement
    return total.fillna(0)

# ============ CONSEILS (pertinent + alertes du jour) ============
def _render_conseils():
    st.markdown("### 💡 Conseils intelligents")
    profile = st.session_state.get("profile", {})
    daily_targets = excel_like_targets(profile)
    week_targets = weekly_targets_from_daily(daily_targets)
    end_date = st.session_state.get("date_bilan", dt.date.today())
    week = weekly_totals(end_date, fetch_journal_by_date)

    # Motivation du jour
    st.info("**Motivation du jour** — " + quote_of_the_day(profile.get("prenom") or profile.get("nom")))

    # Métriques 7j
    kcal_w = _energy_from_series(week)
    p_w = float(week.get("Protéines_g", week.get("Proteines_g", 0.0)) or 0.0)
    g_w = float(week.get("Glucides_g", 0.0) or 0.0)
    l_w = float(week.get("Lipides_g", 0.0) or 0.0)
    fib_w = float(week.get("Fibres_g", 0.0) or 0.0)
    kc, pr, gl, li, fb = st.columns(5)
    kc.metric("Énergie (kcal/7j)", f"{kcal_w:.0f}")
    pr.metric("Protéines (g/7j)", f"{p_w:.0f}")
    gl.metric("Glucides (g/7j)", f"{g_w:.0f}")
    li.metric("Lipides (g/7j)",   f"{l_w:.0f}")
    fb.metric("Fibres (g/7j)",    f"{fib_w:.0f}")

    # Diagnostic semaine + alertes du jour
    diag = analyze_week(week, week_targets)
    today = analyze_today(_sum_numeric(fetch_journal_by_date(dt.date.today().isoformat()),
                                       drop_cols={"id","date","repas","nom","quantite_g"}), daily_targets)

    if today["alerts"]:
        st.error("**Alerte du jour :** " + "  •  ".join(today["alerts"]))

    if diag["strengths"]:
        st.success("**Points forts (7j)** : " + "  •  ".join(diag["strengths"]))
    if diag["gaps"] or diag["limits"]:
        st.warning(
            "**À renforcer (7j)** : "
            + "  •  ".join([f"{label} ({cov:.0f}%)" for (label, cov) in diag["gaps"]])
            + ("  •  " if (diag["gaps"] and diag["limits"]) else "")
            + "  •  ".join([f"{label} — au-dessus" for (label, _, _) in diag["limits"]])
        )
    if not diag["strengths"] and not (diag["gaps"] or diag["limits"]) and not today["alerts"]:
        st.info("Ajoute tes repas dans le Journal pour débloquer ces conseils 👍")

    # Plan d’action
    st.markdown("#### 🎯 Plan d’action")
    plan = build_actions(diag)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**À ajouter**")
        for a in plan["to_add"] or ["_Rien de prioritaire_"]:
            st.markdown("- " + a)
    with c2:
        st.markdown("**À limiter**")
        for a in plan["to_limit"] or ["_RAS_"]:
            st.markdown("- " + a)
    with c3:
        st.markdown("**Lifestyle**")
        for a in plan["lifestyle"]:
            st.markdown("- " + a)

    with st.expander("ℹ️ Sources (repères & recommandations)"):
        st.caption("ANSES / EFSA — Repères nutritionnels généraux. Conseils synthétiques orientés pratico-pratiques.")

# ============ COACH IA+ (recettes ciblées + portion + macros auto) ============
def _render_coach():
    st.markdown("### 🤖 Coach IA — recommandations personnalisées")
    profile = st.session_state.get("profile", {})
    daily_targets = excel_like_targets(profile)
    week_targets = weekly_targets_from_daily(daily_targets)
    end_date = st.session_state.get("date_bilan", dt.date.today())
    week = weekly_totals(end_date, fetch_journal_by_date)
    diag = analyze_week(week, week_targets)

    needs = needs_from_diagnostic(diag) or ["proteines","fibres"]
    st.caption("Suggestions basées sur tes 7 derniers jours.")
    tag = st.selectbox("Moment", ["Toutes","Petit-déj","Déjeuner","Dîner","Collation","Pré-workout","Post-workout"], index=0)

    foods = load_foods()
    foods = foods.loc[:, ~foods.columns.duplicated()].copy()
    index_df = build_search_index(foods)

    picks = suggest_recipes(needs, tag_filter=tag, limit=6)
    for r in picks:
        with st.container():
            cA, cB = st.columns([3,1])
            if r.get("image_url"):
                cB.image(r["image_url"], use_container_width=True)
            cA.markdown(f"**{r['name']}** — _{r['tag']}_")
            cA.caption("Ingrédients : " + " | ".join([f"{name} ({qty} g)" for name, qty in r["items"]]))
            # Portion conseillée basée sur 1er besoin (si présent), sinon somme des g
            suggested_portion = portion_hint_from_gap(diag["gaps"][0][0]) if diag.get("gaps") else sum(q for _, q in r["items"])
            cA.caption(f"➡️ Portion conseillée indicative : ~{suggested_portion} g")
            # Macros/micros calculés automatiquement
            nutr_series = _nutr_from_recipe_items(foods, index_df, r["items"])
            kcal = _energy_from_series(pd.Series({
                "Protéines_g": float(nutr_series.get("Protéines_g", nutr_series.get("Proteines_g", 0.0)) or 0.0),
                "Glucides_g":  float(nutr_series.get("Glucides_g", 0.0) or 0.0),
                "Lipides_g":   float(nutr_series.get("Lipides_g", 0.0) or 0.0),
            }))
            cA.write(f"🔥 **{kcal:.0f} kcal**  •  💪 **{nutr_series.get('Protéines_g', nutr_series.get('Proteines_g', 0.0)):.1f} g P**  •  🍞 **{nutr_series.get('Glucides_g', 0.0):.1f} g G**  •  🥑 **{nutr_series.get('Lipides_g', 0.0):.1f} g L**")
            if r.get("steps"):
                with st.expander("👩‍🍳 Étapes"):
                    for i, step in enumerate(r["steps"], 1):
                        st.markdown(f"{i}. {step}")
            # Ajout au journal (quantité = somme g; ajustable ensuite)
            if cB.button("➕ Journal (Déjeuner)", key=f"coach_add_{r['name']}"):
                total_qty = sum(q for _, q in r["items"])
                insert_journal(dt.date.today().isoformat(), "Déjeuner", r["name"], total_qty, nutr_series.to_dict())
                st.success("Ajouté au Journal (Déjeuner).")
                st.rerun()

# ============ RECETTES (banque + création, images + macros auto) ============
def _render_recettes():
    st.markdown("### 🍽️ Recettes")
    _ensure_state_defaults()

    foods = load_foods()
    foods = foods.loc[:, ~foods.columns.duplicated()].copy()
    index_df = build_search_index(foods)

    cA, cB, cC = st.columns([3,1.5,1])
    q = cA.text_input("Rechercher (nom ou ingrédient)", value=st.session_state["recipe_filters"]["q"])
    tag = cB.selectbox("Catégorie", ["Toutes","Petit-déj","Déjeuner","Dîner","Collation","Pré-workout","Post-workout"], index=0)
    st.session_state["recipe_filters"] = {"q": q, "tag": tag}

    # Banque intégrée
    st.markdown("#### ⭐ Suggestions")
    suggested = [r for r in RECIPES if tag=="Toutes" or r["tag"]==tag]
    if q.strip():
        ql = q.lower()
        suggested = [r for r in suggested if (ql in r["name"].lower() or any(ql in n.lower() for n,_ in r["items"]))]

    for r in suggested[:8]:
        with st.container():
            cA, cB = st.columns([3,1])
            if r.get("image_url"):
                cB.image(r["image_url"], use_container_width=True)
            cA.markdown(f"**{r['name']}** — _{r['tag']}_")
            cA.caption("Ingrédients : " + " | ".join([f"{name} ({qty} g)" for name, qty in r["items"]]))
            nutr_series = _nutr_from_recipe_items(foods, index_df, r["items"])
            kcal = _energy_from_series(pd.Series({
                "Protéines_g": float(nutr_series.get("Protéines_g", nutr_series.get("Proteines_g", 0.0)) or 0.0),
                "Glucides_g":  float(nutr_series.get("Glucides_g", 0.0) or 0.0),
                "Lipides_g":   float(nutr_series.get("Lipides_g", 0.0) or 0.0),
            }))
            cA.write(f"🔥 **{kcal:.0f} kcal**  •  💪 **{nutr_series.get('Protéines_g', nutr_series.get('Proteines_g', 0.0)):.1f} g P**  •  🍞 **{nutr_series.get('Glucides_g', 0.0):.1f} g G**  •  🥑 **{nutr_series.get('Lipides_g', 0.0):.1f} g L**")
            if r.get("steps"):
                with st.expander("👩‍🍳 Étapes"):
                    for i, step in enumerate(r["steps"], 1):
                        st.markdown(f"{i}. {step}")
            if cB.button("➕ Journal (Déjeuner)", key=f"sugg_add_{r['name']}"):
                insert_journal(dt.date.today().isoformat(), "Déjeuner", r["name"], sum(q for _, q in r["items"]), nutr_series.to_dict())
                st.success("Ajouté au Journal (Déjeuner).")
                st.rerun()

    st.divider()
    with st.expander("➕ Créer une recette perso"):
        name = st.text_input("Nom", placeholder="ex: Porridge protéiné")
        tag_new = st.selectbox("Catégorie", ["Petit-déj","Déjeuner","Dîner","Collation","Pré-workout","Post-workout"])
        items = st.session_state.setdefault("new_recipe_items", [])
        img = st.text_input("Image (URL, optionnel)", placeholder="https://…")
        # Ajout ingrédient
        c1, c2, c3 = st.columns([3,1,1])
        qi = c1.text_input("Ingrédient", placeholder="ex: avoine", key="rec_q")
        res = search_foods(index_df, qi, limit=10, page=1) if qi else pd.DataFrame()
        choice = c1.selectbox("Résultats", res["nom"].tolist(), key="rec_pick", label_visibility="collapsed") if not res.empty else None
        qty = c2.number_input("Quantité (g)", min_value=1, value=50, step=10)
        if c3.button("Ajouter l’ingrédient"):
            if choice:
                items.append({"food": choice, "qty_g": qty})
                st.session_state["new_recipe_items"] = items
                st.rerun()

        if items:
            st.write("**Ingrédients :**")
            for i, it in enumerate(items):
                col1, col2, col3 = st.columns([4,1,1])
                col1.write(f"- {it['food']}")
                col2.write(f"{it['qty_g']} g")
                if col3.button("🗑️", key=f"del_ing_{i}"):
                    items.pop(i); st.session_state["new_recipe_items"] = items; st.rerun()

        steps = st.text_area("Étapes (une par ligne)")
        if st.button("Enregistrer la recette"):
            if name.strip() and items:
                pairs = [(it["food"], it["qty_g"]) for it in items]
                nutr_series = _nutr_from_recipe_items(foods, index_df, pairs)
                st.session_state["recipes"].append({
                    "name": name.strip(),
                    "tag": tag_new,
                    "items": pairs,
                    "macros": nutr_series,
                    "image_url": img.strip() if img.strip() else None,
                    "steps": [s.strip() for s in steps.splitlines() if s.strip()]
                })
                st.session_state["new_recipe_items"] = []
                st.success(f"Recette « {name} » enregistrée !")
                st.rerun()

    # Recettes perso
    data = st.session_state.get("recipes", [])
    if data:
        st.markdown("#### 📒 Mes recettes")
        for i, r in enumerate(data):
            with st.container():
                cA, cB = st.columns([3,1])
                if r.get("image_url"):
                    cB.image(r["image_url"], use_container_width=True)
                tt = r["macros"] if isinstance(r["macros"], pd.Series) else _to_series(r["macros"])
                kcal = _energy_from_series(pd.Series({
                    "Protéines_g": float(tt.get("Protéines_g", tt.get("Proteines_g", 0.0)) or 0.0),
                    "Glucides_g":  float(tt.get("Glucides_g", 0.0) or 0.0),
                    "Lipides_g":   float(tt.get("Lipides_g", 0.0) or 0.0),
                }))
                p = float(tt.get("Protéines_g", tt.get("Proteines_g", 0.0)) or 0.0)
                g = float(tt.get("Glucides_g", 0.0) or 0.0)
                l = float(tt.get("Lipides_g", 0.0) or 0.0)
                cA.markdown(f"**{r['name']}** — _{r.get('tag','')}_")
                cA.write(f"🔥 **{kcal:.0f} kcal**  •  💪 **{p:.1f} g P**  •  🍞 **{g:.1f} g G**  •  🥑 **{l:.1f} g L**")
                cA.caption(" | ".join([f"{it[0]} ({it[1]} g)" for it in r["items"]]))
                if r.get("steps"):
                    with st.expander("👩‍🍳 Étapes"):
                        for j, step in enumerate(r["steps"], 1):
                            st.markdown(f"{j}. {step}")
                if cB.button("➕ Journal (Déjeuner)", key=f"add_rec_{i}"):
                    insert_journal(dt.date.today().isoformat(), "Déjeuner", r["name"], sum(it[1] for it in r["items"]), tt.to_dict())
                    st.success("Ajouté au Journal (Déjeuner).")
                    st.rerun()

# ============ NUTRI (macro + encyclopédie micro) ============
def _render_nutri():
    st.markdown("### 📚 Nutri — repères visuels")
    # Macros (fiches)
    cards = [
        ("💪 Protéines",  "Satiété, maintien musculaire. Vise ~1.2–1.6 g/kg/j.",
         ["Poulet/poisson", "Tofu/tempeh", "Yaourt grec", "Œufs"], "Répartis sur 2–3 repas."),
        ("🍞 Glucides",   "Énergie. Préfère IG bas & riches en fibres.",
         ["Avoine/quinoa", "Patate douce", "Légumineuses", "Fruits"], "Combine avec fibres/protéines."),
        ("🥑 Lipides",    "Hormones & membranes. Favorise insaturés (ω-3/ω-9).",
         ["Huile d’olive", "Noix", "Poissons gras", "Avocat"], "1–2 càs d’huiles de qualité/j."),
        ("🌾 Fibres",     "Microbiote, satiété, métabolisme.",
         ["Lentilles", "Pois chiches", "Fruits rouges", "Chia/lin"], "Objectif ~30 g/j."),
    ]
    for title, why, examples, tip in cards:
        with st.expander(title):
            st.markdown(f"**Bénéfices clés** — {why}")
            st.markdown("**Sources** — " + ", ".join(examples))
            st.info(tip)

    st.divider()
    st.markdown("### 🍊 Encyclopédie micronutriments (rôle • sources • repère)")
    for m in MICROS:
        with st.expander(m["name"]):
            st.markdown(f"**Rôles & bénéfices** — {m['why']}")
            st.markdown(f"**Où les trouver ?** — {m['sources']}")
            st.caption(f"**Repère quotidien** — {m['rdi']}")
    with st.expander("ℹ️ Sources"):
        st.caption("Repères issus d’organismes de référence (ex: ANSES/EFSA/WHO). Présentation adaptée en langage simple.")

# ============ DÉFIS (gamification simple) ============
def _render_defis():
    st.markdown("### 🏆 Défis & motivation")
    _ensure_state_defaults()
    today = dt.date.today().isoformat()
    if st.session_state.get("challenge_day") != today:
        st.session_state["challenge_done"] = False
        st.session_state["challenge_day"] = today

    st.write("**Défi du jour** :")
    d1 = st.checkbox("Boire 2 verres d’eau au réveil")
    d2 = st.checkbox("10 minutes de marche active")
    d3 = st.checkbox("Ajouter 1 portion de légumes verts aujourd’hui")

    if st.button("Valider mes défis"):
        st.session_state["challenge_done"] = bool(d1 or d2 or d3)
        st.success("Bravo ! Challenge du jour validé ✅")

# ============ RENDER PRINCIPAL ============
def render_alimentation_tab():
    st.subheader("💡 Alimentation")
    _ensure_state_defaults()
    active = _header_nav()
    tabs = {
        "Conseils": _render_conseils,
        "Coach IA": _render_coach,
        "Recettes": _render_recettes,
        "Nutri": _render_nutri,
        "Défis": _render_defis
    }
    tabs.get(active, _render_conseils)()
