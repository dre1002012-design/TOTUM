# timing_foods_io.py
# Mesure simple du temps de lecture de ta base aliments :
# - Excel (ton fichier d’origine)
# - CSV (assets/foods.csv)
#
# -> Objectif : voir si le gain de vitesse vient du CSV (probable).
import time
import pandas as pd
from pathlib import Path

# ⚠️ MODIFIE ICI avec le chemin de TON Excel d’origine (onglet aliments)
# Exemple possible :
# EXCEL_PATH = Path(r"C:\Users\Alexa\TOTUM-auth.api\assets\TOTUM-Suivi nutritionnel.xlsx")
EXCEL_PATH = Path(r"C:\Users\Alexa\TOTUM-auth.api\assets\TOTUM-Suivi nutritionnel.xlsx")

CSV_PATH = Path(r"C:\Users\Alexa\TOTUM-auth.api\assets\foods.csv")

def time_read_excel(path: Path):
    if not path.exists():
        print(f"[Excel] Fichier introuvable : {path}")
        return None, None
    t0 = time.perf_counter()
    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"[Excel] Erreur lecture : {e}")
        return None, None
    t1 = time.perf_counter()
    return df, t1 - t0

def time_read_csv(path: Path):
    if not path.exists():
        print(f"[CSV] Fichier introuvable : {path}")
        return None, None
    t0 = time.perf_counter()
    # Auto-détection du séparateur (virgule ou point-virgule)
    try:
        # Essai avec virgule
        df = pd.read_csv(path)
        if df.shape[1] == 1:
            # Probable séparateur ';'
            df = pd.read_csv(path, sep=';')
    except Exception as e:
        print(f"[CSV] Erreur lecture : {e}")
        return None, None
    t1 = time.perf_counter()
    return df, t1 - t0

print("=== Test lecture Excel vs CSV ===")

df_xlsx, t_xlsx = time_read_excel(EXCEL_PATH)
if t_xlsx is not None:
    print(f"[Excel] Lignes: {0 if df_xlsx is None else len(df_xlsx)}  | Temps: {t_xlsx:.3f} s")

df_csv, t_csv = time_read_csv(CSV_PATH)
if t_csv is not None:
    print(f"[CSV]   Lignes: {0 if df_csv is None else len(df_csv)}  | Temps: {t_csv:.3f} s")

if t_xlsx is not None and t_csv is not None:
    if t_xlsx > 0:
        print(f"→ Accélération estimée CSV vs Excel : x{t_xlsx / t_csv:.1f}")
