#!/usr/bin/env python3
"""Crawl complet de la grille nationale CEF puis génération du site.
Lancé en arrière-plan (long)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import AnnuaireCEFParser
from config import GEO_GRID
from update_manager import apply_updates
from utils import setup_logging
import sqlite3

logger = setup_logging("crawl_complet")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "messes.db"

def main():
    start = time.time()
    logger.info(f"=== Crawl national complet ({len(GEO_GRID)} points) ===")

    p = AnnuaireCEFParser()
    candidates = p.run()
    logger.info(f"Total candidats: {len(candidates)}")

    conn = sqlite3.connect(DB_PATH)
    try:
        report = {}
        n, m, d = apply_updates(conn, candidates, report)
        logger.info(f"Résultat: {n} nouveaux, {m} modifiés, {d} désactivés")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM lieux WHERE actif=1")
        total = cur.fetchone()[0]
        logger.info(f"Total lieux actifs en base: {total}")
    finally:
        conn.close()

    logger.info(f"Durée totale: {(time.time()-start)/60:.1f} min")
    print(f"CRAWL_OK total={total} nouveaux={n} duree_min={(time.time()-start)/60:.1f}")

if __name__ == "__main__":
    main()
