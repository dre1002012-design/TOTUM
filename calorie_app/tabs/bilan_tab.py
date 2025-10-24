# calorie_app/tabs/bilan_tab.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import datetime as dt

from calorie_app.core.data import fetch_journal_by_date
from calorie_app.core.calc import excel_like_targets

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

def _donut(value: float, goal: float, title: str, color="#FF7F3F", size=(2.0,2.0)):
    fig, ax = plt.subplots(figsize=size)
    v = max(0.0, float(value or 0.0))
    g = max(0.0001, float(goal or 0.0001))
    frac = min(v/g, 1.0)
    ax.pie([frac, 1-frac], startangle=90,
           colors=[color, "#EEE"], wedgeprops=dict(width=0.35, edgecolor="white"))
    ax.text(0, 0, f"{v:.0f}/{g:.0f}", ha="center", va="center", fontsize=10)
    ax.set_title(title, fontsize=10)
    ax.set(aspect="equal")
    plt.tight_layout()
    return fig

def _row_of_donuts(items, size=(2.0,2.0)):
    cols = st.columns(4)
    for i, (title, value, goal, color) in enumerate(items[:4]):
        with cols[i]:
            fig = _donut(value, goal, title, color=color, size=size)
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    if len(items) > 4:
        cols = st.columns(4)
        for i, (title, value, goal, color) in enumerate(items[4:8]):
            with cols[i]:
                fig = _donut(value, goal, title, color=color, size=size)
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

def _pct(value, goal):
    v = float(value or 0.0)
    g = float(goal or 0.0)
    return (v/g*100.0) if g>0 else 0.0

# ---------- Bilan ----------
def render_bilan_tab():
    st.subheader("📊 Bilan")

    date_value = st.date_input("Date", value=dt.date.today(), key="bilan_date_input")
    date_iso = date_value.isoformat()

    df = fetch_journal_by_date(date_iso)
    totals = _sum_numeric(df, drop_cols={"id","date","repas","nom","quantite_g"})

    profile = st.session_state.get("profile", {})
    targets = excel_like_targets(profile)

    # ---- Macros
    kcal = _energy_from_series(totals)
    p = float(totals.get("Protéines_g", totals.get("Proteines_g", 0)) or 0)
    g = float(totals.get("Glucides_g", 0) or 0)
    l = float(totals.get("Lipides_g", 0) or 0)

    kcal_t = float(targets.get("kcal", max(1.0, kcal)))
    p_t = float(targets.get("protein_g", targets.get("proteines_g", 0)) or 0)
    g_t = float(targets.get("carb_g", targets.get("glucides_g", 0)) or 0)
    l_t = float(targets.get("fat_g", targets.get("lipides_g", 0)) or 0)

    st.markdown("#### ⚙️ Macro (jour)")
    _row_of_donuts([
        ("kcal", kcal, kcal_t, "#FF7F3F"),
        ("Protéines (g)", p, p_t, "#4CAF50"),
        ("Glucides (g)", g, g_t, "#2196F3"),
        ("Lipides (g)",  l, l_t, "#9C27B0"),
    ], size=(1.8,1.8))

    # ---- AG essentiels (toutes clés tolérées, ALA corrigé)
    ala = float(totals.get("Omega3_ALA_g", totals.get("ALA_g", totals.get("AG_omega3_ALA_g", 0))) or 0)
    ala_t = float(targets.get("omega3_ala_g", targets.get("ALA_g_obj", 2.0)) or 2.0)
    epa_dha = float(totals.get("Omega3_EPA_DHA_g", totals.get("EPA_DHA_g", 0)) or 0)
    epa_dha_t = float(targets.get("omega3_epa_dha_g", 0.25) or 0.25)
    la_omega6 = float(totals.get("Omega6_Linoleic_g", totals.get("AG_omega6_LA_g", 0)) or 0)
    la_omega6_t = float(targets.get("omega6_la_g", 7.0) or 7.0)

    st.markdown("#### 🧬 Acides gras essentiels")
    _row_of_donuts([
        ("ω-3 ALA (g)", ala, ala_t, "#009688"),
        ("EPA+DHA (g)", epa_dha, epa_dha_t, "#00BCD4"),
        ("ω-6 LA (g)", la_omega6, la_omega6_t, "#FFC107"),
        ("Lipides (g)", l, l_t, "#9C27B0"),
    ], size=(1.8,1.8))

    # ---- À surveiller (si présents)
    sugars = totals.get("Sucres_g", totals.get("sugar_g", None))
    satfat = totals.get("AG_Satures_g", totals.get("saturated_fat_g", None))
    sodium = totals.get("Sodium_mg", totals.get("sel_mg", None))
    to_watch = []
    if sugars is not None:
        sug_t = float(targets.get("sugars_g", 50.0) or 50.0)
        to_watch.append(("Sucres (g)", float(sugars or 0), sug_t, "#F44336"))
    if satfat is not None:
        sat_t = float(targets.get("sat_fat_g", 20.0) or 20.0)
        to_watch.append(("AG saturés (g)", float(satfat or 0), sat_t, "#E91E63"))
    if sodium is not None:
        sod_t = float(targets.get("sodium_mg", 2000.0) or 2000.0)
        to_watch.append(("Sodium (mg)", float(sodium or 0), sod_t, "#795548"))
    if to_watch:
        st.markdown("#### ⚠️ À surveiller")
        _row_of_donuts(to_watch, size=(1.8,1.8))

    # ---- Vitamines & Minéraux (exhaustif, tri auto)
    # On scinde : vitamines d'abord (nom contient 'vit' ou prefixe 'vit_'), puis minéraux (_mg/_mcg hors 'vit')
    cols_all = list(totals.index)
    vit_cols = [c for c in cols_all if ("vit" in c.lower()) or c.lower().startswith("vit_")]
    mineral_cols = [c for c in cols_all if (c.endswith("_mg") or c.endswith("_mcg")) and (c not in vit_cols)]

    def _render_micro_section(title, cols):
        if not cols:
            return
        st.markdown(f"#### {title} (triés par % d’objectif)")
        data = []
        for c in cols:
            val = float(totals.get(c, 0) or 0)
            tgt_key = f"{c}_target"
            goal = float((targets.get(tgt_key) or 0))
            if goal <= 0:
                # repère par défaut prudent si non fourni
                goal = 400.0 if c.endswith("_mcg") else 1000.0
            data.append((c, val, goal, _pct(val, goal)))
        if not data:
            return
        dfm = pd.DataFrame(data, columns=["nutriment","val","obj","cov"]).sort_values("cov", ascending=False)

        # rendu compact : par lignes de 4, barres de progression
        top = dfm  # montre tout, mais compact
        for i in range(0, len(top), 4):
            row = top.iloc[i:i+4]
            cols = st.columns(len(row))
            for j, (_, r) in enumerate(row.iterrows()):
                with cols[j]:
                    cov = min(max(r["cov"], 0), 200)
                    st.progress(min(int(cov), 100), text=r["nutriment"])
                    st.caption(f"{r['val']:.0f}/{r['obj']:.0f}  ({cov:.0f}%)")

    _render_micro_section("🍊 Vitamines", vit_cols)
    _render_micro_section("🧱 Minéraux", mineral_cols)

    with st.expander("Légende"):
        st.write("🟢 objectif atteint • 🟠 en cours • 🔴 insuffisant — les anneaux montrent la part de l’objectif atteinte.")
