"""
Génère les pages SEO statiques par département :
output/departements/31-haute-garonne/index.html

Chaque page contient :
- meta title/description optimisés pour la recherche locale
- la liste des lieux du département (générée depuis la base)
- le maillage interne vers les départements voisins
- bloc affiliation discret + lien vers la carte interactive

C'est le levier SEO local : Google indexe 101 pages ciblées
« messe à [ville] », « messe en latin [département] », etc.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, OUTPUT_DIR, COMMUNE_LABELS, DEPT_COORDS, BASE_URL
from utils import setup_logging, slugify
from nav import build_nav, NAV_CSS

logger = setup_logging("generate_dept_pages")

# ── Menu sticky commun (chemins relatifs depuis /departements/XX-nom/) ──
DEPT_NAV = build_nav("../../")


# ── Modal horaires (HTML + JS) — injectée dans chaque page département ──
# Constante NON f-string : les accolades JS restent simples.
MODAL_BLOCK = """
<!-- Modal horaires : garde l'utilisateur dans le site -->
<div class="modal-overlay" id="horairesModal" style="display:none" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
  <div class="modal">
    <button class="modal-close" id="modalClose" aria-label="Fermer">✕</button>
    <h3 id="modalTitle"></h3>
    <div id="modalMeta"></div>
    <div class="modal-frame-wrap">
      <iframe id="modalFrame" src="" loading="lazy" title="Horaires sur messes.info"></iframe>
    </div>
    <div class="modal-actions">
      <a id="modalOpen" href="#" target="_blank" rel="noopener" class="messes-btn">Ouvrir dans messes.info</a>
      <button id="modalCloseBtn" class="share-btn">Fermer</button>
    </div>
  </div>
</div>
<script>
(function(){
  const modal = document.getElementById('horairesModal');
  if(!modal) return;
  const frame = document.getElementById('modalFrame');
  const open = document.getElementById('modalOpen');
  const title = document.getElementById('modalTitle');
  const meta = document.getElementById('modalMeta');
  const closeModal = ()=>{ modal.style.display='none'; frame.src=''; document.body.style.overflow=''; };
  document.addEventListener('click', e=>{
    const btn = e.target.closest('.horaires-btn');
    if(btn){
      title.textContent = btn.dataset.lieu ? btn.dataset.ville + ' — ' + btn.dataset.lieu : btn.dataset.ville;
      meta.textContent = 'Horaires et célébrations — source messes.info (Conférence des Évêques de France).';
      frame.src = btn.dataset.url;
      open.href = btn.dataset.url;
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
    }
  });
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.getElementById('modalCloseBtn').addEventListener('click', closeModal);
  modal.addEventListener('click', e=>{ if(e.target===modal) closeModal(); });
  document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeModal(); });
})();
</script>
"""


# ── Noms des départements français (numéro → nom, pour les pages) ─────
DEPT_NAMES = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes", "06": "Alpes-Maritimes", "07": "Ardèche", "08": "Ardennes",
    "09": "Ariège", "10": "Aube", "11": "Aude", "12": "Aveyron", "13": "Bouches-du-Rhône",
    "14": "Calvados", "15": "Cantal", "16": "Charente", "17": "Charente-Maritime",
    "18": "Cher", "19": "Corrèze", "2A": "Corse-du-Sud", "2B": "Haute-Corse",
    "21": "Côte-d'Or", "22": "Côtes-d'Armor", "23": "Creuse", "24": "Dordogne",
    "25": "Doubs", "26": "Drôme", "27": "Eure", "28": "Eure-et-Loir", "29": "Finistère",
    "30": "Gard", "31": "Haute-Garonne", "32": "Gers", "33": "Gironde", "34": "Hérault",
    "35": "Ille-et-Vilaine", "36": "Indre", "37": "Indre-et-Loire", "38": "Isère",
    "39": "Jura", "40": "Landes", "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire",
    "44": "Loire-Atlantique", "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne",
    "48": "Lozère", "49": "Maine-et-Loire", "50": "Manche", "51": "Marne", "52": "Haute-Marne",
    "53": "Mayenne", "54": "Meurthe-et-Moselle", "55": "Meuse", "56": "Morbihan",
    "57": "Moselle", "58": "Nièvre", "59": "Nord", "60": "Oise", "61": "Orne",
    "62": "Pas-de-Calais", "63": "Puy-de-Dôme", "64": "Pyrénées-Atlantiques",
    "65": "Hautes-Pyrénées", "66": "Pyrénées-Orientales", "67": "Bas-Rhin", "68": "Haut-Rhin",
    "69": "Rhône", "70": "Haute-Saône", "71": "Saône-et-Loire", "72": "Sarthe",
    "73": "Savoie", "74": "Haute-Savoie", "75": "Paris", "76": "Seine-Maritime",
    "77": "Seine-et-Marne", "78": "Yvelines", "79": "Deux-Sèvres", "80": "Somme",
    "81": "Tarn", "82": "Tarn-et-Garonne", "83": "Var", "84": "Vaucluse",
    "85": "Vendée", "86": "Vienne", "87": "Haute-Vienne", "88": "Vosges",
    "89": "Yonne", "90": "Territoire de Belfort", "91": "Essonne", "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis", "94": "Val-de-Marne", "95": "Val-d'Oise",
    "971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte",
    "20": "Corse", "97": "Outre-mer", "98": "Outre-mer", "987": "Polynésie française",
    "988": "Nouvelle-Calédonie", "975": "Saint-Pierre-et-Miquelon", "986": "Wallis-et-Futuna",
}


# ── Modèle de page département ─────────────────────────────────────────
def build_dept_page(dept_code: str, lieux: list[dict], voisins: list[str],
                    last_update: str) -> str:
    """Construit le HTML d'une page département."""
    dept_nom = DEPT_NAMES.get(dept_code, dept_code)
    nb = len(lieux)
    nb_trid = sum(1 for l in lieux if l["rite"] == "tridentin")

    title = f"Messes en {dept_nom} ({dept_code}) — annuaire des églises catholiques"
    desc = (f"Trouvez une messe en {dept_nom} : {nb} églises et lieux de culte"
            f"{f', dont {nb_trid} messes en latin (rite tridentin)' if nb_trid else ''}. "
            f"Horaires, adresses, GPS. Annuaire mis à jour quotidiennement.")

    # Villes du département (uniques, triées)
    villes = sorted({l["ville"] for l in lieux if l["ville"]}, key=lambda v: v.lower())

    # Liste des lieux
    cards = ""
    for l in sorted(lieux, key=lambda x: (x["ville"] or "").lower()):
        rite_tag = {
            "tridentin": "Tridentin · 1962",
            "paulvi": "Paul VI",
            "oriental": "Rite oriental",
        }.get(l["rite"], "Messe")
        lang = f' · {l["langue"]}' if l.get("langue") else ""
        hor = ""
        if l.get("horaires") and "voir site" not in l["horaires"].lower():
            hor = f'<div class="row"><span class="label">Horaires</span> — {l["horaires"][:200]}</div>'
        # Téléphone (premier numéro du contact)
        tel_html = ""
        if l.get("contact"):
            m_tel = re.search(r'(\b0\d(?:\s?\d){8}\b)', l["contact"])
            if m_tel:
                num = re.sub(r'\s+', '', m_tel.group(1))
                tel_html = f'<a class="tel-link" href="tel:{num}">📞 {m_tel.group(1)}</a>'
        url = f'<button class="messes-btn horaires-btn" data-url="{l["url_detail"]}" data-ville="{l["ville"] or ""}" data-lieu="{l["lieu"] or ""}">Horaires sur messes.info</button>' if l.get("url_detail") else ""
        if not l.get("url_detail") and l.get("coord_lat") is not None and l.get("coord_lon") is not None:
            # Lieu sans page messes.info mais avec GPS : horaires à proximité
            url = (f'<button class="messes-btn horaires-btn" data-url="https://messes.info/horaires/{l["coord_lat"]}:{l["coord_lon"]}" '
                   f'data-ville="{l["ville"] or ""}" data-lieu="{l["lieu"] or ""}">Horaires à proximité</button>')
        # Liens GPS (coord_lat/coord_lon)
        gps_html = ""
        if l.get("coord_lat") is not None and l.get("coord_lon") is not None:
            lat, lon = l["coord_lat"], l["coord_lon"]
            gps_html = (f'<a class="messes-btn gps" href="https://www.google.com/maps/search/?api=1&query={lat},{lon}" target="_blank" rel="noopener" title="Ouvrir dans Google Maps">Google Maps</a>'
                        f'<a class="messes-btn gps" href="https://waze.com/ul?ll={lat},{lon}&navigate=yes" target="_blank" rel="noopener" title="Ouvrir dans Waze">Waze</a>'
                        f'<a class="messes-btn gps" href="https://maps.apple.com/?q={lat},{lon}" target="_blank" rel="noopener" title="Ouvrir dans Plans (Apple)">Apple Maps</a>')
        cards += f"""
    <article class="card {l['rite'] or ''}" itemscope itemtype="https://schema.org/Church">
      <div class="card-top">
        <div class="card-ville" itemprop="name">{l['ville'] or ''}</div>
        <div class="card-dept">{l['dept'] or ''}</div>
      </div>
      <div class="card-lieu">{l['lieu'] or ''}</div>
      {f'<div class="card-adresse" itemprop="address">{l["adresse"]}</div>' if l.get("adresse") else ''}
      <div class="tags">
        <span class="tag {'rite-t' if l['rite']=='tridentin' else 'rite-p' if l['rite']=='paulvi' else 'rite-o' if l['rite']=='oriental' else 'lang'}">{rite_tag}{lang}</span>
        {f'<span class="tag comm">{l["communaute"]}</span>' if l.get("communaute") else ''}
      </div>
      {f'<div class="card-detail">{hor}</div>' if hor else ''}
      <div class="card-actions">{url}{gps_html}{tel_html}</div>
    </article>"""

    # Maillage interne : départements voisins (numéros proches)
    voisin_links = []
    for v in sorted(voisins):
        vn = DEPT_NAMES.get(v, v)
        voisin_links.append(f'<a href="../{v}-{slugify(vn)}/">{vn}</a>')
    voisin_html = " · ".join(voisin_links) if voisin_links else ""

    # Villes : liens ancrés vers la liste (simples textes pour SEO)
    villes_html = ", ".join(v for v in villes[:40])

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#6d2438">
<link rel="canonical" href="{BASE_URL}/departements/{dept_code}-{slugify(dept_nom)}/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "name": "Messes en {dept_nom}",
  "numberOfItems": {nb},
  "itemListElement": [
    {", ".join(f'{{"@type":"ListItem","position":{i+1},"name":"{l["lieu"]} — {l["ville"]}"}}' for i, l in enumerate(lieux[:50]))}
  ]
}}
</script>
<style>
  :root{{--ink:#221f2b;--parchment:#efe7d6;--burgundy:#6d2438;--gold:#a9822f;--slate:#5b5847;--card:#faf6ec;}}
  *{{box-sizing:border-box;}}
  body{{margin:0;background:var(--parchment);background-image:radial-gradient(rgba(109,36,56,0.05) 1px,transparent 1px);background-size:22px 22px;color:var(--ink);font-family:'Inter',sans-serif;line-height:1.5;}}
  .wrap{{max-width:1100px;margin:0 auto;padding:2rem 1.5rem;}}
  header{{border-bottom:2px solid var(--ink);padding-bottom:1.5rem;margin-bottom:1.5rem;}}
  .eyebrow{{font-size:0.72rem;letter-spacing:0.18em;text-transform:uppercase;color:var(--burgundy);font-weight:600;margin-bottom:0.5rem;}}
  h1{{font-family:'Fraunces',serif;font-weight:600;font-size:clamp(1.8rem,3.5vw,2.6rem);margin:0 0 0.5rem;}}
  .subtitle{{color:var(--slate);max-width:700px;}}
  .trust{{margin-top:1rem;color:var(--slate);font-size:0.85rem;}}
  .trust b{{color:var(--ink);}}
  .back{{display:inline-block;margin-bottom:1.2rem;color:var(--burgundy);font-weight:600;text-decoration:none;font-size:0.85rem;}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem;}}
  .card{{background:var(--card);border:1px solid var(--ink);padding:1rem;border-left:6px solid var(--gold);}}
  .card.tridentin{{border-left-color:var(--burgundy);}}
  .card-top{{display:flex;justify-content:space-between;gap:0.6rem;}}
  .card-ville{{font-family:'Fraunces',serif;font-weight:600;font-size:1.15rem;}}
  .card-dept{{font-size:0.7rem;color:var(--slate);white-space:nowrap;padding-top:0.2rem;}}
  .card-lieu{{font-size:0.85rem;margin:0.2rem 0;}}
  .card-adresse{{font-size:0.78rem;color:var(--slate);}}
  .tags{{margin:0.5rem 0;}}
  .tag{{font-size:0.68rem;font-weight:600;padding:0.2rem 0.5rem;border-radius:20px;border:1px solid var(--ink);margin-right:0.3rem;display:inline-block;}}
  .tag.rite-t{{background:var(--burgundy);color:#fff;border-color:var(--burgundy);}}
  .tag.rite-p{{background:var(--gold);color:#221f2b;border-color:var(--gold);}}
  .card-detail{{font-size:0.8rem;border-top:1px dashed var(--ink);padding-top:0.5rem;margin-top:0.5rem;}}
  .card-detail .label{{color:var(--burgundy);font-weight:600;}}
  .card-actions{{margin-top:0.6rem;}}
  .messes-btn{{font-size:0.7rem;font-weight:600;background:var(--burgundy);color:#fff;border:1px solid var(--burgundy);padding:0.28rem 0.55rem;border-radius:20px;text-decoration:none;display:inline-block;font-family:'Inter',sans-serif;cursor:pointer;}}
  .messes-btn:hover{{background:var(--ink);color:var(--parchment);}}
  .messes-btn.gps{{background:#2b5c8a;border-color:#2b5c8a;}}
  .card-actions{{display:flex;flex-wrap:wrap;gap:0.35rem;align-items:center;}}
  .modal-overlay{{position:fixed;inset:0;z-index:50;background:rgba(34,31,43,0.55);display:flex;align-items:center;justify-content:center;padding:1.5rem;}}
  .modal{{background:var(--card);border:2px solid var(--ink);box-shadow:8px 8px 0 rgba(34,31,43,0.35);max-width:860px;width:100%;max-height:90vh;display:flex;flex-direction:column;position:relative;}}
  .modal h3{{font-family:'Fraunces',serif;font-weight:600;font-size:1.25rem;margin:1rem 1.2rem 0.2rem;padding-right:2.5rem;}}
  .modal #modalMeta{{font-size:0.8rem;color:var(--slate);margin:0 1.2rem 0.6rem;}}
  .modal-frame-wrap{{flex:1;min-height:300px;border-top:1px solid var(--line,#ddd);border-bottom:1px solid var(--line,#ddd);}}
  .modal-frame-wrap iframe{{width:100%;height:100%;min-height:300px;border:0;background:#fff;}}
  .modal-actions{{display:flex;gap:0.5rem;align-items:center;padding:0.8rem 1.2rem;}}
  .modal-close{{position:absolute;top:0.6rem;right:0.8rem;background:none;border:none;font-size:1.1rem;cursor:pointer;color:var(--ink);padding:0.3rem;}}
  .modal-close:hover{{color:var(--burgundy);}}
  .tel-link{{font-size:0.72rem;font-weight:600;color:var(--ink);border:1px solid var(--ink);background:#fff;padding:0.28rem 0.55rem;border-radius:20px;text-decoration:none;display:inline-block;margin-left:0.3rem;}}
  .voisins{{margin-top:2rem;font-size:0.85rem;color:var(--slate);}}
  .voisins a{{color:var(--burgundy);}}
  .affil{{margin-top:2.5rem;border:1px solid var(--ink);background:var(--card);padding:1.2rem;font-size:0.85rem;}}
  .affil h2{{font-family:'Fraunces',serif;font-size:1.2rem;margin:0 0 0.6rem;}}
  .affil a{{color:var(--burgundy);font-weight:600;}}
  .affil .note{{color:var(--slate);font-size:0.75rem;margin-top:0.6rem;}}
  .support{{margin-top:1rem;}}
  .support a{{display:inline-block;background:var(--ink);color:var(--parchment);padding:0.6rem 1.2rem;text-decoration:none;font-weight:600;font-size:0.85rem;box-shadow:3px 3px 0 rgba(34,31,43,0.6);}}
  footer{{margin-top:3rem;border-top:1px solid var(--ink);padding-top:1rem;font-size:0.75rem;color:var(--slate);}}
  .villes{{font-size:0.85rem;color:var(--slate);margin-top:1rem;}}
  {NAV_CSS}
  .back{{display:inline-block;margin-bottom:1.2rem;color:var(--burgundy);font-weight:600;text-decoration:none;font-size:0.85rem;}}
</style>
</head>
<body>
{DEPT_NAV}
<div class="wrap">
  <a class="back" href="../../">← Retour à l'annuaire interactif</a>
  <header>
    <div class="eyebrow">Annuaire national · France</div>
    <h1>Messes en {dept_nom} ({dept_code})</h1>
    <p class="subtitle">{desc}</p>
    <div class="trust"><b>{nb}</b> lieux de culte répertoriés{f', dont <b>{nb_trid}</b> messes en latin (rite tridentin)' if nb_trid else ''} — mise à jour le {last_update}.</div>
  </header>

  <div class="villes"><strong>Villes couvertes :</strong> {villes_html or "—"}</div>

  <main class="grid">{cards}
  </main>

  <div class="affil">
    <h2>📖 Pour aller plus loin</h2>
    <p>Préparer une célébration, découvrir la liturgie traditionnelle ou trouver de la lecture spirituelle :
    <a href="https://www.arteg.fr/" target="_blank">Librairie Artège</a> ·
    <a href="https://www.lelivrechretien.fr/" target="_blank">Le Livre Chrétien</a> ·
    <a href="https://www.amazon.fr/s?k=missel+1962" target="_blank">Missels et livres de prière</a></p>
    <div class="note">L'annuaire est gratuit et sans publicité.</div>
  </div>

  <div class="voisins"><strong>Départements à proximité :</strong> {voisin_html or "—"}</div>

  <footer>
    Annuaire des messes en France — données sources : messes.info (CEF), AMDG, La Porte Latine.
    Vérifiez toujours les horaires avant de vous déplacer.
  </footer>
</div>
{MODAL_BLOCK}
</body>
</html>"""
    return html


# ── Génération ─────────────────────────────────────────────────────────
def generate_all(conn: sqlite3.Connection, last_update: str) -> int:
    """Génère toutes les pages départements. Retourne le nombre de pages."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ville, dept_code, dept_nom, diocese, lieu, adresse, rite,
               langue, communaute, horaires, contact, url_detail, coord_lat, coord_lon
        FROM lieux
        WHERE actif = 1 AND dept_code != ''
        ORDER BY dept_code, ville
    """)
    by_dept: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        d = {
            "ville": row[0], "dept_code": row[1], "dept_nom": row[2] or DEPT_NAMES.get(row[1], row[1]),
            "diocese": row[3] or "", "lieu": row[4], "adresse": row[5] or "",
            "rite": row[6], "langue": row[7], "communaute": row[8] or "",
            "horaires": row[9] or "", "contact": row[10] or "", "url_detail": row[11] or "",
            "coord_lat": row[12] if len(row) > 12 else None, "coord_lon": row[13] if len(row) > 13 else None,
            "dept": f"{row[1]} – {row[2] or DEPT_NAMES.get(row[1], row[1])}",
        }
        by_dept.setdefault(row[1], []).append(d)

    dept_dir = OUTPUT_DIR / "departements"
    dept_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    codes = sorted(by_dept.keys(), key=lambda c: (len(c), c))
    for code, lieux in by_dept.items():
        # Voisins : 2 précédents + 2 suivants dans le tri (maillage interne)
        idx = codes.index(code)
        voisins = [c for c in codes[max(0, idx-2):idx+3] if c != code][:4]
        dept_nom = DEPT_NAMES.get(code, code)
        page = build_dept_page(code, lieux, voisins, last_update)
        page_dir = dept_dir / f"{code}-{slugify(dept_nom)}"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(page, encoding="utf-8")
        count += 1
    logger.info(f"Pages départements générées: {count} ({len(codes)} départements)")
    return count


def generate_sitemap(by_dept_codes: list[str]) -> None:
    """Génère sitemap.xml (index + toutes les pages départements)."""
    base = BASE_URL
    urls = [f"<url><loc>{base}/</loc></url>", f"<url><loc>{base}/data.js</loc></url>"]
    for code in sorted(by_dept_codes, key=lambda c: (len(c), c)):
        nom = DEPT_NAMES.get(code, code)
        urls.append(f"<url><loc>{base}/departements/{code}-{slugify(nom)}/</loc></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    (OUTPUT_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")
    logger.info(f"Sitemap généré: {len(urls)} URLs")


def generate_robots() -> None:
    robots = f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"
    (OUTPUT_DIR / "robots.txt").write_text(robots, encoding="utf-8")
    logger.info("robots.txt généré")


def main() -> int:
    if not DB_PATH.exists():
        logger.error("Base absente")
        return 1
    conn = sqlite3.connect(DB_PATH)
    try:
        n = generate_all(conn, last_update_date(conn))
        # Codes pour le sitemap (les mêmes que les pages générées)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT dept_code FROM lieux WHERE actif=1 AND dept_code != ''")
        codes = [r[0] for r in cur.fetchall()]
        generate_sitemap(codes)
        generate_robots()
        print(f"DEPT_PAGES_OK pages={n}")
    finally:
        conn.close()
    return 0


def last_update_date(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM maj_log")
    row = cur.fetchone()
    if row and row[0]:
        try:
            return datetime.fromisoformat(row[0]).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return datetime.now().strftime("%d/%m/%Y")


if __name__ == "__main__":
    raise SystemExit(main())
