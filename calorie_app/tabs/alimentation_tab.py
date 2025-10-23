import streamlit as st
import pandas as pd
import datetime as dt

from calorie_app.core.calc import excel_like_targets, calc_from_food_row
from calorie_app.core.data import fetch_journal_by_date, insert_journal
from calorie_app.core.load import load_foods
from calorie_app.core.search import build_search_index, search_foods
from calorie_app.core.coach import (
    weekly_targets_from_daily, weekly_totals, analyze_week, analyze_today, build_actions
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
    cols = st.columns(4)
    labels = ["Conseils", "Recettes", "Nutri", "Coach IA"]
    for i, lab in enumerate(labels):
        html = f'<div class="pill {"active" if active==lab else ""}">{lab}</div>'
        if cols[i].button(lab, key=f"pill_{lab}"):
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

# ============ CONSEILS (plus pertinent + alertes du jour) ============
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

    # Diagnostic semaine + alertes du jour (pizza, salé, sucré…)
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

    # Plan d’action synthétique
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

# ============ COACH IA (différent: propose des recettes ciblées) ============
def _render_coach():
    st.markdown("### 🤖 Coach IA — recommandations personnalisées")
    profile = st.session_state.get("profile", {})
    daily_targets = excel_like_targets(profile)
    week_targets = weekly_targets_from_daily(daily_targets)
    end_date = st.session_state.get("date_bilan", dt.date.today())
    week = weekly_totals(end_date, fetch_journal_by_date)
    diag = analyze_week(week, week_targets)

    # Traduit les gaps/limits en besoins “goals”
    needs = []
    for label, _ in diag.get("gaps", []):
        if "Protéines" in label: needs.append("proteines")
        if "Fibres" in label:    needs.append("fibres")
        if "Oméga-3 ALA" in label: needs.append("ala")
        if "Glucides" in label:  needs.append("glucides")
        if "Lipides" in label:   needs.append("lipides")
    for label, _, _ in diag.get("limits", []):
        if "Sucres" in label:    needs.append("fibres")  # aider à lisser
        if "AG saturés" in label: needs.append("ala")    # basculer vers bons lipides
        if "Sel" in label:       needs.append("micros")  # + aliments bruts

    st.caption("Suggestions basées sur tes 7 derniers jours :")
    tag = st.selectbox("Moment", ["Toutes","Petit-déj","Déjeuner","Dîner","Collation","Pré-workout","Post-workout"], index=0)
    picks = suggest_recipes(needs or ["proteines","fibres"], tag_filter=tag, limit=6)

    for r in picks:
        with st.container():
            cA, cB = st.columns([3,1])
            cA.markdown(f"**{r['name']}** — _{r['tag']}_")
            cA.caption(" | ".join([f"{name} ({qty} g)" for name, qty in r["items"]]))
            goals_txt = ", ".join(GOAL_MAP[g] for g in r["goals"])
            cA.write(f"🎯 {goals_txt}")
            if cB.button("➕ Journal (Déjeuner)", key=f"coach_add_{r['name']}"):
                # On ajoute la recette comme une préparation “rapide” (quantité = somme g)
                total_qty = sum(q for _, q in r["items"])
                # On ne recalcule pas les micros exacts ici (restera optionnel)
                insert_journal(dt.date.today().isoformat(), "Déjeuner", r["name"], total_qty, {})
                st.success("Ajouté au Journal (Déjeuner). Ouvre Journal pour ajuster la portion si besoin.")
                st.rerun()

# ============ RECETTES (banque + création) ============
def _render_recettes():
    st.markdown("### 🍽️ Recettes")
    _ensure_state_defaults()

    foods = load_foods()
    foods = foods.loc[:, ~foods.columns.duplicated()].copy()
    index_df = build_search_index(foods)

    # Filtres & moteur
    cA, cB, cC = st.columns([3,1.5,1])
    q = cA.text_input("Rechercher une recette (nom ou ingrédient)", value=st.session_state["recipe_filters"]["q"])
    tag = cB.selectbox("Catégorie", ["Toutes","Petit-déj","Déjeuner","Dîner","Collation","Pré-workout","Post-workout"], index=0)
    st.session_state["recipe_filters"] = {"q": q, "tag": tag}

    # Banque intégrée (RECIPES du catalog)
    st.markdown("#### ⭐ Suggestions par moment")
    suggested = [r for r in suggest_recipes([], tag_filter=tag, limit=6)]
    for r in suggested:
        with st.container():
            cA, cB = st.columns([3,1])
            cA.markdown(f"**{r['name']}** — _{r['tag']}_")
            cA.caption(" | ".join([f"{name} ({qty} g)" for name, qty in r["items"]]))
            if cB.button("➕ Journal (Déjeuner)", key=f"sugg_add_{r['name']}"):
                insert_journal(dt.date.today().isoformat(), "Déjeuner", r["name"], sum(q for _, q in r["items"]), {})
                st.success("Ajouté au Journal (Déjeuner).")
                st.rerun()

    st.divider()
    with st.expander("➕ Créer une recette perso"):
        name = st.text_input("Nom de la recette", placeholder="ex: Porridge protéiné")
        tag_new = st.selectbox("Catégorie", ["Petit-déj","Déjeuner","Dîner","Collation","Pré-workout","Post-workout"])
        items = st.session_state.setdefault("new_recipe_items", [])
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

        if st.button("Enregistrer la recette"):
            if name.strip() and items:
                total = pd.Series(dtype=float)
                for it in items:
                    row = foods.loc[foods["nom"].astype(str) == it["food"]]
                    if not row.empty:
                        nutr = calc_from_food_row(row.iloc[0], it["qty_g"])
                        total = (total.add(nutr, fill_value=0) if not total.empty else nutr)
                st.session_state["recipes"].append({"name": name.strip(), "tag": tag_new, "items": items.copy(), "macros": total})
                st.session_state["new_recipe_items"] = []
                st.success(f"Recette « {name} » enregistrée !")
                st.rerun()

    # Recettes perso sauvegardées
    data = st.session_state.get("recipes", [])
    if data:
        st.markdown("#### 📒 Mes recettes")
        for i, r in enumerate(data):
            with st.container():
                tt = r["macros"] if isinstance(r["macros"], pd.Series) else pd.Series(dtype=float)
                kcal = _energy_from_series(pd.Series({
                    "Protéines_g": tt.get("Protéines_g", tt.get("Proteines_g", 0.0)),
                    "Glucides_g":  tt.get("Glucides_g", 0.0),
                    "Lipides_g":   tt.get("Lipides_g", 0.0),
                }))
                p = float(tt.get("Protéines_g", tt.get("Proteines_g", 0.0)) or 0.0)
                g = float(tt.get("Glucides_g", 0.0) or 0.0)
                l = float(tt.get("Lipides_g", 0.0) or 0.0)
                cA, cB, cC, cD, cE = st.columns([4,2,2,2,2])
                cA.markdown(f"**{r['name']}** — _{r.get('tag','')}_")
                cB.write(f"🔥 {kcal:.0f} kcal")
                cC.write(f"💪 {p:.1f} g P")
                cD.write(f"🍞 {g:.1f} g G")
                cE.write(f"🥑 {l:.1f} g L")
                c1, c2 = st.columns([3,1])
                c1.caption(" | ".join([f"{it['food']} ({it['qty_g']} g)" for it in r["items"]]))
                if c2.button("➕ Journal (Déjeuner)", key=f"add_rec_{i}"):
                    insert_journal(dt.date.today().isoformat(), "Déjeuner", r["name"], sum(it["qty_g"] for it in r["items"]), r["macros"])
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
            st.markdown(f"**Pourquoi ?** {why}")
            st.markdown("**Sources clés :** " + ", ".join(examples))
            st.info(tip)

    st.divider()
    st.markdown("### 🍊 Encyclopédie micronutriments (rôle • sources • repère)")
    for m in MICROS:
        with st.expander(m["name"]):
            st.markdown(f"**Rôle** — {m['why']}")
            st.markdown(f"**Sources** — {m['sources']}")
            st.caption(f"**Repère quotidien** — {m['rdi']}")

# ============ RENDER PRINCIPAL ============
def render_alimentation_tab():
    st.subheader("💡 Alimentation")
    active = _header_nav()
    tabs = {"Conseils": _render_conseils, "Recettes": _render_recettes, "Nutri": _render_nutri, "Coach IA": _render_coach}
    tabs.get(active, _render_conseils)()
