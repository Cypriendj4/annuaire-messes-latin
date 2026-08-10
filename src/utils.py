"""
Utilitaires partagés : logging, fuzzy matching, géocodage, helpers.
"""
import re
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from rapidfuzz import fuzz, process

from config import COMMUNE_LABELS, FSSPX_COMMUNITIES, DEPT_COORDS

# ── Logging ────────────────────────────────────────────────────────────
def setup_logging(name: str = "annuaire", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


# ── Normalisation ──────────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """Normalise pour comparaison : minuscules, pas d'accents, espaces simples."""
    if not text:
        return ""
    text = text.lower().strip()
    # Remplace accents
    replacements = {
        'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a', 'ã': 'a', 'å': 'a',
        'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
        'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
        'ò': 'o', 'ó': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o',
        'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
        'ÿ': 'y', 'ñ': 'n', 'ç': 'c', 'œ': 'oe', 'æ': 'ae',
        'ß': 'ss',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Nettoie ponctuation multiple, espaces
    text = re.sub(r'[^\w\s-]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def normalize_ville(text: str) -> str:
    """Normalise nom de ville pour déduplication."""
    text = normalize_text(text)
    # Supprime préfixes/suffixes courants
    text = re.sub(r'^(ville de|commune de|ville-|commune-)\s*', '', text)
    text = re.sub(r'\s*(centre|centre-ville|ville)$', '', text)
    return text


def normalize_lieu(text: str) -> str:
    """Normalise nom de lieu (église/chapelle) pour déduplication."""
    text = normalize_text(text)
    # Supprime mots génériques
    stopwords = {'eglise', 'eglise-paroissiale', 'eglise-paroisse', 'chapelle', 'basilique',
                 'cathedrale', 'abbaye', 'monastere', 'prieure', 'sanctuaire', 'eglise-abbatiale',
                 'eglise-colllegiale', 'eglise-collgeiale', 'eglise-eglise'}
    words = [w for w in text.split() if w not in stopwords]
    return ' '.join(words)


def extract_dept_code(dept_str: str) -> str:
    """Extrait le code département de '31 – Haute-Garonne' → '31'."""
    match = re.match(r'^(\d{1,3}[AB]?)', dept_str.strip())
    return match.group(1) if match else ""


# ── Fuzzy matching ─────────────────────────────────────────────────────
def find_match(query: str, choices: List[str], threshold: int = 85) -> Optional[Tuple[str, int]]:
    """Retourne (meilleur_match, score) si score >= threshold, sinon None."""
    if not choices:
        return None
    result = process.extractOne(query, choices, scorer=fuzz.WRatio)
    if result and result[1] >= threshold:
        return result[0], result[1]
    return None


def lieux_equivalent(l1: Dict, l2: Dict, threshold: int = 85) -> bool:
    """Détermine si deux lieux sont le même (même église, même ville, même rite/communauté)."""
    if l1.get('rite') != l2.get('rite'):
        return False
    if l1.get('communaute') != l2.get('communaute'):
        return False
    v1, v2 = normalize_ville(l1.get('ville', '')), normalize_ville(l2.get('ville', ''))
    if fuzz.WRatio(v1, v2) < threshold:
        return False
    lie1, lie2 = normalize_lieu(l1.get('lieu', '')), normalize_lieu(l2.get('lieu', ''))
    if fuzz.WRatio(lie1, lie2) < threshold:
        return False
    return True


# ── Géocodage approximatif (centroïde département) ────────────────────
def get_dept_coords(dept_code: str) -> Optional[Tuple[float, float]]:
    """Retourne (lat, lon) du centroïde département, ou None."""
    return DEPT_COORDS.get(dept_code)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en km entre deux points GPS."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


# ── Helpers diverses ───────────────────────────────────────────────────
def slugify(text: str) -> str:
    """Pour IDs HTML, ancres, etc."""
    text = normalize_text(text)
    text = re.sub(r'[^\w-]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def compute_hash(*fields: str) -> str:
    """Hash stable pour détecter changements."""
    content = '|'.join(str(f) for f in fields)
    return hashlib.md5(content.encode()).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def parse_date_fr(text: str) -> Optional[str]:
    """Essaie de parser une date française '07/08/2026' → '2026-08-07'."""
    match = re.search(r'(\d{1,2})[/\.](\d{1,2})[/\.](\d{4})', text)
    if match:
        d, m, y = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return None


# ── Labels UI ──────────────────────────────────────────────────────────
def get_commune_label(code: str) -> str:
    return COMMUNE_LABELS.get(code, code)


def is_fsspX(communaute: str) -> bool:
    return communaute in FSSPX_COMMUNITIES


# ── Cache helpers ──────────────────────────────────────────────────────
def cache_key(url: str, params: dict = None) -> str:
    """Clé de cache stable pour requests-cache."""
    base = url
    if params:
        base += '?' + '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.md5(base.encode()).hexdigest()


# ── Validation ─────────────────────────────────────────────────────────
def validate_lieu(data: Dict) -> Tuple[bool, List[str]]:
    """Valide un dict lieu avant insertion. Retourne (ok, erreurs)."""
    errors = []
    required = ['ville', 'dept', 'diocese', 'lieu', 'rite', 'langue', 'communaute']
    for field in required:
        if not data.get(field):
            errors.append(f"Champ requis manquant: {field}")
    if data.get('rite') not in ('tridentin', 'paulvi'):
        errors.append(f"Rite invalide: {data.get('rite')}")
    if data.get('langue') not in ('latin', 'francais'):
        errors.append(f"Langue invalide: {data.get('langue')}")
    return len(errors) == 0, errors