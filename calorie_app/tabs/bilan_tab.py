import streamlit as st
import pandas as pd
import numpy as np
import re, unicodedata
import datetime as dt
import plotly.graph_objects as go

# ===== Couleurs (restent cohérentes avec ton ancien visuel) =====
COLORS = {
    "brand":    "#ff7f3f",   "brand2":   "#ffb347",
    "ink":      "#0d1b1e",   "muted":    "#5f6b76",
    "energie":   "#ff7f3f",  "proteines": "#2ca02c",
    "glucides":  "#1f77b4",  "lipides":   "#d62728",
    "fibres":    "#9467bd",  "omega3":    "#00bcd4",
    "epa":       "#26a69a",  "dha":       "#7e57c2",
    "omega6":    "#ffb300",  "omega9":    "#8d6e63",
    "restant":   "#e0e0e0",  "objectif":  "#bdbdbd",
    "ok":        "#5cb85c",  "warn":      "#f0ad4e", "bad":"#d9534f",
}

# ===== Backend existant (on ne change pas tes autres fichiers) =====
from calorie_app.core.data import fetch_journal_by_date, fetch_last_date_with_rows
from calorie_app.core.calc import excel_like_targets

# ===== Petits helpers (identiques à l’esprit de ton app.py) =====
def strip_accents(text: str) -> str:
    text = str(text or "")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

def canon(s: str) -> str:
    s = strip_accents(str(s)).lower().replace("_", " ").replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()

def canon_key(s: str) -> str:
    return canon(s).replace("(", "").replace(")", "").replace("’", "'").replace(" ", "").replace("__", "_")

def round1(x) -> float:
    try: return float(np.round(float(x), 1))
    except Exception: return 0.0

def parse_name_unit(label: str) -> tuple[str,str]:
    if label is None: return "", ""
    s = str(label).strip()
    parts = re.split(r"\s*[-–—]\s*", s)
    if len(parts) >= 2:
        unit = normalize_unit(parts[-1])
        name = "-".join(parts[:-1]).strip()
        return name, unit
    return s, ""

def normalize_unit(u: str) -> str:
    x = canon(u).replace(" ", "")
    if x in {"g","gramme","grammes"}: return "g"
    if x in {"mg","milligramme","milligrammes"}: return "mg"
    if x in {"ug","µg","mcg"}: return "µg"
    if x in {"kcal","calories","calorie"}: return "kcal"
    return u

def macro_base_name(label: str) -> str:
    name, _ = parse_name_unit(label); nc = canon(name); ns = nc.replace(" ", "")
    if nc.startswith("energie"): return "energie"
    if nc.startswith("proteine"): return "proteines"
    if nc.startswith("glucide"): return "glucides"
    if nc.startswith("lipide"): return "lipides"
    if nc.startswith("sucres"): return "sucres"
    if "acides gras satures" in nc or "ag satures" in nc or "agsatures" in nc: return "agsatures"
    if "omega9" in ns or ("oleique" in nc and "w9" in nc): return "omega9"
    if "omega6" in ns or ("linoleique" in nc and ("w6" in nc or "la" in nc)): return "omega6"
    if "epa" in nc: return "epa"
    if "dha" in nc: return "dha"
    if "omega3" in ns or "w3" in ns or ("alpha" in nc and "linolenique" in nc) or "ala" in nc: return "ala"
    if nc.startswith("fibres"): return "fibres"
    if nc.startswith("sel"): return "sel"
    return name

def pct_color(p):
    if pd.isna(p): return COLORS["warn"]
    if p >= 100: return COLORS["ok"]
    if p >= 50:  return COLORS["warn"]
    return COLORS["bad"]

def drop_parasite_columns(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty: return df
    cols = []
    for c in df.columns:
        sc = str(c).strip().lower()
        if sc == "" or sc.startswith("unnamed") or sc in {"done","none","nan"}:
            continue
        cols.append(c)
    out = df[cols]
    return out.loc[:, ~(out.isna().all())]

# Unifications (pour retrouver les colonnes même si l’appellation varie)
PREFERRED_NAMES = {
    "energiekcal":"Énergie_kcal", "proteinesg":"Protéines_g", "glucidesg":"Glucides_g", "lipidesg":"Lipides_g",
    "fibresg":"Fibres_g", "agsaturesg":"AG_saturés_g",
    "acideoleiquew9g":"Acide_oléique_W9_g", "acidelinoleiquew6lag":"Acide_linoléique_W6_LA_g",
    "acidealphalinoleniquew3alag":"Acide_alpha-linolénique_W3_ALA_g",
    "omega3alag":"Acide_alpha-linolénique_W3_ALA_g", "omega3ala":"Acide_alpha-linolénique_W3_ALA_g",
    "w3alag":"Acide_alpha-linolénique_W3_ALA_g", "alag":"Acide_alpha-linolénique_W3_ALA_g",
    "epag":"EPA_g", "dhag":"DHA_g", "sucresg":"Sucres_g", "selg":"Sel_g",
}

def unify_totals_series(s: pd.Series) -> pd.Series:
    if not isinstance(s, pd.Series) or s.empty: return s
    buckets: dict[str, float] = {}; name_for_bucket: dict[str,str] = {}
    for col in s.index:
        key = canon_key(col); preferred = PREFERRED_NAMES.get(key); bucket = preferred or key
        buckets[bucket] = buckets.get(bucket, 0.0) + float(s[col] or 0.0)
        if preferred: name_for_bucket[bucket] = preferred
        else: name_for_bucket.setdefault(bucket, col)
    out = pd.Series({name_for_bucket[k]: v for k,v in buckets.items()})
    if "Énergie_kcal" not in out.index and "Energie_kcal" in out.index: out["Énergie_kcal"] = out["Energie_kcal"]
    return out

def unify_totals_for_date(date_iso: str) -> pd.Series:
    df_today = fetch_journal_by_date(date_iso)
    if not df_today.empty:
        base_exclude = {"id","date","repas","nom","quantite_g"}
        df_clean = drop_parasite_columns(df_today).copy()
        for c in df_clean.columns:
            if c not in base_exclude: df_clean[c] = pd.to_numeric(df_clean[c], errors="coerce")
        df_num = df_clean.drop(columns=[c for c in base_exclude if c in df_clean.columns], errors="ignore")
        raw = df_num.sum(numeric_only=True)
        return unify_totals_series(raw)
    return pd.Series(dtype=float)

# ===== Donut identique à ton rendu =====
def donut(cons, target, title, color_key="energie", height=210):
    cons = float(cons or 0.0); target = float(target or 0.0)
    if target <= 0:
        fig = go.Figure(data=[go.Pie(values=[1], labels=["Objectif manquant"], hole=0.68,
                                     textinfo="label", marker_colors=[COLORS["objectif"]])])
        fig.update_layout(title=title, margin=dict(l=0,r=0,t=34,b=0), height=height, showlegend=False,
                          font=dict(size=13), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig
    pct = 0 if target == 0 else cons/target*100
    wedge = COLORS["ok"] if pct>=100 else (COLORS["warn"] if pct>=50 else COLORS["bad"])
    rest = max(target - cons, 0.0)
    fig = go.Figure(data=[go.Pie(values=[cons, rest], labels=["Ingéré","Restant"], hole=0.70, textinfo="none",
                                 marker_colors=[wedge, COLORS["restant"]])])
    fig.update_layout(
        title=title,
        annotations=[dict(text=f"{cons:.1f}/{target:.1f}<br>({pct:.0f}%)", x=0.5, y=0.5, showarrow=False, font=dict(size=15))],
        margin=dict(l=0,r=0,t=32,b=0), height=height, showlegend=False, font=dict(size=13),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

def get_profile_targets_cached() -> dict:
    p = st.session_state["profile"]
    base = excel_like_targets(p)
    prof = {k: round1(v) for k,v in base.items()}
    st.session_state["profile_targets"] = prof
    return prof

# ===== Calcul robuste ALA (oméga-3) =====
def _find_ala_columns_in(dfcols: list[str]) -> list[str]:
    cols = []
    for c in dfcols:
        ck = canon_key(c)
        if "epa" in ck or "dha" in ck:
            continue
        # ALA : multiples variantes rencontrées
        if ("ala" in ck and ("omega3" in ck or "w3" in ck)) \
           or ("alpha" in ck and "linolen" in ck) \
           or ck.endswith("alag") or ck.endswith("ala") \
           or "acidealphalinoleniquew3" in ck:
            cols.append(c)
    return cols

def _ala_consumed_from_day(df: pd.DataFrame, totals_series: pd.Series) -> float:
    # 1) colonne exacte dans df du jour
    if df is not None and not df.empty and "Acide_alpha-linolénique_W3_ALA_g" in df.columns:
        return float(pd.to_numeric(df["Acide_alpha-linolénique_W3_ALA_g"], errors="coerce").fillna(0.0).sum())
    # 2) sinon, heuristique sur d’autres libellés possibles dans df
    if df is not None and not df.empty:
        ala_cols = _find_ala_columns_in(df.columns.tolist())
        if ala_cols:
            s = pd.DataFrame(df[ala_cols]).apply(pd.to_numeric, errors="coerce").fillna(0.0)
            return float(s.sum(numeric_only=True).sum())
    # 3) sinon, on tente dans la série de totaux
    if isinstance(totals_series, pd.Series) and not totals_series.empty:
        cand = _find_ala_columns_in(list(totals_series.index))
        if cand:
            return float(pd.to_numeric(totals_series[cand], errors="coerce").fillna(0.0).sum())
        if "Acide_alpha-linolénique_W3_ALA_g" in totals_series.index:
            return float(pd.to_numeric(pd.Series([totals_series["Acide_alpha-linolénique_W3_ALA_g"]]),
                                       errors="coerce").fillna(0.0).iloc[0])
    return 0.0

# ===== PAGE =====
def render_bilan_tab():
    st.subheader("📊 Bilan")

    # 1) Date par défaut = aujourd’hui (ou dernière journée renseignée)
    default_bilan_date = dt.date.today()
    last_with = fetch_last_date_with_rows()
    if last_with and fetch_journal_by_date(default_bilan_date.isoformat()).empty:
        if st.session_state.get("last_added_date"):
            try:
                default_bilan_date = pd.to_datetime(st.session_state["last_added_date"]).date()
            except Exception:
                default_bilan_date = pd.to_datetime(last_with).date()
        else:
            default_bilan_date = pd.to_datetime(last_with).date()

    date_bilan = st.date_input("Date", value=default_bilan_date, format="DD/MM/YYYY", key="date_bilan")
    df_day = fetch_journal_by_date(date_bilan.isoformat())
    totals = unify_totals_for_date(date_bilan.isoformat())

    xlt = excel_like_targets(st.session_state.get("profile", {}))
    targets_macro = st.session_state.get("targets_macro", pd.DataFrame()).copy()
    targets_micro = st.session_state.get("targets_micro", pd.DataFrame()).copy()

    # 2) Donuts — 3 paragraphes comme avant
    # 2.1 Macro principaux
    p = float(totals.get("Protéines_g", totals.get("Proteines_g", 0.0)) or 0.0)
    g = float(totals.get("Glucides_g", 0.0) or 0.0)
    l = float(totals.get("Lipides_g", 0.0) or 0.0)
    kcal = p*4 + g*4 + l*9
    st.markdown("### 🌾 Macros principaux")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.plotly_chart(donut(kcal, xlt["energie_kcal"], "Énergie (kcal)", "energie"), use_container_width=True)
    with c2: st.plotly_chart(donut(p,    xlt["proteines_g"], "Protéines (g)",  "proteines"), use_container_width=True)
    with c3: st.plotly_chart(donut(g,    xlt["glucides_g"],  "Glucides (g)",   "glucides"),  use_container_width=True)
    with c4: st.plotly_chart(donut(l,    xlt["lipides_g"],   "Lipides (g)",    "lipides"),   use_container_width=True)
    with c5: st.plotly_chart(donut(float(totals.get("Fibres_g", 0.0)), xlt.get("fibres_g", 30.0), "Fibres (g)", "fibres"), use_container_width=True)

    st.divider()

    # 2.2 Acides gras essentiels (incl. ALA robuste)
    ala = _ala_consumed_from_day(df_day, totals)
    epa = float(totals.get("EPA_g", 0.0))
    dha = float(totals.get("DHA_g", 0.0))
    o6  = float(totals.get("Acide_linoléique_W6_LA_g", totals.get("Acide_linoleique_W6_LA_g", 0.0)))
    o9  = float(totals.get("Acide_oléique_W9_g", totals.get("Acide_oleique_W9_g", 0.0)))
    st.markdown("### 🫒 Acides gras essentiels")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.plotly_chart(donut(ala, xlt.get("ala_w3_g", 0.0), "Oméga-3 ALA (g)", "omega3"), use_container_width=True)
    with c2: st.plotly_chart(donut(epa, xlt.get("epa_g", 0.25),     "EPA (g)",        "epa"),    use_container_width=True)
    with c3: st.plotly_chart(donut(dha, xlt.get("dha_g", 0.25),     "DHA (g)",        "dha"),    use_container_width=True)
    with c4: st.plotly_chart(donut(o6,  xlt.get("omega6_g", 0.0),   "Oméga-6 LA (g)", "omega6"), use_container_width=True)
    with c5: st.plotly_chart(donut(o9,  xlt.get("omega9_g", 0.0),   "Oméga-9 (g)",    "omega9"), use_container_width=True)

    st.divider()

    # 2.3 À surveiller (Sucres, AG saturés, Sel) — réclamé
    sucres   = float(totals.get("Sucres_g", 0.0))
    ag_sat   = float(totals.get("AG_saturés_g", totals.get("AG_satures_g", 0.0)))
    sel      = float(totals.get("Sel_g", totals.get("Sodium_g", 0.0)))
    st.markdown("### ⚠️ À surveiller")
    c1, c2, c3 = st.columns(3)
    with c1: st.plotly_chart(donut(sucres, xlt.get("sucres_g", 0.0), "Sucres (g)"), use_container_width=True)
    with c2: st.plotly_chart(donut(ag_sat, xlt.get("agsatures_g", 0.0), "AG saturés (g)"), use_container_width=True)
    with c3: st.plotly_chart(donut(sel,    xlt.get("sel_g", 6.0), "Sel (g)"), use_container_width=True)

    # Légende couleur (objectif atteint / en cours / insuffisant)
    st.caption("🟢 **Objectif atteint**  •  🟠 **En cours**  •  🔴 **Insuffisant**")

    st.divider()

    # 3) VITAMINES & MINÉRAUX — deux sections séparées, graphiques triés
    def build_micro_tables_from_targets_and_totals(targets_micro_df: pd.DataFrame, totals_series: pd.Series):
        if targets_micro_df is None or targets_micro_df.empty or "Nutriment" not in targets_micro_df.columns:
            return pd.DataFrame(), pd.DataFrame()

        df = targets_micro_df.copy()
        if "Objectif" not in df.columns:
            df["Objectif"] = np.nan

        def consumed_micro(r):
            name, unit = parse_name_unit(str(r["Nutriment"]))
            key = f"{name}_{normalize_unit(unit)}".replace(" ","_")
            # clé exacte
            if isinstance(totals_series, pd.Series) and key in totals_series.index and pd.notna(totals_series[key]):
                return float(totals_series[key])
            # sinon, matching canonique
            for idx in totals_series.index:
                if canon_key(idx) == canon_key(key):
                    return float(totals_series[idx])
            return 0.0

        df["Consommée"] = df.apply(consumed_micro, axis=1).astype(float)
        # Séparation vit / minéraux
        def is_vit(n: str) -> bool:
            n = strip_accents(str(n)).lower()
            return n.startswith("vit") or "vitamine" in n
        vit = df[df["Nutriment"].astype(str).apply(is_vit)].copy()
        mino= df[~df["Nutriment"].astype(str).apply(is_vit)].copy()

        # Tri demandé : du plus consommé au moins consommé (Indépendamment de l’objectif)
        vit = vit.sort_values("Consommée", ascending=False)
        mino= mino.sort_values("Consommée", ascending=False)
        return vit, mino

    vit, mino = build_micro_tables_from_targets_and_totals(targets_micro, totals)

    def micro_bar(df: pd.DataFrame, title: str):
        if df.empty:
            st.info(f"Aucune donnée pour {title.lower()}.")
            return
        d = df.copy()
        # couverture si objectif dispo
        if "Objectif" not in d.columns:
            d["Objectif"] = np.nan
        d["% objectif"] = (d["Consommée"] / pd.to_numeric(d["Objectif"], errors="coerce")) * 100.0
        d["% objectif"] = d["% objectif"].replace([np.inf,-np.inf], np.nan)

        xmax = float(max((pd.to_numeric(d["Objectif"], errors="coerce").max(skipna=True),
                          d["Consommée"].max(skipna=True)), default=0.0)) * 1.15 or 1.0
        height = max(320, int(24*len(d)) + 110)

        fig = go.Figure()
        # Objectif (fond gris)
        fig.add_bar(y=d["Nutriment"], x=pd.to_numeric(d["Objectif"], errors="coerce"),
                    name="Objectif", orientation="h",
                    marker_color=COLORS["objectif"], opacity=0.30,
                    hovertemplate="Objectif: %{x:.1f}<extra></extra>")
        # Ingéré (barre colorée avec code couleur %)
        fig.add_bar(y=d["Nutriment"], x=d["Consommée"],
                    name="Ingéré", orientation="h",
                    marker_color=[pct_color(v) for v in d["% objectif"]],
                    text=[f"{c:.1f}" + (f"/{o:.1f}" if pd.notna(o) else "") +
                          (f" ({p:.0f}%)" if pd.notna(p) else "")
                          for c,o,p in zip(d["Consommée"], d["Objectif"], d["% objectif"])],
                    textposition="outside", cliponaxis=False,
                    hovertemplate="Ingéré: %{x:.1f}<extra></extra>")
        fig.update_layout(barmode="overlay", title=title, xaxis_title="", yaxis_title="",
                          xaxis=dict(range=[0, xmax]),
                          height=height, margin=dict(l=6,r=6,t=36,b=8),
                          legend=dict(orientation="h", y=-0.18),
                          font=dict(size=13),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, config={"displaylogo":False,"responsive":True,"staticPlot":True}, use_container_width=True)

    # Sections séparées + tri par consommé (desc)
    st.markdown("### 🍊 Vitamines")
    micro_bar(vit,  "Vitamines — objectif vs ingéré")
    st.markdown("### 🧂 Minéraux")
    micro_bar(mino, "Minéraux — objectif vs ingéré")
