"""
core/excel.py — utilitaires de lecture Excel (feuilles, nettoyage)
"""

from pathlib import Path
import io
import pandas as pd

# dépendances internes
from .utils import coerce_num_col, canon_key

def drop_parasite_columns(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Retire les colonnes vides/parasites (ex: 'Unnamed')."""
    if df is None or df.empty:
        return df
    cols = []
    for c in df.columns:
        sc = str(c).strip().lower()
        if sc == "" or sc.startswith("unnamed") or sc in {"done", "none", "nan"}:
            continue
        cols.append(c)
    out = df[cols]
    return out.loc[:, ~(out.isna().all())]

def read_sheet_values_path(path: Path, sheet_name: str) -> pd.DataFrame | None:
    """
    Lit une feuille Excel 'sheet_name' depuis 'path' en valeurs (pas de formules), et renvoie un DataFrame propre.
    """
    try:
        import openpyxl
        bio = io.BytesIO(Path(path).read_bytes())
        wb = openpyxl.load_workbook(bio, data_only=True, read_only=True)
        if sheet_name not in wb.sheetnames:
            return None
        ws = wb[sheet_name]
        rows = list(ws.values)
        if not rows:
            return None
        header = [str(x) if x is not None else "" for x in rows[0]]
        df = pd.DataFrame(rows[1:], columns=header)
        return drop_parasite_columns(df)
    except Exception:
        return None

def clean_liste(df_liste: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie la feuille 'Liste' : garde 'nom' + colonnes *_100g, convertit en numériques,
    et fusionne les colonnes quasi-identiques (canon_key).
    """
    df_liste = drop_parasite_columns(df_liste)
    assert "nom" in df_liste.columns, "La feuille 'Liste' doit contenir la colonne 'nom'."
    if "Energie_kcal_100g" in df_liste.columns and "Énergie_kcal_100g" not in df_liste.columns:
        df_liste = df_liste.rename(columns={"Energie_kcal_100g": "Énergie_kcal_100g"})
    keep = ["nom"] + [c for c in df_liste.columns if str(c).endswith("_100g")]
    df = df_liste[keep].copy()
    for c in [x for x in df.columns if str(x).endswith("_100g")]:
        df[c] = coerce_num_col(df[c]).fillna(0.0)

    # fusion douce de colonnes quasi identiques (même clé canonique)
    dup_groups: dict[str, list[str]] = {}
    for c in [x for x in df.columns if str(x).endswith("_100g")]:
        key = canon_key(c)
        dup_groups.setdefault(key, []).append(c)
    for cols in dup_groups.values():
        if len(cols) > 1:
            base = sorted(cols, key=len)[0]
            df[base] = df[cols].sum(axis=1, numeric_only=True)
            for extra in cols:
                if extra != base and extra in df.columns:
                    df.drop(columns=[extra], inplace=True, errors="ignore")
    return df
