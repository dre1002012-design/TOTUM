"""
core/search.py — index et recherche rapide sur foods.csv
Ultra fluide, avec boost des favoris et des récents.
"""

import re
import pandas as pd
import streamlit as st
from calorie_app.core.utils import canon

# Colonnes clés à montrer dans les résultats compacts
RESULT_COLS = [
    "nom",
    "Énergie_kcal_100g", "Protéines_g_100g", "Glucides_g_100g", "Lipides_g_100g",
    "Fibres_g_100g", "Sucres_g_100g",
]

def _char_overlap_score(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb); union = max(len(sa | sb), 1)
    return inter / union

@st.cache_data(show_spinner=False)
def build_search_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute _canon (nom normalisé) et ne garde que les colonnes utiles.
    (Dédup sur les colonnes du df, pas sur la liste 'keep'.)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["nom", "_canon"])

    idx = df.copy()
    # dédup colonnes côté df (par sécurité)
    idx = idx.loc[:, ~idx.columns.duplicated()].copy()

    # colonne 'nom' obligatoire
    if "nom" not in idx.columns:
        idx["nom"] = ""

    idx["nom"] = idx["nom"].astype(str)
    idx["_canon"] = idx["nom"].apply(canon)

        # on ne garde que ce qui existe réellement (et on déduplique l’ordre)
    keep = ["nom", "_canon"] + [c for c in RESULT_COLS if c in idx.columns]
    keep_unique = []
    for c in keep:
        if c in idx.columns and c not in keep_unique:
            keep_unique.append(c)
    idx = idx[keep_unique]
    return idx



def search_foods(index_df: pd.DataFrame, query: str, limit: int = 30, page: int = 1) -> pd.DataFrame:
    """
    Recherche en 4 passes puis score final avec boosts :
      1) startswith(_canon)
      2) all tokens present (AND)
      3) contains
      4) fallback similarité caractères
    Boosts : favoris (score +1), récents (score +0.5)
    Pagination par page (1-indexed).
    """
    if index_df is None or index_df.empty:
        return index_df

    q = (query or "").strip()
    if not q:
        # si pas de requête: on met en avant favoris puis récents
        res = index_df.copy()
        res = res.loc[:, ~res.columns.duplicated()].copy()        
        favs = set(st.session_state.get("fav_foods", []))
        recs = st.session_state.get("recent_foods", [])
        recs_set = set(recs)
        res["_score"] = 0.0
        res.loc[res["nom"].isin(recs_set), "_score"] += 0.5
        res.loc[res["nom"].isin(favs), "_score"] += 1.0
        res = res.sort_values("_score", ascending=False).drop(columns=["_score"])
        start = (max(page,1)-1)*limit
        return res.iloc[start:start+limit]

    q_canon = canon(q)
    tokens = [t for t in q_canon.split(" ") if t]

    m1 = index_df["_canon"].str.startswith(q_canon, na=False)
    part1 = index_df[m1]

    def all_tokens_present(s: str) -> bool:
        return all(t in s for t in tokens)
    remain = index_df[~m1]
    m2 = remain["_canon"].apply(all_tokens_present) if tokens else pd.Series(False, index=remain.index)
    part2 = remain[m2]
    remain = remain[~m2]

    m3 = remain["_canon"].str.contains(re.escape(q_canon), na=False)
    part3 = remain[m3]
    part4 = remain[~m3].copy()
    if not part4.empty:
        part4["_tmp"] = part4["_canon"].apply(lambda s: _char_overlap_score(s, q_canon))
        part4 = part4.sort_values("_tmp", ascending=False).drop(columns=["_tmp"])

    out = pd.concat([part1, part2, part3, part4]).drop_duplicates(subset=["nom"], keep="first")

    # Boosts
    favs = set(st.session_state.get("fav_foods", []))
    recs = st.session_state.get("recent_foods", [])
    recs_set = set(recs)
    out["_score_boost"] = 0.0
    out.loc[out["nom"].isin(recs_set), "_score_boost"] += 0.5
    out.loc[out["nom"].isin(favs),     "_score_boost"] += 1.0

    # Classement: priorité de passe (position) + boost
    out["_rank"] = range(len(out))
    out = out.sort_values(["_score_boost", "_rank"], ascending=[False, True]).drop(columns=["_score_boost", "_rank"])

    # Pagination
    start = (max(page,1)-1)*limit
    return out.iloc[start:start+limit]
