"""
core/data.py — accès à la base SQLite locale
"""

import sqlite3, json
import pandas as pd

DB_PATH = "totum.db"

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id=1),
            sexe TEXT, age INTEGER, taille_cm REAL, poids_kg REAL,
            activite TEXT, prot_pct INTEGER, gluc_pct INTEGER, lip_pct INTEGER
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            repas TEXT NOT NULL,
            nom TEXT NOT NULL,
            quantite_g REAL NOT NULL,
            nutrients_json TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn

def load_profile():
    conn = init_db()
    cur = conn.execute("SELECT sexe,age,taille_cm,poids_kg,activite,prot_pct,gluc_pct,lip_pct FROM profile WHERE id=1;")
    row = cur.fetchone()
    if row:
        return {"sexe":row[0],"age":row[1],"taille_cm":row[2],"poids_kg":row[3],
                "activite":row[4],"repartition_macros":(row[5],row[6],row[7])}
    return {"sexe":"Homme","age":40,"taille_cm":181.0,"poids_kg":72.0,
            "activite":"Sédentaire","repartition_macros":(30,55,15)}

def save_profile(p):
    conn = init_db()
    conn.execute("""
        INSERT INTO profile (id,sexe,age,taille_cm,poids_kg,activite,prot_pct,gluc_pct,lip_pct)
        VALUES (1,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            sexe=excluded.sexe, age=excluded.age, taille_cm=excluded.taille_cm, poids_kg=excluded.poids_kg,
            activite=excluded.activite, prot_pct=excluded.prot_pct, gluc_pct=excluded.gluc_pct, lip_pct=excluded.lip_pct;
    """, (p["sexe"], int(p["age"]), float(p["taille_cm"]), float(p["poids_kg"]),
          p["activite"], 30, 55, 15))
    conn.commit()

# === Journal helpers (on les ajoute déjà, utiles pour plus tard) ===

def insert_journal(date_iso, repas, nom, quantite_g, nutrients: dict):
    conn = init_db()
    conn.execute(
        "INSERT INTO journal (date,repas,nom,quantite_g,nutrients_json) VALUES (?,?,?,?,?)",
        (date_iso, repas, nom, float(quantite_g), json.dumps(nutrients, ensure_ascii=False))
    )
    conn.commit()

def delete_journal_row(row_id: int):
    conn = init_db()
    conn.execute("DELETE FROM journal WHERE id=?", (int(row_id),))
    conn.commit()

def fetch_journal_by_date(date_iso) -> pd.DataFrame:
    conn = init_db()
    cur = conn.execute(
        "SELECT id,date,repas,nom,quantite_g,nutrients_json FROM journal WHERE date=? ORDER BY id ASC;",
        (date_iso,)
    )
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["id","date","repas","nom","quantite_g"])
    df = pd.DataFrame(rows, columns=["id","date","repas","nom","quantite_g","nutrients_json"])
    expanded = []
    for js in df["nutrients_json"]:
        try:
            expanded.append(json.loads(js))
        except Exception:
            expanded.append({})
    nutr_df = pd.DataFrame(expanded).fillna(0.0)
    return pd.concat([df.drop(columns=["nutrients_json"]), nutr_df], axis=1)

def fetch_last_date_with_rows() -> str | None:
    conn = init_db()
    cur = conn.execute("SELECT date, COUNT(*) c FROM journal GROUP BY date ORDER BY date DESC;")
    r = cur.fetchone()
    return r[0] if r else None
