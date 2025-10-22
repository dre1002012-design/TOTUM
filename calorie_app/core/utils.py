"""
core/utils.py — fonctions utilitaires de base
(ne rien modifier sans raison)
"""

import re
import unicodedata
import pandas as pd
import numpy as np

# --- Nettoyage texte ---

def strip_accents(text: str) -> str:
    text = str(text or "")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")

def canon(s: str) -> str:
    s = strip_accents(str(s)).lower().replace("_", " ").replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()

def canon_key(s: str) -> str:
    return canon(s).replace("(", "").replace(")", "").replace("’", "'").replace(" ", "").replace("__", "_")

def norm(s: str) -> str:
    s = strip_accents(s).lower()
    return re.sub(r"[^a-z0-9]+", "", s)

def normalize_unit(u: str) -> str:
    u = (u or "").strip()
    u = u.replace("mcg", "µg").replace("ug", "µg").replace("μg", "µg")
    return u

# --- Données numériques ---

def coerce_num_col(s: pd.Series | None) -> pd.Series | None:
    """Convertit proprement une colonne texte en nombres"""
    if s is None: return None
    s = s.astype(str).str.replace("\u00A0", " ", regex=False).str.replace(",", ".", regex=False)
    ext = s.str.extract(r"([-+]?\d*\.?\d+)")[0]
    return pd.to_numeric(ext, errors="coerce")

def percent(n, d):
    n = pd.to_numeric(n, errors="coerce").fillna(0.0)
    d = pd.to_numeric(d, errors="coerce").replace(0, np.nan)
    return (n / d * 100).fillna(0.0)

def round1(x) -> float:
    try: return float(np.round(float(x), 1))
    except Exception: return 0.0
    
def norm(s: str) -> str:
    """Normalise une chaîne pour comparer sans accents ni majuscules."""
    s = str(s or "")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s.lower())
