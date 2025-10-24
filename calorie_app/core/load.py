# calorie_app/core/load.py
import os
import pandas as pd
import streamlit as st

ASSETS_DIR = os.environ.get("ASSETS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets"))
CSV_PATH = os.path.join(ASSETS_DIR, "foods.csv")
PARQUET_PATH = os.path.join(ASSETS_DIR, "foods.parquet")

DTYPES = {
    "id": "string",
    "nom": "string",
    "brand": "string",
    "category": "string",
    "serving_unit": "string",
}

NUM_COLS = [
    "Énergie_kcal_100g","Energie_kcal_100g","kcal",
    "Protéines_g_100g","Proteines_g_100g","protein_g",
    "Glucides_g_100g","carb_g",
    "Lipides_g_100g","fat_g",
    "Fibres_g_100g","fiber_g",
    "Sucres_g_100g","sugar_g",
]

def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def _load_parquet(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)

@st.cache_data(ttl=3600, show_spinner=False)
def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=DTYPES, low_memory=False)
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def load_foods() -> pd.DataFrame:
    """Charge la base aliments avec cache + Parquet pour la vitesse."""
    # Si on a déjà un parquet → le plus rapide
    if os.path.exists(PARQUET_PATH):
        df = _load_parquet(PARQUET_PATH)
        return _coerce_numeric(df)

    # Sinon on lit le CSV une seule fois, on normalise, on écrit le parquet
    df = _load_csv(CSV_PATH)
    # dédoublonnage colonnes
    df = df.loc[:, ~df.columns.duplicated()].copy()
    # normalisations utiles
    if "nom" in df.columns:
        df["nom"] = df["nom"].astype("string")
    # écriture parquet (si autorisé en écriture)
    try:
        df.to_parquet(PARQUET_PATH, index=False)
    except Exception:
        pass
    return _coerce_numeric(df)
