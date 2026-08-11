#!/usr/bin/env python3
"""
Géocode les lieux sans coordonnées GPS (via Nominatim / OpenStreetMap).
Respecte la limite de 1 requête/seconde. Ajoute coord_lat/coord_lon à la base.
"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DB_PATH
from utils import setup_logging
import requests

logger = setup_logging("geocode")

HEADERS = {
    "User-Agent": "AnnuaireMesses/1.0 (annuaire des messes en France - usage ponctuel)",
    "Accept": "application/json",
}
BASE = "https://nominatim.openstreetmap.org/search"


def geocode(query: str) -> tuple | None:
    """Retourne (lat, lon) ou None."""
    try:
        r = requests.get(BASE, params={"q": query, "format": "json", "limit": 1, "countrycodes": "fr"}, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        logger.warning(f"Erreur géocodage '{query[:50]}': {e}")
    return None


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Lieux actifs sans GPS, avec une adresse ou une ville exploitable
    cur.execute("""
        SELECT id, ville, adresse, dept_code, source_principale
        FROM lieux
        WHERE actif = 1 AND (coord_lat IS NULL OR coord_lon IS NULL)
          AND (adresse != '' OR ville != '')
        ORDER BY source_principale
    """)
    rows = cur.fetchall()
    logger.info(f"{len(rows)} lieux à géocoder")

    ok = 0
    fail = 0
    for row in rows:
        # Query : adresse + ville + département (ou ville seule)
        parts = [p for p in (row["adresse"], row["ville"], row["dept_code"]) if p]
        query = ", ".join(parts)
        if not query.strip():
            fail += 1
            continue
        res = geocode(query)
        if res:
            cur.execute("UPDATE lieux SET coord_lat=?, coord_lon=? WHERE id=?",
                        (res[0], res[1], row["id"]))
            ok += 1
        else:
            fail += 1
        conn.commit()
        time.sleep(1.1)  # politesse Nominatim : 1 req/s

    logger.info(f"Géocodés: {ok} | Échecs: {fail}")
    print(f"GEOCODE_OK ok={ok} fail={fail}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
