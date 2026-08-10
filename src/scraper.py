"""
Scrapers modulaires pour les 4 sources de l'annuaire des messes en latin.

Chaque parseur hérite de la classe de base `Scraper` et implémente :
    fetch()     → récupère la page
    parse()     → extrait les lieux bruts
    normalize() → transforme en dict conforme au schéma
    validate()  → vérifie les champs requis

Scraping "poli" : user-agent identifiable, délai entre requêtes, cache 24h,
retry avec backoff, respect des limites de requêtes.
"""
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

from config import (
    REQUEST_TIMEOUT, REQUEST_DELAY, MAX_RETRIES, USER_AGENT,
    CACHE_EXPIRE_DAYS, VILLES_PRINCIPALES, GEO_GRID, GRID_MAX_PAGES,
)
from utils import setup_logging, extract_dept_code, normalize_text, slugify, compute_hash

logger = setup_logging("scraper")

# Cache simple en mémoire (persistant sur disque via requests-cache si dispo)
try:
    import requests_cache
    CACHE_PATH = str(Path(__file__).resolve().parent.parent / "data" / "http_cache")
    requests_cache.install_cache(
        CACHE_PATH,
        backend="sqlite",
        expire_after=CACHE_EXPIRE_DAYS * 86400,
    )
    _CACHE_ENABLED = True
except ImportError:
    _CACHE_ENABLED = False


def fetch_url(url: str, encoding: Optional[str] = None, timeout: int = REQUEST_TIMEOUT,
              retries: int = MAX_RETRIES, delay: float = REQUEST_DELAY) -> Optional[str]:
    """Fetch avec retry + backoff. Retourne le HTML texte ou None."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if resp.status_code == 200:
                resp.encoding = encoding or resp.encoding or "utf-8"
                if attempt > 1:
                    time.sleep(delay * 2)
                return resp.text
            else:
                logger.warning(f"[{resp.status_code}] {url}")
                if resp.status_code in (403, 429):
                    time.sleep(delay * attempt * 3)
                elif resp.status_code in (404, 410):
                    return None
        except requests.RequestException as e:
            logger.warning(f"Erreur {url}: {e}")
        time.sleep(delay * attempt)
    logger.error(f"Échec après {retries} tentatives: {url}")
    return None


class Scraper(ABC):
    """Classe de base abstraite."""

    source_code = "generic"

    @abstractmethod
    def fetch(self) -> None:
        """Récupère les données sources."""

    @abstractmethod
    def parse(self) -> List[Dict]:
        """Extrait les lieux bruts depuis le contenu fetched."""

    @abstractmethod
    def normalize(self, raw: Dict) -> Optional[Dict]:
        """Transforme un dict brut en dict conforme au schéma. Retourne None si invalide."""

    def validate(self, data: Dict) -> bool:
        """Valide les champs obligatoires : ville + lieu.
        rite/langue/communaute/dept/diocese peuvent être NULL ou vides
        (églises générales de l'annuaire national, sources partielles)."""
        return bool(data.get("ville")) and bool(data.get("lieu"))

    def run(self) -> List[Dict]:
        """Pipeline complet : fetch → parse → normalize → validate."""
        self.fetch()
        results = []
        self._pending = []
        for raw in self.parse():
            norm = self.normalize(raw)
            if norm and self.validate(norm):
                norm["source_principale"] = self.source_code
                norm["hash_contenu"] = compute_hash(
                    norm.get("ville", ""), norm.get("lieu", ""), norm.get("rite", ""),
                    norm.get("communaute", ""), norm.get("horaires", ""),
                    norm.get("adresse", ""), norm.get("celebrant", ""),
                )
                results.append(norm)
            # Entrées supplémentaires éventuelles (ex: AMDG par département)
            while getattr(self, "_pending", None):
                extra_raw = self._pending.pop(0)
                extra = self.normalize_extra(extra_raw, raw)
                if extra and self.validate(extra):
                    extra["source_principale"] = self.source_code
                    extra["hash_contenu"] = compute_hash(
                        extra.get("ville", ""), extra.get("lieu", ""), extra.get("rite", ""),
                        extra.get("communaute", ""), extra.get("horaires", ""),
                        extra.get("adresse", ""), extra.get("celebrant", ""),
                    )
                    results.append(extra)
        logger.info(f"[{self.source_code}] {len(results)} lieux extraits")
        return results

    def normalize_extra(self, extra_raw: Dict, parent_raw: Dict) -> Optional[Dict]:
        """Normalise une entrée supplémentaire (par défaut : None = ignorée).
        À surcharger dans les classes filles qui produisent plusieurs entrées."""
        return None


# ─────────────────────────────────────────────────────────────────────
# AMDG — messes tridentin (forme extraordinaire), MAJ hebdomadaire
# ─────────────────────────────────────────────────────────────────────
class AMDGParser(Scraper):
    source_code = "amdg"

    def __init__(self):
        self.list_url = "https://www.amdg.asso.fr/lieux_messes_spv.htm"
        self.html = None
        self.soup = None

    def fetch(self) -> None:
        html = fetch_url(self.list_url, encoding="windows-1252")
        if html:
            self.html = html
            self.soup = BeautifulSoup(html, "lxml")

    def parse(self) -> List[Dict]:
        """Parse les tableaux Word par département (ancres #1..#95)."""
        results = []
        if not self.soup:
            return results

        # AMDG structure : par département, un titre puis liste de lieux.
        # Approche robuste : extraire le texte et segmenter par département.
        # Stratégie : chercher les ancres <a name="1">, <a name="2">, ...
        anchors = self.soup.find_all("a", attrs={"name": re.compile(r"^\d{1,3}$")})
        for anchor in anchors:
            dept_num = anchor.get("name")
            dept_name = ""
            # Le nom du département suit généralement l'ancre dans le même bloc
            parent_p = anchor.find_parent("p")
            if parent_p:
                full = parent_p.get_text(" ", strip=True)
                # Ex: "31 - Haute-Garonne" après le numéro
                m = re.search(r"(?:-\s*|:?\s*)(.+)$", full)
                if m and m.group(1).strip() and not m.group(1).strip().isdigit():
                    dept_name = m.group(1).strip()
                else:
                    dept_name = full
            # Collecte les paragraphes suivants jusqu'à la prochaine ancre
            content_parts = []
            node = anchor.find_parent("p")
            if node:
                sibling = node.find_next_sibling()
                guard = 0
                while sibling and guard < 30:
                    if sibling.find("a", attrs={"name": re.compile(r"^\d{1,3}$")}):
                        break
                    text = sibling.get_text(" ", strip=True)
                    if text and len(text) > 3:
                        content_parts.append(text)
                    sibling = sibling.find_next_sibling()
                    guard += 1
            results.append({
                "dept_num": dept_num,
                "dept_name": dept_name,
                "content": " | ".join(content_parts),
            })
        return results

    def normalize(self, raw: Dict) -> Optional[Dict]:
        """Transforme le contenu brut d'un département en lieux individuels."""
        dept_num = raw["dept_num"]
        dept_name = raw["dept_name"]
        content = raw.get("content", "")

        # Extrait le diocèse depuis le nom de département
        # ex: "Diocèse de Belley-Ars" → "Belley-Ars"
        diocese = ""
        if dept_name:
            diocese = re.sub(r'^(Dioc[èe]se|Dioc[èe]se de|dioc[èe]se)\s+(de\s+|d\'|d\')?', '', dept_name).strip()
            if not diocese or diocese.lower() == dept_name.lower():
                diocese = dept_name

        # Format AMDG typique : "1. VILLE - 01270 - Lieu ..." ou "1. VILLE (01) ..."
        # Segmentation par numérotation "N." au début
        segments = re.split(r'(?<=\d)\s*(?=\d+\.\s)', content)
        entries = []
        for seg in segments:
            seg = seg.strip()
            if len(seg) < 10:
                continue
            # Extrait ville et lieu du premier segment
            m = re.match(r'^\d+\.\s*([A-ZÀ-ÖØ-Þ][^\-]{2,60}?)\s*[-–]\s*(.+)$', seg, re.S)
            if m:
                ville = m.group(1).strip()
                lieu_rest = m.group(2).strip()
                # Nettoie le CP si présent après la ville
                ville = re.sub(r'\s+\d{5}$', '', ville)
                entries.append({"ville": ville, "lieu": lieu_rest})
            else:
                entries.append({"ville": dept_name, "lieu": seg})

        if not entries:
            return None

        # On ne retourne qu'un seul dict par normalize() — la boucle run()
        # traite chaque entrée. On stocke les suivantes dans _extra.
        if len(entries) > 1:
            self._pending = getattr(self, "_pending", [])
            self._pending.extend(entries[1:])

        first = entries[0]
        return {
            "ville": first["ville"],
            "dept": f"{dept_num} – {dept_name}",
            "diocese": diocese,
            "lieu": first["lieu"][:120],
            "adresse": "",
            "rite": "tridentin",
            "langue": "latin",
            "communaute": "Diocèse",
            "celebrant": "",
            "horaires": first["lieu"][:200],
            "contact": "",
        }

    def normalize_extra(self, extra_raw: Dict, parent_raw: Dict) -> Optional[Dict]:
        """Normalise les lieux supplémentaires d'un même département AMDG."""
        dept_num = parent_raw["dept_num"]
        dept_name = parent_raw["dept_name"]
        diocese = ""
        if dept_name:
            diocese = re.sub(r'^(Dioc[èe]se|Dioc[èe]se de|dioc[èe]se)\s+(de\s+|d\'|d\')?', '', dept_name).strip()
            if not diocese or diocese.lower() == dept_name.lower():
                diocese = dept_name
        return {
            "ville": extra_raw["ville"],
            "dept": f"{dept_num} – {dept_name}",
            "diocese": diocese,
            "lieu": extra_raw["lieu"][:120],
            "adresse": "",
            "rite": "tridentin",
            "langue": "latin",
            "communaute": "Diocèse",
            "celebrant": "",
            "horaires": extra_raw["lieu"][:200],
            "contact": "",
        }


# ─────────────────────────────────────────────────────────────────────
# La Porte Latine — WordPress/Elementor, CPT "lieux"
# ─────────────────────────────────────────────────────────────────────
class PorteLatineParser(Scraper):
    source_code = "portelatine"

    def __init__(self):
        self.base_url = "https://laportelatine.org"
        self.list_url = "https://laportelatine.org/lieux"
        self.pages = []

    def fetch(self) -> None:
        page = 1
        while True:
            url = self.list_url if page == 1 else f"{self.list_url}/page/{page}"
            html = fetch_url(url)
            if not html:
                break
            # Page vide → fin de la pagination
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select("h4.elementor-heading-title a")
            if not cards:
                logger.info(f"[portelatine] Fin de pagination à la page {page}")
                break
            self.pages.append(html)
            # Vérifie s'il y a une page suivante
            next_rel = soup.find("link", rel="next")
            if not next_rel:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
            if page > 150:  # garde-fou
                logger.warning("[portelatine] Garde-fou 150 pages atteint")
                break

    def parse(self) -> List[Dict]:
        results = []
        for html in self.pages:
            soup = BeautifulSoup(html, "lxml")
            # Cartes : h4.elementor-heading-title > a (lien vers page détail)
            cards = soup.select("h4.elementor-heading-title a")
            for card in cards:
                title = card.get_text(strip=True)
                href = card.get("href")
                if not title:
                    continue
                results.append({
                    "lieu": title,
                    "url_detail": href,
                })
        # Déduplication par URL
        seen = set()
        unique = []
        for r in results:
            if r["url_detail"] not in seen:
                seen.add(r["url_detail"])
                unique.append(r)
        return unique

    def normalize(self, raw: Dict) -> Optional[Dict]:
        """Le parseur liste ne donne pas tous les champs → on laisse le détail vide.
        La page détail serait fetchée par update_manager pour enrichir."""
        # Extraction d'info depuis l'URL : /lieux/{prieure}/{ville}
        m = re.search(r"/lieux/([^/]+)/([^/]+)", raw.get("url_detail", ""))
        ville = m.group(2).replace("-", " ").title() if m else ""
        prieure = m.group(1).replace("-", " ").title() if m else ""
        return {
            "ville": ville,
            "dept": "",
            "diocese": "",
            "lieu": raw.get("lieu", ""),
            "adresse": "",
            "rite": "tridentin",
            "langue": "latin",
            "communaute": "FSSPX" if prieure else "FSSPX",
            "celebrant": "",
            "horaires": "Voir site",
            "contact": "",
            "_url_detail": raw.get("url_detail"),
        }


# ─────────────────────────────────────────────────────────────────────
# trouverunemesse.com — agrégateur, requêtage par ville
# ─────────────────────────────────────────────────────────────────────
class TrouverUneMesseParser(Scraper):
    source_code = "trouverunemesse"

    def __init__(self):
        self.search_url = "https://trouverunemesse.com/recherche.php"
        self.villes = VILLES_PRINCIPALES
        self.pages = []

    def fetch(self) -> None:
        for ville in self.villes:
            url = f"{self.search_url}?lieu={ville.replace(' ', '+')}"
            html = fetch_url(url, timeout=20)
            if html:
                self.pages.append((ville, html))
            time.sleep(REQUEST_DELAY)

    def parse(self) -> List[Dict]:
        results = []
        for ville, html in self.pages:
            soup = BeautifulSoup(html, "lxml")
            for card in soup.select("article.result-card"):
                time_el = card.select_one(".mass-time")
                date_el = card.select_one(".mass-date")
                place_el = card.select_one(".result-place h3 a")
                addr_el = card.select_one(".result-place p")
                if not place_el:
                    continue
                results.append({
                    "ville_recherchee": ville,
                    "lieu": place_el.get_text(strip=True),
                    "adresse": addr_el.get_text(strip=True) if addr_el else "",
                    "horaires": f"{date_el.get_text(strip=True) if date_el else ''} {time_el.get_text(strip=True) if time_el else ''}".strip(),
                    "url_maps": place_el.get("href", ""),
                })
        return results

    def normalize(self, raw: Dict) -> Optional[Dict]:
        # Détection du rite/langue : difficile via cet agrégateur (pas de filtre).
        # Par défaut : paulvi/latin — à affiner via enrichissement.
        # Le lieu peut être une église "classique" → on filtre par mot-clés
        lieu = raw.get("lieu", "")
        adresse = raw.get("adresse", "")
        # Code postal dans l'adresse pour département
        cp_match = re.search(r"\b(\d{5})\b", adresse)
        dept_code = cp_match.group(1)[:2] if cp_match else ""
        return {
            "ville": raw.get("ville_recherchee", ""),
            "dept": dept_code,
            "diocese": "",
            "lieu": lieu,
            "adresse": adresse,
            "rite": "paulvi",
            "langue": "latin",
            "communaute": "Diocèse",
            "celebrant": "",
            "horaires": raw.get("horaires", ""),
            "contact": "",
        }


# ─────────────────────────────────────────────────────────────────────
# messes.info — fallback HTML (version GWT inutilisable)
# ─────────────────────────────────────────────────────────────────────
class MessesInfoParser(Scraper):
    source_code = "messes_info"

    def __init__(self):
        self.annuaire_url = "https://messes.info/annuaire/"
        self.pages = []

    def fetch(self) -> None:
        # Stratégie : récupérer la liste des départements, puis pour chaque
        # département les églises, puis les horaires. Pour rester simple et
        # respectueux, on ne fetch que la page annuaire de Paris en exemple.
        url = "https://messes.info/annuaire/48.857547:2.351376"
        html = fetch_url(url)
        if html:
            self.pages.append(html)

    def parse(self) -> List[Dict]:
        results = []
        for html in self.pages:
            soup = BeautifulSoup(html, "lxml")
            # Articles schema.org/Event dans le fallback HTML
            for article in soup.select("article[itemscope][itemtype*='schema.org/Event']"):
                name_el = article.find(attrs={"itemprop": "name"})
                url_el = article.find(attrs={"itemprop": "url"})
                addr_el = article.find(attrs={"itemprop": "streetAddress"})
                cp_el = article.find(attrs={"itemprop": "postalCode"})
                city_el = article.find(attrs={"itemprop": "addressLocality"})
                lat_el = article.find(attrs={"itemprop": "latitude"})
                lon_el = article.find(attrs={"itemprop": "longitude"})
                start_el = article.find(attrs={"itemprop": "startDate"})
                lang_div = None
                for div in article.find_all("div"):
                    txt = div.get_text(strip=True)
                    if txt in ("Français", "Latin"):
                        lang_div = txt
                        break
                results.append({
                    "nom": name_el.get_text(strip=True) if name_el else "",
                    "url_lieu": url_el.get("content") if url_el else "",
                    "adresse": addr_el.get_text(strip=True) if addr_el else "",
                    "cp": cp_el.get_text(strip=True) if cp_el else "",
                    "ville": city_el.get_text(strip=True) if city_el else "",
                    "lat": lat_el.get("content") if lat_el else None,
                    "lon": lon_el.get("content") if lon_el else None,
                    "horaires": start_el.get("content") if start_el else "",
                    "langue": lang_div or "",
                })
        return results

    def normalize(self, raw: Dict) -> Optional[Dict]:
        cp = raw.get("cp", "")
        dept_code = cp[:2] if len(cp) >= 2 else ""
        if cp.startswith("97") or cp.startswith("98"):
            dept_code = cp[:3]
        langue = "latin" if raw.get("langue") == "Latin" else "francais"
        return {
            "ville": raw.get("ville", ""),
            "dept": dept_code,
            "diocese": "",
            "lieu": raw.get("nom", ""),
            "adresse": raw.get("adresse", ""),
            "rite": "paulvi",
            "langue": langue,
            "communaute": "Diocèse",
            "celebrant": "",
            "horaires": raw.get("horaires", ""),
            "contact": "",
            "coord_lat": float(raw["lat"]) if raw.get("lat") else None,
            "coord_lon": float(raw["lon"]) if raw.get("lon") else None,
        }


# ─────────────────────────────────────────────────────────────────────
# Annuaire national messes.info (CEF) — grille géographique
# Crawl /annuaire/{lat}:{lon}?page=N sur une grille couvrant la France.
# ─────────────────────────────────────────────────────────────────────
class AnnuaireCEFParser(Scraper):
    source_code = "annuaire_cef"

    def __init__(self):
        self.annuaire_url = "https://messes.info/annuaire/"
        self.grid = GEO_GRID
        self.results = []

    def fetch(self) -> None:
        """Crawl la grille : pour chaque point, pagine jusqu'à épuisement.
        Extrait directement chaque article (nom, adresse, GPS, url)."""
        seen_urls = set()
        total_pages = 0
        for lat, lon in self.grid:
            point_urls = 0
            for page in range(1, GRID_MAX_PAGES + 1):
                url = f"{self.annuaire_url}{lat}:{lon}"
                if page > 1:
                    url += f"?page={page}"
                html = fetch_url(url, timeout=20)
                if not html:
                    break
                articles = re.findall(r'<article[^>]*>.*?</article>', html, re.S)
                if not articles:
                    break  # fin de la pagination pour ce point
                total_pages += 1
                new_count = 0
                for art in articles:
                    m_url = re.search(r'href="(/lieu/[^"]*)"', art)
                    if not m_url:
                        continue
                    path = m_url.group(1)
                    if path in seen_urls:
                        continue
                    seen_urls.add(path)
                    new_count += 1
                    self.results.append(self._parse_article(art, path))
                point_urls += new_count
                if new_count == 0 and page > 3:
                    break  # plus de nouveautés → point épuisé
                time.sleep(REQUEST_DELAY)
        logger.info(f"[annuaire_cef] {len(self.results)} lieux uniques, {total_pages} pages crawlées")

    def _parse_article(self, art: str, path: str) -> Dict:
        """Extrait les champs d'un article schema.org d'une page annuaire."""
        def _prop(prop: str) -> str:
            for pattern in (
                rf'itemprop="{prop}"[^>]*>([^<]*)<',
                rf'itemprop="{prop}" content="([^"]*)"',
            ):
                m2 = re.search(pattern, art)
                if m2 and m2.group(1).strip():
                    return m2.group(1).strip()
            return ""

        names = re.findall(r'itemprop="name">([^<]*)<', art)
        nom = names[0].strip() if names else ""
        adresse = _prop("streetAddress")
        cp = _prop("postalCode")
        ville = _prop("addressLocality")
        lat = _prop("latitude")
        lon = _prop("longitude")
        m_dept = re.search(r'/lieu/(\d{1,3}[AB]?)/', path)
        dept_code = m_dept.group(1) if m_dept else ""
        if not ville:
            m_ville = re.search(r'/lieu/\d+/([^/]+)/', path)
            ville = m_ville.group(1).replace("-", " ").title() if m_ville else ""
        try:
            lat_f = float(lat) if lat else None
            lon_f = float(lon) if lon else None
        except ValueError:
            lat_f = lon_f = None

        # Classification du rite :
        #   - nom contenant un mot-clé oriental → rite oriental
        #   - sinon église paroissiale générale → Paul VI en français (défaut)
        from utils import is_oriental
        if is_oriental(nom):
            rite, langue = "oriental", None
        else:
            rite, langue = "paulvi", "francais"

        return {
            "ville": ville,
            "dept": dept_code,
            "dept_code": dept_code,
            "dept_nom": "",
            "diocese": None,
            "lieu": nom,
            "adresse": adresse,
            "rite": rite,
            "langue": langue,
            "communaute": "Paroisse",
            "celebrant": "",
            "horaires": "",
            "contact": "",
            "url_detail": f"https://messes.info{path}",
            "coord_lat": lat_f,
            "coord_lon": lon_f,
        }

    def parse(self) -> List[Dict]:
        """Les articles sont déjà extraits dans fetch()."""
        return self.results

    def normalize(self, raw: Dict) -> Optional[Dict]:
        """Les données sont déjà normalisées par _parse_article."""
        return raw


PARSERS = {
    "amdg": AMDGParser,
    "portelatine": PorteLatineParser,
    "annuaire_cef": AnnuaireCEFParser,
    "trouverunemesse": TrouverUneMesseParser,
    "messes_info": MessesInfoParser,
}


def run_all_parsers(sources: List[str]) -> Dict[str, List[Dict]]:
    """Exécute les parseurs demandés. Retourne {source: [lieux_normés]}."""
    from config import SOURCES
    results = {}
    for code in sources:
        if code not in PARSERS:
            logger.warning(f"Parseur inconnu: {code}")
            continue
        try:
            parser = PARSERS[code]()
            results[code] = parser.run()
        except Exception as e:
            logger.error(f"Erreur parseur {code}: {e}", exc_info=True)
            results[code] = []
    return results


if __name__ == "__main__":
    logger.info("=== Test parseurs ===")
    res = run_all_parsers(["amdg", "portelatine", "trouverunemesse", "messes_info"])
    for source, items in res.items():
        logger.info(f"{source}: {len(items)} résultats")
        if items:
            logger.info(f"  Exemple: {items[0]}")