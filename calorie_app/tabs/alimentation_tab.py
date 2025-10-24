# calorie_app/tabs/alimentation_tab.py
import streamlit as st
import pandas as pd
import datetime as dt

from calorie_app.core.calc import excel_like_targets
from calorie_app.core.data import fetch_journal_by_date
from calorie_app.core.coach import (
    weekly_targets_from_daily, weekly_totals, analyze_week, analyze_today, build_actions
)
from calorie_app.core.motivation import quote_of_the_day
from calorie_app.core.catalog import MICROS

# ---------- Helpers ----------
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

def _ensure_state_defaults():
    st.session_state.setdefault("alim_tab", "Conseils")

# ---------- Conseils (simple, pertinent, compact) ----------
def _render_conseils():
    profile = st.session_state.get("profile", {})
    daily_targets = excel_like_targets(profile)
    week_targets = weekly_targets_from_daily(daily_targets)
    end_date = st.session_state.get("date_bilan", dt.date.today())
    week = weekly_totals(end_date, fetch_journal_by_date)

    st.caption("✨ " + quote_of_the_day(profile.get("prenom") or profile.get("nom")))

    kcal_w = _energy_from_series(week)
    p_w = float(week.get("Protéines_g", week.get("Proteines_g", 0.0)) or 0.0)
    g_w = float(week.get("Glucides_g", 0.0) or 0.0)
    l_w = float(week.get("Lipides_g", 0.0) or 0.0)
    fib_w = float(week.get("Fibres_g", 0.0) or 0.0)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("kcal/7j", f"{kcal_w:.0f}")
    c2.metric("P", f"{p_w:.0f} g")
    c3.metric("G", f"{g_w:.0f} g")
    c4.metric("L", f"{l_w:.0f} g")
    c5.metric("Fibres", f"{fib_w:.0f} g")

    diag = analyze_week(week, week_targets)
    today = analyze_today(
        _sum_numeric(fetch_journal_by_date(dt.date.today().isoformat()),
                     drop_cols={"id","date","repas","nom","quantite_g"}),
        daily_targets
    )
    if today.get("alerts"):
        st.error("Alerte : " + " • ".join(today["alerts"]))

    col1, col2 = st.columns(2)
    with col1:
        if diag.get("strengths"):
            st.success("Forces : " + " • ".join(diag["strengths"]))
        if diag.get("gaps"):
            st.warning("À renforcer : " + " • ".join([f"{n} ({cov:.0f}%)" for n, cov in diag["gaps"]]))
    with col2:
        if diag.get("limits"):
            st.warning("À limiter : " + " • ".join([n for n,_,_ in diag["limits"]]))

    st.markdown("#### 🎯 Plan d’action")
    plan = build_actions(diag)
    a1, a2, a3 = st.columns(3)
    with a1:
        st.markdown("**Ajouter**")
        for a in plan.get("to_add") or ["—"]:
            st.markdown("- " + a)
    with a2:
        st.markdown("**Limiter**")
        for a in plan.get("to_limit") or ["—"]:
            st.markdown("- " + a)
    with a3:
        st.markdown("**Lifestyle**")
        for a in plan.get("lifestyle") or ["—"]:
            st.markdown("- " + a)

# ---------- Nutri (encyclopédie compacte) ----------
def _render_nutri():
    st.markdown("### 📚 Repères micro (rôles • sources • repères)")
    for m in MICROS:
        with st.expander(m["name"]):
            st.markdown(f"**Rôles** — {m['why']}")
            st.markdown(f"**Sources** — {m['sources']}")
            st.caption(f"**Repère** — {m['rdi']}")

# ---------- Render principal ----------
def render_alimentation_tab():
    st.subheader("💡 Alimentation")
    _ensure_state_defaults()
    tabs = st.tabs(["Conseils","Nutri"])
    with tabs[0]:
        _render_conseils()
    with tabs[1]:
        _render_nutri()
