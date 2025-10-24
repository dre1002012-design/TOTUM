# calorie_app/core/load.py
import os
import pandas as pd
import streamlit as st

ASSETS_DIR = os.environ.get("ASSETS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets"))
CSV_PATH = os.path.join(ASSETS_DIR, "foods.csv")

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
def load_foods() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, dtype=DTYPES, low_memory=False)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if "nom" in df.columns:
        df["nom"] = df["nom"].astype("string")
    return _coerce_numeric(df)
