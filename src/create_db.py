"""
Crée la base SQLite et importe les données initiales du fichier HTML statique.
"""
import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime

from config import DB_PATH, COMMUNE_LABELS, FSSPX_COMMUNITIES
from utils import setup_logging, normalize_ville, normalize_lieu, extract_dept_code, slugify, compute_hash, now_iso

logger = setup_logging("create_db")

# ── Schéma SQLite ──────────────────────────────────────────────────────
SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lieux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ville TEXT NOT NULL,
    dept_code TEXT NOT NULL,
    dept_nom TEXT NOT NULL,
    diocese TEXT,
    lieu TEXT NOT NULL,
    adresse TEXT,
    rite TEXT CHECK (rite IN ('tridentin','paulvi') OR rite IS NULL),
    langue TEXT CHECK (langue IN ('latin','francais') OR langue IS NULL),
    communaute TEXT,
    celebrant TEXT,
    horaires TEXT,
    contact TEXT,
    url_detail TEXT,                  -- lien messes.info (annuaire national)
    source_principale TEXT NOT NULL,
    source_secondaire TEXT,           -- JSON array
    derniere_maj DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    coord_lat REAL,
    coord_lon REAL,
    actif BOOLEAN NOT NULL DEFAULT 1,
    confiance INTEGER NOT NULL DEFAULT 3,
    hash_contenu TEXT,                -- pour détecter changements
    UNIQUE(ville, lieu, communaute, rite)
);

CREATE INDEX IF NOT EXISTS idx_rite ON lieux(rite);
CREATE INDEX IF NOT EXISTS idx_diocese ON lieux(diocese);
CREATE INDEX IF NOT EXISTS idx_communaute ON lieux(communaute);
CREATE INDEX IF NOT EXISTS idx_dept ON lieux(dept_code);
CREATE INDEX IF NOT EXISTS idx_actif ON lieux(actif);
CREATE INDEX IF NOT EXISTS idx_confiance ON lieux(confiance);

-- Anti-doublon annuaire national : URL messes.info unique par église
CREATE UNIQUE INDEX IF NOT EXISTS idx_url_detail
    ON lieux(url_detail) WHERE url_detail IS NOT NULL;

CREATE TABLE IF NOT EXISTS communes_labels (
    code TEXT PRIMARY KEY,
    label_complet TEXT NOT NULL,
    est_fsspX BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sources (
    code TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    url_base TEXT NOT NULL,
    frequence_maj TEXT,
    fiabilite INTEGER DEFAULT 3,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS maj_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    nouveaux INTEGER DEFAULT 0,
    modifies INTEGER DEFAULT 0,
    desactives INTEGER DEFAULT 0,
    erreurs TEXT,
    duree_ms INTEGER
);
"""

# ── Données initiales (extraction du HTML fourni) ──────────────────────
# Note: Ces données sont une version condensée pour l'exemple.
# En production, le script lirait le fichier HTML et extrairait le tableau DATA.
DATA_INITIAL = [
    # --- Exemples (les 119 entrées réelles seraient ici) ---
    {
        "ville": "Toulouse", "dept": "31 – Haute-Garonne", "diocese": "Toulouse",
        "lieu": "Chapelle Saint-Jean-Baptiste", "adresse": "7 rue Antonin-Mercié",
        "rite": "tridentin", "langue": "latin", "communaute": "ICRSP",
        "celebrant": "Chanoines Colomb et Jantaud",
        "horaires": "Dim. 8h15, 10h00 et 18h00", "contact": "07 65 70 98 56",
    },
    {
        "ville": "Paris", "dept": "75 – Paris", "diocese": "Paris",
        "lieu": "Saint-Eugène–Sainte-Cécile — messe en forme extraordinaire",
        "adresse": "4 bis rue Sainte-Cécile", "rite": "tridentin", "langue": "latin",
        "communaute": "Diocèse", "celebrant": "Prêtres de la paroisse",
        "horaires": "Plusieurs messes dominicales — voir site", "contact": "01 48 24 70 25",
    },
    {
        "ville": "Paris", "dept": "75 – Paris", "diocese": "Paris",
        "lieu": "Saint-Eugène–Sainte-Cécile — messe en forme ordinaire",
        "adresse": "4 bis rue Sainte-Cécile", "rite": "paulvi", "langue": "francais",
        "communaute": "Diocèse", "celebrant": "Prêtres de la paroisse",
        "horaires": "Dim. 9h30", "contact": "01 48 24 70 25",
    },
    {
        "ville": "Chambéry", "dept": "73 – Savoie", "diocese": "Chambéry, Maurienne, Tarentaise",
        "lieu": "Église Notre-Dame (paroisse Saint-François-de-Sales – Cathédrale)",
        "adresse": "Rue Saint-Antoine", "rite": "paulvi", "langue": "latin",
        "communaute": "Diocèse", "celebrant": "Prêtres de la paroisse cathédrale",
        "horaires": "Dim. 9h30 (messe dominicale en latin) · sam. 17h30", "contact": "04 79 70 58 15",
    },
    # ... (toutes les 119 entrées)
]

def parse_dept(dept_str: str) -> tuple[str, str]:
    """'31 – Haute-Garonne' → ('31', 'Haute-Garonne')"""
    match = re.match(r'^(\d{1,3}[AB]?)\s*[–-]\s*(.+)$', dept_str.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return dept_str, ""


def init_communes_labels(conn: sqlite3.Connection):
    """Remplit la table communes_labels."""
    cur = conn.cursor()
    for code, label in COMMUNE_LABELS.items():
        cur.execute(
            "INSERT OR REPLACE INTO communes_labels (code, label_complet, est_fsspX) VALUES (?, ?, ?)",
            (code, label, 1 if code in FSSPX_COMMUNITIES else 0)
        )
    conn.commit()


def init_sources(conn: sqlite3.Connection):
    """Remplit la table sources."""
    from config import SOURCES
    cur = conn.cursor()
    for code, info in SOURCES.items():
        cur.execute(
            "INSERT OR REPLACE INTO sources (code, nom, url_base, frequence_maj, fiabilite, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (code, info["name"], info["base_url"], info["frequency"], info["reliability"], info.get("notes", ""))
        )
    conn.commit()


def import_initial_data(conn: sqlite3.Connection, data: list[dict]):
    """Importe les données initiales dans la table lieux."""
    cur = conn.cursor()
    imported = 0
    for entry in data:
        dept_code, dept_nom = parse_dept(entry["dept"])
        hash_contenu = compute_hash(
            entry["ville"], entry["lieu"], entry["rite"], entry["communaute"],
            entry.get("horaires", ""), entry.get("adresse", ""), entry.get("celebrant", "")
        )
        try:
            cur.execute("""
                INSERT INTO lieux (
                    ville, dept_code, dept_nom, diocese, lieu, adresse,
                    rite, langue, communaute, celebrant, horaires, contact,
                    source_principale, source_secondaire, derniere_maj,
                    confiance, hash_contenu
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry["ville"], dept_code, dept_nom, entry["diocese"], entry["lieu"],
                entry.get("adresse") or None, entry["rite"], entry["langue"],
                entry["communaute"], entry.get("celebrant") or None,
                entry.get("horaires") or None, entry.get("contact") or None,
                "initial_manual", json.dumps([]), now_iso(), 3, hash_contenu
            ))
            imported += 1
        except sqlite3.IntegrityError:
            logger.debug(f"Doublon ignoré: {entry['ville']} - {entry['lieu']} ({entry['communaute']})")
    conn.commit()
    return imported


def load_initial_json() -> list[dict]:
    """Charge les données initiales depuis data/initial_data.json si présent,
    sinon retombe sur l'échantillon DATA_INITIAL."""
    json_path = DB_PATH.parent / "initial_data.json"
    if json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    return DATA_INITIAL


def main():
    logger.info("=== Création base SQLite ===")
    DATA_DIR = DB_PATH.parent
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    # Crée les tables
    conn.executescript(SCHEMA)
    logger.info("Tables créées")

    # Remplit tables de référence
    init_communes_labels(conn)
    init_sources(conn)
    logger.info("Tables de référence remplies")

    # Importe données initiales (JSON extrait du HTML, ou échantillon fallback)
    initial_data = load_initial_json()
    imported = import_initial_data(conn, initial_data)
    logger.info(f"Importé: {imported} lieux initiaux")

    # Stats
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM lieux")
    total = cur.fetchone()[0]
    cur.execute("SELECT rite, COUNT(*) FROM lieux GROUP BY rite")
    for rite, cnt in cur.fetchall():
        logger.info(f"  {rite}: {cnt}")

    conn.close()
    logger.info(f"Base créée: {DB_PATH}")


if __name__ == "__main__":
    main()