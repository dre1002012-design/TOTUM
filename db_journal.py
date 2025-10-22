# db_journal.py
# Accès unique et robuste à la base SQLite "totum.db" à la racine du projet.
# Schéma attendu (déjà présent chez toi) :
#  - table journal(id INTEGER PK, date TEXT, repas TEXT, nom TEXT, quantite_g REAL, nutrients_json TEXT)
#  - table profile(...)
#  - table favorites(nom TEXT PK)            <-- si absente, on la crée automatiquement

from __future__ import annotations
import json, os, sqlite3
from contextlib import contextmanager
from datetime import date as _date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --- Localisation DB : toujours ABSOLUE, quelle que soit la console courante
ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = str((ROOT_DIR / "totum.db").resolve())

def get_db_path() -> str:
    return DB_PATH

# --- Connexion + PRAGMA
@contextmanager
def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    finally:
        conn.close()

# --- Bootstrapping minimal : s'assure que la table favorites existe
def _ensure_schema():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS favorites(
                nom TEXT PRIMARY KEY
            )
        """)
_ensure_schema()

# -------- ÉCRITURE JOURNAL --------
def _mk_payload(kcal100: Optional[float], carbs100: Optional[float],
                prot100: Optional[float], fat100: Optional[float],
                grams: float) -> Dict:
    """Construit le JSON stocké dans nutrients_json (per100 + totals). Valeurs manquantes = 0."""
    k = float(kcal100 or 0.0)
    c = float(carbs100 or 0.0)
    p = float(prot100 or 0.0)
    f = float(fat100  or 0.0)
    g = float(grams or 0.0)

    factor = g / 100.0
    totals = {
        "kcal": round(k * factor, 2),
        "carbs": round(c * factor, 2),
        "prot": round(p * factor, 2),
        "fat": round(f * factor, 2),
    }
    per100 = {"kcal": k, "carbs": c, "prot": p, "fat": f}
    return {"per100": per100, "totals": totals}

def add_journal_entry(
    repas: str,
    nom: str,
    quantite_g: float,
    kcal100: Optional[float],
    carbs100: Optional[float],
    prot100: Optional[float],
    fat100: Optional[float],
    jour_iso: Optional[str] = None
) -> int:
    """
    Ajoute UNE ligne au journal.
    Retourne l'id de la ligne insérée.
    """
    d = jour_iso or _date.today().isoformat()
    payload = _mk_payload(kcal100, carbs100, prot100, fat100, quantite_g)
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO journal(date, repas, nom, quantite_g, nutrients_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (d, repas, nom, float(quantite_g), json.dumps(payload, ensure_ascii=False))
        )
        return cur.lastrowid

# -------- LECTURE JOUR --------
def read_entries_for_day(jour_iso: Optional[str] = None) -> List[Dict]:
    """Retourne les lignes du jour : [{id, repas, nom, q, k}, ...]"""
    d = jour_iso or _date.today().isoformat()
    out: List[Dict] = []
    with _conn() as c:
        for r in c.execute(
            "SELECT id, repas, nom, quantite_g, nutrients_json FROM journal WHERE date=? ORDER BY id ASC",
            (d,)
        ):
            try:
                payload = json.loads(r["nutrients_json"] or "{}")
                k = float(payload.get("totals", {}).get("kcal", 0.0))
            except Exception:
                k = 0.0
            out.append({
                "id": int(r["id"]),
                "repas": r["repas"],
                "nom": r["nom"],
                "q": float(r["quantite_g"]),
                "k": float(k),
            })
    return out

def read_totals_for_day(jour_iso: Optional[str] = None) -> Dict[str, float]:
    """Additionne les totals (kcal, carbs, prot, fat) du jour depuis nutrients_json."""
    d = jour_iso or _date.today().isoformat()
    K = C = P = F = 0.0
    with _conn() as c:
        for r in c.execute(
            "SELECT nutrients_json FROM journal WHERE date=?",
            (d,)
        ):
            try:
                payload = json.loads(r["nutrients_json"] or "{}")
                t = payload.get("totals", {})
                K += float(t.get("kcal", 0.0))
                C += float(t.get("carbs", 0.0))
                P += float(t.get("prot", 0.0))
                F += float(t.get("fat", 0.0))
            except Exception:
                continue
    return {"kcal": round(K, 2), "carbs": round(C, 2), "prot": round(P, 2), "fat": round(F, 2)}

# -------- UNDO dernière ligne du jour --------
def delete_last_for_day(jour_iso: Optional[str] = None) -> bool:
    d = jour_iso or _date.today().isoformat()
    with _conn() as c:
        cur = c.execute("SELECT id FROM journal WHERE date=? ORDER BY id DESC LIMIT 1", (d,))
        row = cur.fetchone()
        if not row:
            return False
        c.execute("DELETE FROM journal WHERE id=?", (row["id"],))
        return True

# -------- Favoris --------
def add_favorite(nom: str) -> bool:
    try:
        with _conn() as c:
            c.execute("INSERT OR IGNORE INTO favorites(nom) VALUES(?)", (nom.strip(),))
        return True
    except Exception:
        return False

def remove_favorite(nom: str) -> bool:
    try:
        with _conn() as c:
            c.execute("DELETE FROM favorites WHERE nom=?", (nom.strip(),))
        return True
    except Exception:
        return False

def list_favorites() -> List[str]:
    out: List[str] = []
    with _conn() as c:
        for r in c.execute("SELECT nom FROM favorites ORDER BY nom COLLATE NOCASE ASC"):
            out.append(r["nom"])
    return out
