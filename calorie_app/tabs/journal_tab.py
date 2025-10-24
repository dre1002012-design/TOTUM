# calorie_app/tabs/journal_tab.py
import streamlit as st
import pandas as pd
import datetime as dt

from calorie_app.core.load import load_foods
from calorie_app.core.search import build_search_index, search_foods
from calorie_app.core.calc import excel_like_targets
from calorie_app.core.data import fetch_journal_by_date, insert_journal

# suppression : essaye d'importer delete_journal si dispo (sinon noop + message)
try:
    from calorie_app.core.data import delete_journal
except Exception:
    def delete_journal(_id: str):
        st.warning("Suppression non activée sur cette installation (fonction manquante).")

MEALS = ["Petit-déjeuner", "Déjeuner", "Dîner", "Collation"]

# ---------- Utils ----------
def _sum_numeric(df: pd.DataFrame, drop_cols=None) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    drop_cols = set(drop_cols or [])
    num = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    num = num.apply(pd.to_numeric, errors="coerce")
    return num.sum(numeric_only=True)

def _energy_from_series(s: pd.Series) -> float:
    p = float(s.get("Protéines_g", s.get("Proteines_g", 0)) or 0)
    g = float(s.get("Glucides_g", 0) or 0)
    l = float(s.get("Lipides_g", 0) or 0)
    return p*4 + g*4 + l*9

def _ensure_state():
    st.session_state.setdefault("journal_q", "")
    st.session_state.setdefault("journal_meal", "Déjeuner")
    st.session_state.setdefault("journal_qty", 100)
    st.session_state.setdefault("journal_page", 1)
    st.session_state.setdefault("journal_date", dt.date.today().isoformat())
    st.session_state.setdefault("favorites", set())

# ---------- Header métriques ----------
def _render_metrics_row(profile: dict, day_total: pd.Series):
    targets = excel_like_targets(profile)
    kcal = _energy_from_series(day_total)
    p = float(day_total.get("Protéines_g", day_total.get("Proteines_g", 0)) or 0)
    g = float(day_total.get("Glucides_g", 0) or 0)
    l = float(day_total.get("Lipides_g", 0) or 0)

    kcal_t = float(targets.get("kcal", 0) or (p*4+g*4+l*9))
    p_t = float(targets.get("protein_g", targets.get("proteines_g", 0)) or 0)
    g_t = float(targets.get("carb_g", targets.get("glucides_g", 0)) or 0)
    l_t = float(targets.get("fat_g", targets.get("lipides_g", 0)) or 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("kcal", f"{kcal:.0f}", f"{int(kcal_t) if kcal_t else 0} obj")
    c2.metric("P", f"{p:.0f} g", f"{int(p_t)} g obj")
    c3.metric("G", f"{g:.0f} g", f"{int(g_t)} g obj")
    c4.metric("L", f"{l:.0f} g", f"{int(l_t)} g obj")

# ---------- Ligne résultat ----------
def _render_result_row(row: pd.Series, chosen_meal: str, qty_g: int, favs: set):
    name = str(row.get("nom", ""))

    kcal = float(row.get("Énergie_kcal_100g", row.get("Energie_kcal_100g", row.get("kcal", 0))) or 0)
    p = float(row.get("Protéines_g_100g", row.get("Proteines_g_100g", row.get("protein_g", 0))) or 0)
    g = float(row.get("Glucides_g_100g", row.get("carb_g", 0)) or 0)
    l = float(row.get("Lipides_g_100g", row.get("fat_g", 0)) or 0)

    c1, c2, c3, c4, c5, c6 = st.columns([3,1,1,1,1,1])
    c1.write(("⭐ " if name in favs else "") + name)
    c2.write(f"{kcal:.0f} kcal")
    c3.write(f"P {p:.1f}")
    c4.write(f"G {g:.1f}")
    c5.write(f"L {l:.1f}")

    col_add = c6
    if col_add.button("➕", key=f"add_{name}_{chosen_meal}_{qty_g}"):
        factor = (qty_g / 100.0)
        nutr = {
            "Protéines_g": p * factor,
            "Glucides_g": g * factor,
            "Lipides_g": l * factor,
            "Énergie_kcal": kcal * factor
        }
        insert_journal(st.session_state["journal_date"], chosen_meal, name, qty_g, nutr)
        st.success(f"Ajouté à {chosen_meal} : {name} ({qty_g} g)")
        st.rerun()

# ---------- Journal du jour ----------
def _render_day_log(date_iso: str, favs: set):
    df = fetch_journal_by_date(date_iso)
    if df is None or df.empty:
        st.info("Aucun aliment ajouté pour cette date.")
        return

    # Favoris : petit rappel
    if favs:
        st.caption("⭐ Favoris : " + ", ".join(list(favs)[:6]))

    keep = ["id","date","repas","nom","quantite_g","Énergie_kcal","Protéines_g","Glucides_g","Lipides_g"]
    show = df[[c for c in keep if c in df.columns]].copy()

    for meal in MEALS:
        part = show.loc[show["repas"]==meal].copy() if "repas" in show.columns else pd.DataFrame()
        if part.empty:
            continue
        st.markdown(f"**{meal}**")

        # affichage + boutons actions
        for idx, r in part.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([3,1,1,1,1,1])
            c1.write(str(r.get("nom","")))
            c2.write(f"{float(r.get('Énergie_kcal', 0) or 0):.0f} kcal")
            c3.write(f"P {float(r.get('Protéines_g', 0) or 0):.1f}")
            c4.write(f"G {float(r.get('Glucides_g', 0) or 0):.1f}")
            c5.write(f"L {float(r.get('Lipides_g', 0) or 0):.1f}")

            # actions : favori + corbeille si id dispo
            name = str(r.get("nom",""))
            idv = r.get("id", None)
            fav_btn = c6.button(("⭐" if name not in favs else "★"), key=f"fav_{meal}_{idx}")
            if fav_btn:
                if name in favs:
                    favs.remove(name)
                else:
                    favs.add(name)
                st.session_state["favorites"] = favs
                st.rerun()

            if idv is not None and st.button("🗑️", key=f"del_{meal}_{idx}"):
                try:
                    delete_journal(idv)
                    st.success("Ligne supprimée.")
                except Exception as e:
                    st.error(f"Suppression impossible ({e}).")
                st.rerun()

        # total repas
        tot = _sum_numeric(part, drop_cols={"date","id","repas","nom"})
        kcal = float(tot.get("Énergie_kcal", 0) or 0)
        p = float(tot.get("Protéines_g", 0) or 0)
        g = float(tot.get("Glucides_g", 0) or 0)
        l = float(tot.get("Lipides_g", 0) or 0)
        st.caption(f"Total {meal} — 🔥 {kcal:.0f} kcal • 💪 {p:.1f} g P • 🍞 {g:.1f} g G • 🥑 {l:.1f} g L")

# ---------- Main ----------
def render_journal_tab():
    _ensure_state()
    st.subheader("🧾 Journal")

    # Date (clé unique)
    cc1, cc2 = st.columns([1.2, 1])
    with cc1:
        date_value = st.date_input(
            "Date",
            value=dt.date.fromisoformat(st.session_state["journal_date"]),
            key="journal_date_input",
        )
        st.session_state["journal_date"] = date_value.isoformat()
    with cc2:
        st.write("")

    # Métriques du jour (ligne de 4)
    day_df = fetch_journal_by_date(st.session_state["journal_date"])
    day_tot = _sum_numeric(day_df, drop_cols={"id","date","repas","nom","quantite_g"})
    profile = st.session_state.get("profile", {})
    _render_metrics_row(profile, day_tot)
    st.divider()

    # Barre de recherche (formulaire = moins de reruns)
    with st.form("search_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([2.2, 1, 1])
        q = c1.text_input("Rechercher un aliment…", key="journal_q", placeholder="ex: œuf, yaourt, avoine")
        meal = c2.selectbox("Repas", MEALS, index=MEALS.index(st.session_state["journal_meal"]))
        qty = c3.number_input("Quantité (g)", min_value=1, max_value=2000, value=int(st.session_state["journal_qty"]), step=25)
        c4, c5 = st.columns([1, 5])
        page = c4.number_input("Page", min_value=1, value=int(st.session_state["journal_page"]), step=1)
        submitted = c5.form_submit_button("Chercher")

    st.session_state["journal_meal"] = meal
    st.session_state["journal_qty"] = qty
    st.session_state["journal_page"] = int(page)

    foods = load_foods()
    foods = foods.loc[:, ~foods.columns.duplicated()].copy()
    index_df = build_search_index(foods)

    favs = set(st.session_state.get("favorites") or [])

    if q.strip():
        results = search_foods(index_df, q.strip(), limit=10, page=int(page))
        if results is None or results.empty:
            st.info("Aucun résultat.")
        else:
            st.caption("Résultats (10 / page)")
            # favoris d’abord
            fav_mask = results["nom"].isin(favs) if "nom" in results.columns else False
            if isinstance(fav_mask, pd.Series) and fav_mask.any():
                st.caption("⭐ Favoris en tête")
                for _, r in results.loc[fav_mask].iterrows():
                    _render_result_row(r, meal, qty, favs)
                for _, r in results.loc[~fav_mask].iterrows():
                    _render_result_row(r, meal, qty, favs)
            else:
                for _, r in results.iterrows():
                    _render_result_row(r, meal, qty, favs)
    else:
        st.info("Tape un mot-clé pour lancer la recherche (ex: poulet, riz, banane).")

    st.divider()
    _render_day_log(st.session_state["journal_date"], favs)
