"""
Gestionnaire de mises à jour : exécute les scrapers, compare avec la base,
génère un rapport, applique les changements et sauvegarde avant modification.

Règles métier :
- Un lieu est DÉSACTIVÉ (actif=0) s'il est absent d'au moins 2 sources sur 4.
- Confiance :
    5 = présent dans 3+ sources
    4 = présent dans 2 sources
    3 = source unique fiable (amdg, portelatine)
    2 = source unique moins fiable (trouverunemesse, messes_info seul)
    1 = douteux (conflit horaires / données incomplètes)
- Priorité de mise à jour des champs : amdg > portelatine > messes_info > trouverunemesse
"""
import json
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DB_PATH, BACKUP_DIR, SOURCES
from scraper import run_all_parsers
from utils import (
    setup_logging, lieux_equivalent, normalize_ville, normalize_lieu,
    extract_dept_code, compute_hash, now_iso, get_dept_coords,
)

logger = setup_logging("update_manager")

# Ordre de priorité des sources pour les champs (le premier qui a une valeur gagne)
SOURCE_PRIORITY = ["amdg", "portelatine", "annuaire_cef", "messes_info", "trouverunemesse"]

FIELD_PRIORITY = ["horaires", "adresse", "celebrant", "contact", "diocese", "lieu"]


def backup_db() -> Optional[Path]:
    """Copie la base avant mise à jour. Retourne le chemin du backup."""
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"messes_{ts}.db"
    shutil.copy2(DB_PATH, dest)
    # Ne garde que les 14 derniers backups
    backups = sorted(BACKUP_DIR.glob("messes_*.db"))
    for old in backups[:-14]:
        old.unlink()
    logger.info(f"Backup créé: {dest}")
    return dest


def compute_confidence(sources_present: List[str]) -> int:
    """Calcule le score de confiance selon le nombre et la qualité des sources."""
    n = len(sources_present)
    if n >= 3:
        return 5
    if n == 2:
        return 4
    # Une seule source
    if sources_present:
        src = sources_present[0]
        if src in ("amdg", "portelatine"):
            return 3
        return 2
    return 1


def merge_sources(existing: Optional[Dict], new_candidates: List[Dict]) -> Dict:
    """Fusionne les données d'un lieu depuis plusieurs sources.

    existing : dict représentant le lieu en base (ou None)
    new_candidates : listes de dicts normalisés pour ce lieu (par source)
    Retourne le dict fusionné avec source_principale et source_secondaire.
    """
    merged = dict(existing or {})
    sources_present = [c["source_principale"] for c in new_candidates]
    # Détecte les changements : hash différent
    if existing:
        sources_present = list(dict.fromkeys(sources_present + [existing.get("source_principale")]))

    # Champs de base : on prend la première valeur non vide selon priorité
    source_by_priority = {s["source_principale"]: s for s in new_candidates}

    # Source principale = la source la plus fiable qui a fourni ce lieu
    for src in SOURCE_PRIORITY:
        if src in source_by_priority:
            merged["source_principale"] = src
            break

    # Rite/langue/communaute : valeur de la source la plus fiable (première dans la liste)
    for field in ("ville", "dept", "dept_code", "dept_nom", "diocese", "lieu",
                  "rite", "langue", "communaute", "celebrant", "horaires",
                  "contact", "adresse", "url_detail"):
        for src in SOURCE_PRIORITY:
            if src in source_by_priority and source_by_priority[src].get(field) is not None:
                merged[field] = source_by_priority[src][field]
                break
        # Sinon garde la valeur existante

    # Coordonnées GPS : préfère non-null, mais ignore les coordonnées
    # manifestement fausses que messes.info renvoie en fallback quand un
    # lieu n'a pas de GPS (le point de requête de la grille, souvent le
    # centre de la France 46.657,2.485, ou des valeurs héritées d'une
    # autre zone). Garde la valeur existante si elle est meilleure.
    def _coord_is_bogus(c) -> bool:
        if not c.get("coord_lat") or not c.get("coord_lon"):
            return True
        lat, lon = float(c["coord_lat"]), float(c["coord_lon"])
        # Point fallback centre-France (messes.info renvoie ce point
        # quand il n'a pas les coordonnées réelles du lieu).
        if abs(lat - 46.657) < 0.01 and abs(lon - 2.485) < 0.01:
            return True
        # Hors des bornes France métropolitaine + DOM (outre-mer inclus)
        if not (-21.5 <= lat <= 51.5 and -62.0 <= lon <= 56.0):
            return True
        return False

    best_coord = None
    for c in new_candidates:
        if _coord_is_bogus(c):
            continue
        best_coord = c
        break
    if best_coord is not None:
        merged["coord_lat"] = best_coord["coord_lat"]
        merged["coord_lon"] = best_coord["coord_lon"]

    # Sources
    merged["source_secondaire"] = json.dumps(
        [s for s in sources_present if s != merged.get("source_principale")]
    )
    merged["confiance"] = compute_confidence(sources_present)
    merged["actif"] = 1
    merged["derniere_maj"] = now_iso()
    merged["hash_contenu"] = compute_hash(
        merged.get("ville", ""), merged.get("lieu", ""), merged.get("rite", ""),
        merged.get("communaute", ""), merged.get("horaires", ""),
        merged.get("adresse", ""), merged.get("celebrant", ""),
    )
    return merged


def load_existing(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """Charge les lieux existants en base. Clé = identifiant canonique."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ville, dept_code, dept_nom, diocese, lieu, adresse, rite,
               langue, communaute, celebrant, horaires, contact, url_detail,
               source_principale, source_secondaire, derniere_maj,
               coord_lat, coord_lon, actif, confiance, hash_contenu
        FROM lieux
    """)
    existing = {}
    for row in cur.fetchall():
        d = {
            "id": row[0], "ville": row[1], "dept_code": row[2], "dept_nom": row[3],
            "diocese": row[4], "lieu": row[5], "adresse": row[6], "rite": row[7],
            "langue": row[8], "communaute": row[9], "celebrant": row[10],
            "horaires": row[11], "contact": row[12], "url_detail": row[13],
            "source_principale": row[14], "source_secondaire": row[15],
            "derniere_maj": row[16], "coord_lat": row[17], "coord_lon": row[18],
            "actif": row[19], "confiance": row[20], "hash_contenu": row[21],
        }
        key = canonical_key(d)
        existing[key] = d
    return existing


def canonical_key(d: Dict) -> str:
    """Clé canonique : ville normalisée + lieu normalisé + communaute + rite.
    (rite/communaute peuvent être NULL pour les églises générales → "")."""
    return "|".join([
        normalize_ville(d.get("ville") or ""),
        normalize_lieu(d.get("lieu") or ""),
        d.get("communaute") or "",
        d.get("rite") or "",
    ])


def group_candidates(candidates: List[Dict]) -> Dict[str, List[Dict]]:
    """Groupe les candidats extraits par clé canonique."""
    groups = {}
    for c in candidates:
        key = canonical_key(c)
        groups.setdefault(key, []).append(c)
    return groups


def apply_updates(conn: sqlite3.Connection, candidates: List[Dict],
                  report: Dict, sources_actives: Optional[List[str]] = None) -> Tuple[int, int, int]:
    """Applique les changements. Retourne (nouveaux, modifiés, désactivés).

    sources_actives : sources exécutées dans CE run. La désactivation ne
    concerne que les lieux dont la source principale a tourné — un lieu
    portelatine n'est jamais jugé "absent" lors d'un run amdg seul."""
    cur = conn.cursor()
    existing = load_existing(conn)
    groups = group_candidates(candidates)
    if sources_actives is None:
        sources_actives = list(SOURCES.keys())

    # 1. Nouveaux + modifications
    nouveaux = 0
    modifies = 0
    for key, cand_list in groups.items():
        # Fusionne les sources
        ex = existing.get(key)
        merged = merge_sources(ex, cand_list)
        # Completer dept si manquant
        if not merged.get("dept_code") and merged.get("dept"):
            merged["dept_code"] = extract_dept_code(merged["dept"])
        # Compléter coordonnées par centroïde département si manquant
        if not merged.get("coord_lat") and merged.get("dept_code"):
            coords = get_dept_coords(merged["dept_code"])
            if coords:
                merged["coord_lat"] = coords[0]
                merged["coord_lon"] = coords[1]

        if ex is None:
            # Nouveau lieu
            cur.execute("""
                INSERT INTO lieux (
                    ville, dept_code, dept_nom, diocese, lieu, adresse, rite,
                    langue, communaute, celebrant, horaires, contact, url_detail,
                    source_principale, source_secondaire, derniere_maj,
                    coord_lat, coord_lon, actif, confiance, hash_contenu
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                merged.get("ville", ""), merged.get("dept_code", ""),
                merged.get("dept_nom", ""), merged.get("diocese"),
                merged.get("lieu", ""), merged.get("adresse"),
                merged.get("rite"), merged.get("langue"),
                merged.get("communaute"), merged.get("celebrant"),
                merged.get("horaires"), merged.get("contact"), merged.get("url_detail"),
                merged.get("source_principale", ""),
                merged.get("source_secondaire", "[]"),
                merged.get("derniere_maj", now_iso()),
                merged.get("coord_lat"), merged.get("coord_lon"),
                merged.get("actif", 1), merged.get("confiance", 3),
                merged.get("hash_contenu", ""),
            ))
            nouveaux += 1
        else:
            # Existant : détecte changement via hash
            if ex.get("hash_contenu") != merged.get("hash_contenu"):
                cur.execute("""
                    UPDATE lieux SET
                        ville=?, dept_code=?, dept_nom=?, diocese=?, lieu=?,
                        adresse=?, rite=?, langue=?, communaute=?, celebrant=?,
                        horaires=?, contact=?, url_detail=?, source_principale=?,
                        source_secondaire=?, derniere_maj=?, coord_lat=?,
                        coord_lon=?, actif=?, confiance=?, hash_contenu=?
                    WHERE id=?
                """, (
                    merged.get("ville", ""), merged.get("dept_code", ""),
                    merged.get("dept_nom", ""), merged.get("diocese"),
                    merged.get("lieu", ""), merged.get("adresse"),
                    merged.get("rite"), merged.get("langue"),
                    merged.get("communaute"), merged.get("celebrant"),
                    merged.get("horaires"), merged.get("contact"), merged.get("url_detail"),
                    merged.get("source_principale", ""),
                    merged.get("source_secondaire", "[]"),
                    merged.get("derniere_maj", now_iso()),
                    merged.get("coord_lat"), merged.get("coord_lon"),
                    merged.get("actif", 1), merged.get("confiance", 3),
                    merged.get("hash_contenu", ""), ex["id"],
                ))
                modifies += 1
    conn.commit()

    # 2. Désactivation : lieu absent d'au moins 2 sources sur 4
    # Règles de sécurité :
    #   - lieux d'origine manuelle (initial_manual) : JAMAIS désactivés
    #   - lieux de sources "jamais_desactiver" (annuaire_cef) : JAMAIS désactivés
    #     (ce sont des milliers d'églises générales, pas jugées par les 4 sources spécialisées)
    desactives = 0
    active_keys = set(groups.keys())
    protected_sources = {code for code, info in SOURCES.items() if info.get("jamais_desactiver")}
    for key, ex in existing.items():
        if ex.get("actif") == 0:
            continue  # déjà inactif
        if ex.get("source_principale") in ("initial_manual",) or ex.get("source_principale") in protected_sources:
            continue  # protégé : vérifié manuellement ou source non désactivable
        if ex.get("source_principale") not in sources_actives:
            continue  # sa source n'a pas tourné ce run → on ne juge pas
        if key not in active_keys:
            # Absent des scrapers → potentiellement disparu
            # Règle : on désactive si absent de 2+ sources.
            # On compte le nombre de sources qui NE listent PAS ce lieu.
            sources_total = set(SOURCES.keys())
            sources_present = set(json.loads(ex.get("source_secondaire") or "[]"))
            sources_present.add(ex.get("source_principale"))
            missing = sources_total - sources_present
            if len(missing) >= 2:
                cur.execute("UPDATE lieux SET actif=0, derniere_maj=? WHERE id=?",
                            (now_iso(), ex["id"]))
                desactives += 1
            else:
                # Présent dans une source fiable → on garde actif mais on note
                logger.debug(f"Lieu {key}: toujours actif (source unique fiable)")
    conn.commit()

    report["nouveaux"] = nouveaux
    report["modifies"] = modifies
    report["desactives"] = desactives
    logger.info(f"Résumé: {nouveaux} nouveaux, {modifies} modifiés, {desactives} désactivés")
    return nouveaux, modifies, desactives


def generate_report(report: Dict) -> str:
    """Génère un rapport texte lisible pour notification Telegram."""
    lines = [
        f"🕐 Mise à jour {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"🆕 Nouveaux : {report.get('nouveaux', 0)}",
        f"✏️ Modifiés : {report.get('modifies', 0)}",
        f"🚫 Désactivés : {report.get('desactives', 0)}",
        f"⏱️ Durée : {report.get('duree_ms', 0)/1000:.1f}s",
    ]
    # Ajoute les lieux notables
    if report.get("nouveaux_lieux"):
        lines.append("\n📍 Nouveaux lieux :")
        for lieu in report["nouveaux_lieux"][:10]:
            lines.append(f"  • {lieu}")
    if report.get("modifies_lieux"):
        lines.append("\n✏️ Lieux modifiés :")
        for lieu in report["modifies_lieux"][:10]:
            lines.append(f"  • {lieu}")
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """Envoie un message Telegram (si token configuré)."""
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Pas de token Telegram configuré, notification ignorée")
        return False
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=15)
        if resp.status_code == 200:
            logger.info("Notification Telegram envoyée")
            return True
        logger.warning(f"Telegram erreur: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Telegram exception: {e}")
    return False


def default_sources() -> List[str]:
    """Sources quotidiennes qui ajoutent des lieux (amdg + portelatine).
    annuaire_cef (grille nationale ~45k églises) est déclenchée par un
    workflow hebdomadaire séparé (update-annuaire-cef.yml) — trop lourd
    pour un run quotidien. Les sources de vérification (trouverunemesse,
    messes_info) ne sont utilisées que si demandées explicitement."""
    return [code for code, info in SOURCES.items()
            if info.get("ajout_lieux", False) and code != "annuaire_cef"]


def weekly_sources() -> List[str]:
    """Sources lourdes hebdomadaires (grille nationale CEF)."""
    return ["annuaire_cef"]


def main(sources: Optional[List[str]] = None):
    start = time.time()
    report = {"nouveaux": 0, "modifies": 0, "desactives": 0, "erreurs": [], "duree_ms": 0}

    if sources is None:
        sources = default_sources()

    logger.info(f"=== Mise à jour annuaire (sources: {', '.join(sources)}) ===")

    # Backup avant modification
    backup_db()

    # Exécute les parseurs
    candidates = []
    results = run_all_parsers(sources)
    for src, items in results.items():
        candidates.extend(items)

    logger.info(f"Total candidats: {len(candidates)}")

    # Applique les changements
    conn = sqlite3.connect(DB_PATH)
    try:
        nouveaux, modifies, desactives = apply_updates(conn, candidates, report, sources_actives=sources)
        report["nouveaux"] = nouveaux
        report["modifies"] = modifies
        report["desactives"] = desactives

        # Log en base
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO maj_log (date, nouveaux, modifies, desactives, erreurs, duree_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            now_iso(), nouveaux, modifies, desactives,
            json.dumps(report["erreurs"]), int((time.time() - start) * 1000)
        ))
        conn.commit()
    finally:
        conn.close()

    report["duree_ms"] = int((time.time() - start) * 1000)

    # Rapport + notification
    message = generate_report(report)
    logger.info("\n" + message)
    send_telegram(message)

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mise à jour de l'annuaire des messes")
    parser.add_argument("--sources", type=str, default=None,
                        help="Sources à exécuter, séparées par des virgules. "
                             "Défaut : sources quotidiennes (amdg,portelatine). "
                             "Hebdo : annuaire_cef.")
    parser.add_argument("--weekly", action="store_true",
                        help="Exécute les sources hebdomadaires (annuaire_cef)")
    args = parser.parse_args()
    if args.weekly:
        sources = weekly_sources()
    elif args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    else:
        sources = None  # default_sources()
    main(sources)