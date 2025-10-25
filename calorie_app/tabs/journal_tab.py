import streamlit as st
import pandas as pd
import datetime as dt

from calorie_app.core.style import apply_journal_style
from calorie_app.core.load import load_foods
from calorie_app.core.search import build_search_index, search_foods, RESULT_COLS
from calorie_app.core.calc import excel_like_targets, calc_from_food_row
from calorie_app.core.data import insert_journal, delete_journal_row, fetch_journal_by_date

# --- Constantes ---
MEALS = ["Petit-déjeuner", "Déjeuner", "Dîner", "Collation"]
BASE_EXCLUDE = {"id", "date", "repas", "nom", "quantite_g"}

# --- Helpers internes ---

def _sum_totals(df: pd.DataFrame) -> pd.Series:
    """Somme les colonnes numériques en ignorant les colonnes de base."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    num = df.drop(columns=[c for c in BASE_EXCLUDE if c in df.columns], errors="ignore")
    num = num.apply(pd.to_numeric, errors="coerce")
    return num.sum(numeric_only=True)

def _energy_from_totals(totals: pd.Series) -> float:
    """kcal estimées à partir des macros totales."""
    p = float(pd.to_numeric(pd.Series([totals.get("Protéines_g", totals.get("Proteines_g", 0.0))]), errors="coerce").fillna(0).iloc[0])
    g = float(pd.to_numeric(pd.Series([totals.get("Glucides_g", 0.0)]), errors="coerce").fillna(0).iloc[0])
    l = float(pd.to_numeric(pd.Series([totals.get("Lipides_g", 0.0)]), errors="coerce").fillna(0).iloc[0])
    return p * 4 + g * 4 + l * 9

def _ensure_lists():
    st.session_state.setdefault("fav_foods", [])       # noms favoris
    st.session_state.setdefault("recent_foods", [])    # derniers ajoutés (10 max)

def _push_recent(name: str, keep: int = 10):
    lst = st.session_state.get("recent_foods", [])
    if name in lst:
        lst.remove(name)
    lst.insert(0, name)
    st.session_state["recent_foods"] = lst[:keep]

# --- UI principale ---

def render_journal_tab():
    st.subheader("🧾 Journal")
    apply_journal_style()
    _ensure_lists()

    # 1) Données: foods + index
    foods = load_foods()
    foods = foods.loc[:, ~foods.columns.duplicated()].copy()
    st.session_state["foods"] = foods
    index_df = build_search_index(foods)

    # 2) Date et objectifs
    ctop1, ctop2 = st.columns([1, 1])
    date_sel = ctop1.date_input("Date", value=dt.date.today(), format="DD/MM/YYYY", key="date_journal")
    date_iso = date_sel.isoformat()
    profile = st.session_state.get("profile", {})
    targets = excel_like_targets(profile)

    # 3) Totaux du jour -> métriques en tête
    df_day = fetch_journal_by_date(date_iso)
    totals_day = _sum_totals(df_day)
    kcal = _energy_from_totals(totals_day)
    prot = float(totals_day.get("Protéines_g", totals_day.get("Proteines_g", 0.0)) or 0.0)
    gluc = float(totals_day.get("Glucides_g", 0.0) or 0.0)
    lip  = float(totals_day.get("Lipides_g", 0.0) or 0.0)

    st.markdown("#### 🎯 Objectifs clés (aujourd’hui)")
    kc, pr, gl, li = st.columns(4)
    kc.metric("Énergie (kcal)", f"{kcal:.0f}", f"/ {targets['energie_kcal']:.0f}")
    pr.metric("Protéines (g)", f"{prot:.1f}",   f"/ {targets['proteines_g']:.1f}")
    gl.metric("Glucides (g)", f"{gluc:.1f}",    f"/ {targets['glucides_g']:.1f}")
    li.metric("Lipides (g)",  f"{lip:.1f}",     f"/ {targets['lipides_g']:.1f}")

    st.divider()

    # 4) Recherche + pagination
    left, right = st.columns([3, 1])
    q = left.text_input("🔎 Rechercher un aliment", placeholder="Tape 2–3 lettres (ex: poulet, riz, pomme)", key="journal_search")
    page = right.number_input("Page", min_value=1, value=1, step=1, help="Pagination des résultats")
    results = search_foods(index_df, q, limit=15, page=int(page))
    results = results.loc[:, ~results.columns.duplicated()].copy()

    # Bandeau récents / favoris si pas de requête
    favs = set(st.session_state.get("fav_foods", []))
    if not q:
        chips = []
        if st.session_state.get("recent_foods"):
            chips.append("🕑 Récents: " + ", ".join(st.session_state["recent_foods"][:8]))
        if favs:
            chips.append("⭐ Favoris: " + ", ".join(list(favs)[:8]))
        if chips:
            st.caption(" •  ".join(chips))

    # 5) Sélecteur rapide (↑/↓ puis Entrée)
    if not results.empty:
        with st.form("quick_add_form", clear_on_submit=True):
            cqa, cqb, cqc, cqd = st.columns([4, 1.2, 1.6, 1.2])
            pick_name = cqa.selectbox(
                "Sélection (↑/↓)",
                options=results["nom"].tolist(),
                key="quick_pick",
                label_visibility="collapsed",
            )
            qty_q = cqb.number_input("g", min_value=1, value=150, step=10, label_visibility="collapsed", key="quick_qty")
            repas_q = cqc.selectbox("Repas", MEALS, index=1, label_visibility="collapsed", key="quick_meal")
            submitted = cqd.form_submit_button("➕ Ajouter (Entrée)")

            if submitted and pick_name:
                base = foods.loc[foods["nom"].astype(str) == pick_name]
                if not base.empty:
                    nutr = calc_from_food_row(base.iloc[0], qty_q)  # macro + micro depuis *_100g
                    insert_journal(date_iso, repas_q, pick_name, qty_q, nutr)
                    _push_recent(pick_name)
                    st.session_state["last_added_date"] = date_iso
                    st.success(f"Ajouté : {qty_q} g de {pick_name} ({repas_q})")
                    st.rerun()

    # 6) Résultats compacts avec actions par ligne
    st.markdown("##### Résultats")
    if results.empty:
        st.info("Aucun résultat. Essaie ‘pou’, ‘riz’, ‘pom’…")
    else:
        for i, row in results.iterrows():
            name = str(row["nom"])
            kcal100 = float(pd.to_numeric(pd.Series([row.get("Énergie_kcal_100g", 0)]), errors="coerce").fillna(0).iloc[0])
            p100 = float(pd.to_numeric(pd.Series([row.get("Protéines_g_100g", 0)]), errors="coerce").fillna(0).iloc[0])
            g100 = float(pd.to_numeric(pd.Series([row.get("Glucides_g_100g", 0)]), errors="coerce").fillna(0).iloc[0])
            l100 = float(pd.to_numeric(pd.Series([row.get("Lipides_g_100g", 0)]), errors="coerce").fillna(0).iloc[0])

            with st.container():
                cA, cB, cC, cD, cE = st.columns([5, 2, 2, 2, 3])
                cA.markdown(f"**{name}**  \n{int(kcal100)} kcal /100g — P {p100:.1f} • G {g100:.1f} • L {l100:.1f}")
                qty = cB.number_input("g", min_value=1, value=150, step=10, key=f"qty_{i}", label_visibility="collapsed")
                repas = cC.selectbox("Repas", MEALS, index=1, key=f"repas_{i}", label_visibility="collapsed")
                # favoris
                starred = name in favs
                if cD.button("⭐" if starred else "☆", key=f"fav_{i}", help="Ajouter/enlever des favoris"):
                    if starred:
                        st.session_state["fav_foods"] = [x for x in st.session_state["fav_foods"] if x != name]
                    else:
                        st.session_state["fav_foods"].append(name)
                    st.rerun()
                # ajouter
                if cE.button("➕ Ajouter", key=f"add_{i}"):
                    base = foods.loc[foods["nom"].astype(str) == name]
                    if not base.empty:
                        nutr = calc_from_food_row(base.iloc[0], qty)
                        insert_journal(date_iso, repas, name, qty, nutr)
                        _push_recent(name)
                        st.session_state["last_added_date"] = date_iso
                        st.success(f"Ajouté : {qty} g de {name} ({repas})")
                        st.rerun()

    st.divider()

    # 7) Aliment personnalisé
    with st.expander("➕ Aliment personnalisé"):
        c1, c2, c3 = st.columns([2, 1, 1])
        nom_pers = c1.text_input("Nom", placeholder="ex: Mon smoothie maison")
        repas_p  = c2.selectbox("Repas", MEALS, index=1, key="repas_perso")
        qty_pers = c3.number_input("Quantité (g)", min_value=1, value=200, step=10)

        st.caption("Valeurs pour 100 g — ne remplis que ce que tu connais.")
        m1, m2, m3, m4 = st.columns(4)
        prot100 = m1.number_input("Protéines (g/100g)", 0.0, step=0.5)
        gluc100 = m2.number_input("Glucides (g/100g)",  0.0, step=0.5)
        lip100  = m3.number_input("Lipides (g/100g)",   0.0, step=0.5)
        fib100  = m4.number_input("Fibres (g/100g)",    0.0, step=0.5)

        n1, n2, n3 = st.columns(3)
        ala100 = n1.number_input("Oméga-3 ALA (g/100g)", 0.0, step=0.1)
        epa100 = n2.number_input("EPA (g/100g)",         0.0, step=0.1)
        dha100 = n3.number_input("DHA (g/100g)",         0.0, step=0.1)

        o1, o2 = st.columns(2)
        o6100 = o1.number_input("Oméga-6 (LA) (g/100g)", 0.0, step=0.1)
        o9100 = o2.number_input("Oméga-9 (oléique) (g/100g)", 0.0, step=0.1)

        if st.button("Ajouter cet aliment personnalisé"):
            if nom_pers.strip():
                # reconstitue une "row 100g" minimale compatible avec calc_from_food_row
                row = pd.Series({
                    "Protéines_g_100g": prot100, "Glucides_g_100g": gluc100, "Lipides_g_100g": lip100,
                    "Fibres_g_100g": fib100, "Acide_alpha-linolénique_W3_ALA_g_100g": ala100,
                    "EPA_g_100g": epa100, "DHA_g_100g": dha100,
                    "Acide_linoléique_W6_LA_g_100g": o6100, "Acide_oléique_W9_g_100g": o9100,
                })
                kcal100 = prot100 * 4 + gluc100 * 4 + lip100 * 9
                row["Énergie_kcal_100g"] = kcal100
                nutr = calc_from_food_row(row, qty_pers)
                insert_journal(date_iso, repas_p, nom_pers.strip(), qty_pers, nutr)
                _push_recent(nom_pers.strip())
                st.success(f"Ajouté : {qty_pers} g de {nom_pers} ({repas_p})")
                st.rerun()

    st.divider()

    # 8) Journal du jour — par repas avec totaux + suppression
    st.markdown("### 🗒️ Journal du jour")
    df_day = fetch_journal_by_date(date_iso)
    if df_day is None or df_day.empty:
        st.info("Aucune entrée aujourd’hui — ajoute un aliment ci-dessus.")
        return

    for meal in MEALS:
        sub = df_day[df_day["repas"] == meal].copy()
        st.markdown(f"#### 🍽️ {meal}")
        if sub.empty:
            st.caption("—")
            continue

        # Totaux par repas
        t = _sum_totals(sub)
        kcal_m = _energy_from_totals(t)
        prot_m = float(t.get("Protéines_g", t.get("Proteines_g", 0.0)) or 0.0)
        gluc_m = float(t.get("Glucides_g", 0.0) or 0.0)
        lip_m  = float(t.get("Lipides_g", 0.0) or 0.0)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("kcal", f"{kcal_m:.0f}")
        c2.metric("P (g)", f"{prot_m:.1f}")
        c3.metric("G (g)", f"{gluc_m:.1f}")
        c4.metric("L (g)", f"{lip_m:.1f}")

        show_cols = ["id", "nom", "quantite_g", "Énergie_kcal", "Protéines_g", "Glucides_g", "Lipides_g"]
        show_cols = [c for c in show_cols if c in sub.columns]
        st.dataframe(sub[show_cols], use_container_width=True, hide_index=True)

        # Suppression
        col_del1, col_del2 = st.columns([4, 1])
        row_id = col_del1.selectbox(f"Supprimer dans {meal}", options=sub["id"].tolist(), format_func=lambda x: f"#{x}", key=f"del_{meal}")
        if col_del2.button("🗑️ Supprimer", key=f"btn_del_{meal}"):
            delete_journal_row(int(row_id))
            st.rerun()
