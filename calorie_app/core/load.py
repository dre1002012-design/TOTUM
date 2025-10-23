import os, io
import pandas as pd
import streamlit as st

# Emplacements par défaut (tu peux ajuster si besoin)
CSV_PATH = os.path.join(os.getcwd(), "calorie_app", "data", "foods.csv")

# Fallback Excel (on réutilisera ta fonction de nettoyage existante à l’étape suivante)
from .excel import read_sheet_values_path as _read_sheet_values_path  # sera déjà présent
from pathlib import Path

DEFAULT_EXCEL_PATH = Path(os.getcwd()) / "assets" / "TOTUM-Suivi nutritionnel.xlsx"

# Colonnes minimales (on tolère les manquantes)
MIN_COLS = ["nom", "Énergie_kcal_100g", "Protéines_g_100g", "Glucides_g_100g", "Lipides_g_100g"]

def _coerce_float_cols(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if c.endswith("_100g"):
            df[c] = pd.to_numeric(pd.Series(df[c]).astype(str)
                                  .str.replace("\u00A0", " ", regex=False)
                                  .str.replace(",", ".", regex=False)
                                  .str.extract(r"([-+]?\d*\.?\d+)")[0], errors="coerce")
    return df

@st.cache_data(show_spinner=False)
def load_foods() -> pd.DataFrame:
    """
    1) Essaie d’abord le CSV (rapide).
    2) Si absent/vidé, fallback sur l’Excel (feuille 'Liste').
    3) Garantit: au moins les MIN_COLS, le reste en NaN si manquant.
    """
    df = pd.DataFrame()
    # 1) CSV direct
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH)
            df = _coerce_float_cols(df)
        except Exception as e:
            st.warning(f"CSV illisible, fallback Excel. Détail: {e}")

    # 2) Fallback Excel (si CSV manquant ou vide)
    if df is None or df.empty:
        try:
            if DEFAULT_EXCEL_PATH.exists():
                import openpyxl
                rows = list(openpyxl.load_workbook(DEFAULT_EXCEL_PATH, data_only=True, read_only=True)['Liste'].values)
                hdr = [str(x) if x is not None else "" for x in rows[0]]
                df = pd.DataFrame(rows[1:], columns=hdr)
                df = df.dropna(how="all").copy()
                df = _coerce_float_cols(df)
        except Exception as e:
            st.error(f"Impossible de charger les aliments (CSV/Excel). Détail: {e}")
            df = pd.DataFrame(columns=MIN_COLS)

    # 3) Contrat minimal
    for c in MIN_COLS:
        if c not in df.columns:
            df[c] = pd.NA

    # Normalisation douce
        df["nom"] = df["nom"].astype(str)
    # Suppression automatique des colonnes dupliquées
    df = df.loc[:, ~df.columns.duplicated()].copy()
    return df
