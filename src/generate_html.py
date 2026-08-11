"""
Génère le site annuaire à partir de la base SQLite :
- output/data.js  → toutes les églises (window.ANNUAIRE_DATA), chargé séparément
  (45k+ lieux = trop lourd pour un HTML inline ; gzip ~1.5 Mo via GitHub Pages)
- output/index.html → page légère avec les filtres, la carte et la pagination

Design original préservé (palette burgundy/parchment/gold, Fraunces/Source Serif 4/Inter).
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, HTML_OUTPUT, OUTPUT_DIR, COMMUNE_LABELS, DEPT_COORDS
from utils import setup_logging, slugify

logger = setup_logging("generate_html")


# ── Extraction des données ─────────────────────────────────────────────
def load_lieux(conn: sqlite3.Connection) -> list[dict]:
    """Charge les lieux actifs de la base."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ville, dept_code, dept_nom, diocese, lieu, adresse, rite,
               langue, communaute, celebrant, horaires, contact, url_detail,
               source_principale, coord_lat, coord_lon, derniere_maj
        FROM lieux
        WHERE actif = 1
        ORDER BY dept_code, ville
    """)
    lieux = []
    for row in cur.fetchall():
        dept_code, dept_nom = row[1], row[2]
        lieux.append({
            "ville": row[0],
            "dept": f"{dept_code} – {dept_nom}" if dept_nom else dept_code,
            "dept_code": dept_code,
            "diocese": row[3] or "",
            "lieu": row[4],
            "adresse": row[5] or "",
            "rite": row[6],           # None pour églises générales
            "langue": row[7],         # None pour églises générales
            "communaute": row[8] or "",
            "celebrant": row[9] or "",
            "horaires": row[10] or "",
            "contact": row[11] or "",
            "url_detail": row[12] or "",
            "source": row[13],
            "lat": row[14],
            "lon": row[15],
        })
    return lieux


def build_data_js(lieux: list[dict]) -> str:
    """Construit le fichier data.js (window.ANNUAIRE_DATA) — format compact."""
    lines = ["// Données annuaire générées automatiquement depuis la base SQLite.",
             "window.ANNUAIRE_DATA = ["]
    for l in lieux:
        def esc(v) -> str:
            return "null" if v is None else json.dumps(v, ensure_ascii=False)
        lines.append(
            "{ville:" + esc(l['ville']) +
            ",dept:" + esc(l['dept']) +
            ",d:" + esc(l['dept_code']) +
            ",dioc:" + esc(l['diocese']) +
            ",lieu:" + esc(l['lieu']) +
            ",adr:" + esc(l['adresse']) +
            ",rite:" + esc(l['rite']) +
            ",lang:" + esc(l['langue']) +
            ",comm:" + esc(l['communaute']) +
            ",cel:" + esc(l['celebrant']) +
            ",horaire:" + esc(l['horaires']) +
            ",tel:" + esc(l['contact']) +
            ",url:" + esc(l['url_detail']) +
            ",src:" + esc(l['source']) +
            ",lat:" + ("null" if l['lat'] is None else repr(l['lat'])) +
            ",lon:" + ("null" if l['lon'] is None else repr(l['lon'])) +
            "},"
        )
    lines.append("];")
    return "\n".join(lines)


def build_labels_js() -> str:
    """Construit le mapping communeLabels."""
    lines = []
    for code, label in COMMUNE_LABELS.items():
        lines.append(f'  {json.dumps(code, ensure_ascii=False)}: {json.dumps(label, ensure_ascii=False)}')
    return '{\n' + ',\n'.join(lines) + '\n}'


def build_dept_coords_js() -> str:
    """Construit le mapping DEPT_COORDS (centroïdes départements, fallback)."""
    lines = []
    for code, (lat, lon) in sorted(DEPT_COORDS.items()):
        lines.append(f'  "{code}":[{lat:.4f},{lon:.4f}]')
    return '{\n' + ',\n'.join(lines) + '\n}'


def last_update_date(conn: sqlite3.Connection) -> str:
    """Retourne la date de dernière mise à jour."""
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM maj_log")
    row = cur.fetchone()
    if row and row[0]:
        try:
            return datetime.fromisoformat(row[0]).strftime("%d/%m/%Y")
        except ValueError:
            pass
    cur.execute("SELECT MAX(derniere_maj) FROM lieux")
    row = cur.fetchone()
    if row and row[0]:
        try:
            return datetime.fromisoformat(row[0]).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return datetime.now().strftime("%d/%m/%Y")


def compute_stats(lieux: list[dict]) -> tuple:
    """(nb_lieux, nb_departements, nb_dioceses)"""
    nb = len(lieux)
    depts = len({l["dept_code"] for l in lieux if l["dept_code"]})
    dioceses = len({l["diocese"] for l in lieux if l["diocese"]})
    return nb, depts, dioceses


# ── Noms des départements (pour la navigation) ─────────────────────────
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


def build_dept_nav(conn: sqlite3.Connection) -> str:
    """Génère le bloc de navigation 'Explorer par département'
    (liens vers les 101 pages SEO + sélecteur rapide)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT dept_code, COUNT(*) FROM lieux
        WHERE actif = 1 AND dept_code != ''
        GROUP BY dept_code ORDER BY dept_code
    """)
    rows = cur.fetchall()
    if not rows:
        return ""

    # Liste de liens (maillage interne + navigation directe)
    links = []
    for code, count in rows:
        nom = DEPT_NAMES.get(code, code)
        slug = slugify(nom)
        links.append(f'<a href="departements/{code}-{slug}/">{code} · {nom}</a>')

    nav = (
        '<div class="dept-nav">'
        '<h2>Explorer par département</h2>'
        '<p class="dept-nav-sub">Pages dédiées avec la liste complète des lieux de culte et messes — utiles pour le référencement et la navigation directe.</p>'
        '<div class="dept-nav-links">' + "\n".join(f"    {l}" for l in links) + "</div>"
        "</div>"
    )
    return nav


# ── Template HTML ──────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trouver une messe en France : toutes les églises, messes en latin &amp; paroisses — Annuaire national</title>
<meta name="description" content="Annuaire national des églises et messes catholiques en France : messes en latin (rite tridentin 1962 &amp; Paul VI) et célébrations paroissiales. Filtrez par ville, rite, langue, diocèse et communauté. Horaires vérifiés, sources citées.">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#6d2438">

<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="Annuaire des messes en France">
<meta property="og:title" content="Trouver une messe partout en France">
<meta property="og:description" content="Toutes les églises catholiques de France — messes en latin (tridentin 1962 &amp; Paul VI) et paroisses. Recherche par ville, filtre par rite, langue, diocèse.">
<meta property="og:locale" content="fr_FR">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&amp;family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400&amp;family=Inter:wght@400;500;600;700&amp;display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#221f2b;
    --parchment:#efe7d6;
    --parchment-deep:#e4d9bf;
    --burgundy:#6d2438;
    --burgundy-deep:#4f1729;
    --gold:#a9822f;
    --gold-light:#cfae63;
    --slate:#5b5847;
    --card:#faf6ec;
    --line: rgba(34,31,43,0.14);
    --radius:3px;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;}
  body{
    background:var(--parchment);
    background-image:
      radial-gradient(rgba(109,36,56,0.05) 1px, transparent 1px);
    background-size: 22px 22px;
    color:var(--ink);
    font-family:'Source Serif 4', serif;
    min-height:100vh;
  }

  /* ---------- header ---------- */
  header{
    border-bottom:2px solid var(--ink);
    padding:2.6rem 1.5rem 1.8rem;
    max-width:1100px;
    margin:0 auto;
  }
  .eyebrow{
    font-family:'Inter',sans-serif;
    font-size:0.72rem;
    letter-spacing:0.18em;
    text-transform:uppercase;
    color:var(--burgundy);
    font-weight:600;
    margin-bottom:0.6rem;
  }
  h1{
    font-family:'Fraunces', serif;
    font-optical-sizing:auto;
    font-weight:600;
    font-size:clamp(2rem, 4.2vw, 3.1rem);
    margin:0 0 0.5rem;
    line-height:1.05;
    letter-spacing:-0.01em;
  }
  h1 em{
    font-style:italic;
    font-weight:400;
    color:var(--burgundy);
  }
  .subtitle{
    font-family:'Inter',sans-serif;
    font-size:0.95rem;
    color:var(--slate);
    max-width:700px;
    line-height:1.5;
  }
  .source-note{
    font-family:'Inter',sans-serif;
    font-size:0.78rem;
    color:var(--slate);
    margin-top:1rem;
    padding-top:0.9rem;
    border-top:1px solid var(--line);
    max-width:760px;
    line-height:1.55;
  }
  .source-note strong{color:var(--ink);}

  /* ---------- navigation principale sticky ---------- */
  .main-nav{
    position:sticky;
    top:0;
    z-index:20;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:1rem;
    background:var(--parchment);
    border-bottom:2px solid var(--ink);
    padding:0.7rem 1.5rem;
    max-width:1100px;
    margin:0 auto;
  }
  .main-nav .brand{
    font-family:'Fraunces',serif;
    font-weight:600;
    color:var(--burgundy);
    text-decoration:none;
    font-size:1.05rem;
    white-space:nowrap;
  }
  .nav-links{display:flex;gap:0.4rem;flex-wrap:wrap;}
  .nav-links a{
    font-size:0.8rem;
    font-weight:600;
    color:var(--ink);
    text-decoration:none;
    padding:0.35rem 0.7rem;
    border:1px solid var(--ink);
    background:var(--card);
  }
  .nav-links a:hover{background:var(--ink);color:var(--parchment);}
  @media (max-width:640px){
    .main-nav{flex-direction:column;align-items:flex-start;}
    .nav-links{width:100%;}
  }

  /* ---------- filters ---------- */
  .filters-wrap{
    background:var(--parchment);
    padding-top:1.4rem;
  }
  .filters{
    max-width:1100px;
    margin:0 auto;
    background:var(--card);
    border:1px solid var(--ink);
    box-shadow:5px 5px 0 rgba(34,31,43,0.9);
    padding:1.3rem 1.4rem 1.5rem;
    display:grid;
    grid-template-columns:repeat(auto-fit, minmax(190px,1fr));
    gap:1rem 1.2rem;
    font-family:'Inter',sans-serif;
  }
  .field label{
    display:block;
    font-size:0.68rem;
    letter-spacing:0.1em;
    text-transform:uppercase;
    font-weight:600;
    color:var(--burgundy);
    margin-bottom:0.4rem;
  }
  .field select, .field input[type="text"]{
    width:100%;
    font-family:'Inter',sans-serif;
    font-size:0.9rem;
    padding:0.5rem 0.6rem;
    border:1px solid var(--ink);
    background:#fff;
    color:var(--ink);
    border-radius:var(--radius);
    appearance:none;
  }
  .field select{
    background-image: linear-gradient(45deg, transparent 50%, var(--ink) 50%), linear-gradient(135deg, var(--ink) 50%, transparent 50%);
    background-position: calc(100% - 16px) center, calc(100% - 11px) center;
    background-size: 5px 5px, 5px 5px;
    background-repeat:no-repeat;
    padding-right:2rem;
  }
  .field select:focus, .field input:focus{
    outline:2px solid var(--burgundy);
    outline-offset:1px;
  }
  .rite-toggle{
    display:flex;
    gap:0.4rem;
  }
  .rite-toggle button{
    flex:1;
    font-family:'Inter',sans-serif;
    font-size:0.82rem;
    font-weight:600;
    padding:0.5rem 0.4rem;
    border:1px solid var(--ink);
    background:#fff;
    color:var(--ink);
    cursor:pointer;
    border-radius:var(--radius);
  }
  .rite-toggle button.active{
    background:var(--ink);
    color:var(--parchment);
  }
  .reset-row{
    grid-column:1/-1;
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-top:0.2rem;
    padding-top:0.9rem;
    border-top:1px solid var(--line);
  }
  #resultCount{
    font-family:'Inter',sans-serif;
    font-size:0.84rem;
    color:var(--slate);
  }
  #resultCount strong{color:var(--ink); font-size:1rem;}
  #resetBtn{
    font-family:'Inter',sans-serif;
    font-size:0.78rem;
    background:none;
    border:none;
    color:var(--burgundy);
    text-decoration:underline;
    cursor:pointer;
    padding:0;
  }

  /* ---------- legend ---------- */
  .legend{
    max-width:1100px;
    margin:1.1rem auto 0;
    padding:0 1.5rem;
    font-family:'Inter',sans-serif;
    font-size:0.74rem;
    color:var(--slate);
    display:flex;
    flex-wrap:wrap;
    gap:0.5rem 1.1rem;
  }
  .legend b{color:var(--ink);}

  /* ---------- results ---------- */
  main{
    max-width:1100px;
    margin:0 auto;
    padding:1.6rem 1.5rem 4rem;
  }
  .grid{
    display:grid;
    grid-template-columns:repeat(auto-fill, minmax(320px,1fr));
    gap:1rem;
  }
  .card{
    background:var(--card);
    border:1px solid var(--ink);
    padding:1.1rem 1.15rem 1.2rem;
    position:relative;
    border-left:6px solid var(--gold);
  }
  .card.tridentin{border-left-color:var(--burgundy);}
  .card.paulvi{border-left-color:var(--gold);}
  .card-top{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:0.6rem;
    margin-bottom:0.35rem;
  }
  .card-ville{
    font-family:'Fraunces', serif;
    font-weight:600;
    font-size:1.22rem;
    line-height:1.15;
  }
  .card-dept{
    font-family:'Inter',sans-serif;
    font-size:0.7rem;
    color:var(--slate);
    white-space:nowrap;
    padding-top:0.2rem;
  }
  .card-lieu{
    font-family:'Inter',sans-serif;
    font-size:0.85rem;
    color:var(--ink);
    margin-bottom:0.15rem;
  }
  .card-adresse{
    font-family:'Inter',sans-serif;
    font-size:0.78rem;
    color:var(--slate);
    margin-bottom:0.7rem;
  }
  .tags{
    display:flex;
    flex-wrap:wrap;
    gap:0.35rem;
    margin-bottom:0.7rem;
  }
  .tag{
    font-family:'Inter',sans-serif;
    font-size:0.68rem;
    font-weight:600;
    letter-spacing:0.03em;
    padding:0.2rem 0.5rem;
    border-radius:20px;
    border:1px solid var(--ink);
  }
  .tag.rite-t{background:var(--burgundy); color:#fff; border-color:var(--burgundy);}
  .tag.rite-p{background:var(--gold); color:#221f2b; border-color:var(--gold);}
  .tag.rite-o{background:#3a5a40; color:#fff; border-color:#3a5a40;}
  .tag.lang{background:#fff;}
  .tag.diocese{background:#fff;}
  .tag.comm{background:var(--ink); color:var(--parchment); border-color:var(--ink);}
  .tag.src{background:transparent; color:var(--slate); border-style:dashed;}

  .card-detail{
    font-family:'Inter',sans-serif;
    font-size:0.82rem;
    line-height:1.55;
    border-top:1px dashed var(--line);
    padding-top:0.6rem;
  }
  .card-detail .row{margin-bottom:0.15rem;}
  .card-detail .label{color:var(--burgundy); font-weight:600;}
  .card-detail a{color:var(--burgundy);}

  .empty{
    font-family:'Inter',sans-serif;
    text-align:center;
    padding:3rem 1rem;
    color:var(--slate);
  }

  footer{
    max-width:1100px;
    margin:0 auto;
    padding:1.5rem 1.5rem 3rem;
    font-family:'Inter',sans-serif;
    font-size:0.75rem;
    color:var(--slate);
    border-top:1px solid var(--line);
    line-height:1.6;
  }

  @media (max-width:560px){
    .filters{grid-template-columns:1fr 1fr;}
    .reset-row{flex-direction:column; align-items:flex-start; gap:0.5rem;}
  }

  /* ---------- breadcrumb ---------- */
  .breadcrumb{
    max-width:1100px;
    margin:0 auto;
    padding:0.9rem 1.5rem 0;
    font-family:'Inter',sans-serif;
    font-size:0.74rem;
    color:var(--slate);
  }
  .breadcrumb a{color:var(--slate); text-decoration:underline;}
  .breadcrumb span[aria-current]{color:var(--ink); font-weight:600;}

  /* ---------- navigation par départements ---------- */
  .dept-nav{
    max-width:1100px;
    margin:0 auto;
    padding:2rem 1.5rem 1rem;
  }
  .dept-nav h2{
    font-family:'Fraunces', serif;
    font-weight:600;
    font-size:1.5rem;
    margin:0 0 0.4rem;
  }
  .dept-nav-sub{
    font-family:'Inter',sans-serif;
    font-size:0.82rem;
    color:var(--slate);
    margin:0 0 1rem;
    max-width:700px;
  }
  .dept-nav-links{
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(200px,1fr));
    gap:0.35rem 1rem;
  }
  .dept-nav-links a{
    font-family:'Inter',sans-serif;
    font-size:0.8rem;
    color:var(--burgundy);
    text-decoration:none;
    padding:0.3rem 0.4rem;
    border-bottom:1px solid var(--line);
  }
  .dept-nav-links a:hover{background:var(--card); text-decoration:underline;}

  /* ---------- trust bar ---------- */
  .trust-bar{
    display:flex;
    flex-wrap:wrap;
    gap:1.3rem;
    margin-top:1.2rem;
    font-family:'Inter',sans-serif;
    font-size:0.78rem;
    color:var(--slate);
  }
  .trust-bar b{color:var(--ink); font-family:'Fraunces',serif; font-size:1.05rem;}

  /* ---------- CTA / geoloc ---------- */
  .cta-row{
    display:flex;
    flex-wrap:wrap;
    gap:0.7rem;
    margin-top:1.3rem;
  }
  .btn-primary{
    font-family:'Inter',sans-serif;
    font-weight:600;
    font-size:0.86rem;
    background:var(--burgundy);
    color:#fff;
    border:1px solid var(--ink);
    padding:0.7rem 1.1rem;
    cursor:pointer;
    box-shadow:3px 3px 0 rgba(34,31,43,0.9);
    display:inline-flex;
    align-items:center;
    gap:0.45rem;
  }
  .btn-primary:hover{background:var(--burgundy-deep);}
  .btn-primary:active{box-shadow:1px 1px 0 rgba(34,31,43,0.9); transform:translate(2px,2px);}
  .btn-primary[disabled]{opacity:0.55; cursor:default;}
  #geoStatus{
    font-family:'Inter',sans-serif;
    font-size:0.76rem;
    color:var(--slate);
    align-self:center;
  }

  /* ---------- share button on cards ---------- */
  .card-actions{
    display:flex;
    justify-content:flex-end;
    gap:0.5rem;
    margin-top:0.5rem;
    flex-wrap:wrap;
  }
  .share-btn, .messes-btn{
    font-family:'Inter',sans-serif;
    font-size:0.7rem;
    font-weight:600;
    background:none;
    border:1px solid var(--ink);
    padding:0.28rem 0.55rem;
    cursor:pointer;
    color:var(--ink);
    border-radius:20px;
    text-decoration:none;
    display:inline-block;
  }
  .share-btn:hover, .messes-btn:hover{background:var(--ink); color:var(--parchment);}
  .messes-btn{background:var(--burgundy); border-color:var(--burgundy); color:#fff;}
  .messes-btn:hover{background:var(--burgundy-deep); color:#fff;}
  .messes-btn.gps{background:#2b5c8a; border-color:#2b5c8a;}
  .messes-btn.gps:hover{background:#1e4266;}
  .card-distance{
    font-family:'Inter',sans-serif;
    font-size:0.68rem;
    font-weight:600;
    color:var(--burgundy);
    white-space:nowrap;
  }

  /* ---------- pagination ---------- */
  .more-row{
    text-align:center;
    margin:1.5rem 0;
  }
  #moreBtn{
    font-family:'Inter',sans-serif;
    font-size:0.86rem;
    font-weight:600;
    background:var(--card);
    color:var(--ink);
    border:1px solid var(--ink);
    padding:0.7rem 1.6rem;
    cursor:pointer;
    box-shadow:3px 3px 0 rgba(34,31,43,0.9);
  }
  #moreBtn:hover{background:var(--parchment-deep);}

  /* ---------- FAQ ---------- */
  .faq{
    max-width:1100px;
    margin:0 auto;
    padding:0 1.5rem 2rem;
  }
  .faq h2{
    font-family:'Fraunces', serif;
    font-weight:600;
    font-size:1.5rem;
    margin:0 0 1rem;
  }
  .faq details{
    border-bottom:1px solid var(--line);
    padding:0.9rem 0;
    font-family:'Inter',sans-serif;
  }
  .faq summary{
    font-weight:600;
    font-size:0.92rem;
    cursor:pointer;
    color:var(--ink);
  }
  .faq p{
    font-size:0.86rem;
    color:var(--slate);
    line-height:1.6;
    margin:0.6rem 0 0;
  }

  .report-cta{
    font-family:'Inter',sans-serif;
    font-size:0.78rem;
    margin-top:0.6rem;
  }
  .report-cta a{color:var(--burgundy); font-weight:600;}
</style>

<script type="application/ld+json">
{
  "@context":"https://schema.org",
  "@type":"WebSite",
  "name":"Annuaire des messes en France",
  "description":"Annuaire national des églises catholiques et messes en France : messes en latin (rite tridentin 1962 et Paul VI) et célébrations paroissiales.",
  "inLanguage":"fr-FR"
}
</script>
<script type="application/ld+json">
{
  "@context":"https://schema.org",
  "@type":"FAQPage",
  "mainEntity":[
    {
      "@type":"Question",
      "name":"Comment trouver une messe près de chez moi ?",
      "acceptedAnswer":{"@type":"Answer","text":"Utilisez le bouton de géolocalisation pour trier les lieux par proximité, ou entrez votre ville / code postal dans la recherche. Vous pouvez affiner avec les filtres rite, langue, diocèse et communauté."}
    },
    {
      "@type":"Question",
      "name":"Qu'est-ce que la messe tridentine ?",
      "acceptedAnswer":{"@type":"Answer","text":"La messe tridentine, ou forme extraordinaire du rite romain, est célébrée selon le missel romain de 1962, en latin. Elle a été confirmée comme légitime par le motu proprio Summorum Pontificum de Benoît XVI en 2007, avec des conditions révisées depuis par Traditionis Custodes (2021)."}
    },
    {
      "@type":"Question",
      "name":"Quelle différence entre le rite tridentin et une messe Paul VI en latin ?",
      "acceptedAnswer":{"@type":"Answer","text":"Le rite tridentin suit le missel de 1962. La messe Paul VI suit le missel de 1969/1970 issu du concile Vatican II (forme ordinaire) : elle peut être célébrée en français ou en latin selon les paroisses, avec la même structure liturgique que la messe habituelle."}
    },
    {
      "@type":"Question",
      "name":"Quelle est la différence entre FSSP, ICRSP, IBP et FSSPX ?",
      "acceptedAnswer":{"@type":"Answer","text":"FSSP, ICRSP et IBP sont des instituts de droit pontifical en pleine communion avec Rome, dont les prêtres célèbrent la forme extraordinaire avec l'accord de l'évêque du lieu. La FSSPX (Fraternité Sacerdotale Saint-Pie X) n'est pas en pleine communion canonique avec Rome ; ses lieux de culte sont signalés séparément sur cet annuaire."}
    }
  ]
}
</script>
</head>
<body>

<nav class="main-nav" aria-label="Navigation principale">
  <a href="index.html" class="brand">🕯️ Messes en France</a>
  <div class="nav-links">
    <a href="messes-en-latin.html">Messes en latin</a>
    <a href="rites-orientaux.html">Rites orientaux</a>
    <a href="departements/index.html">Départements</a>
    <a href="a-propos.html">À propos</a>
  </div>
</nav>

<header>
  <div class="eyebrow">Annuaire national · France</div>
  <h1>Trouvez une messe <em>partout en France</em></h1>
  <p class="subtitle">Toutes les églises catholiques de France — messes en latin (rite tridentin 1962 &amp; Paul VI) et célébrations paroissiales. Recherchez par ville ou code postal, filtrez par rite, langue, diocèse et communauté.</p>

  <div class="trust-bar">
    <div><b id="trustCount">—</b> lieux référencés</div>
    <div><b id="trustDepts">{{DEPT_COUNT}}</b> départements couverts</div>
    <div><b>{{LAST_UPDATE}}</b> dernière mise à jour des sources</div>
  </div>

  <div class="cta-row">
    <button class="btn-primary" id="geoBtn">📍 Trouver la messe la plus proche de moi</button>
    <span id="geoStatus"></span>
  </div>
</header>

<div class="filters-wrap">
  <div class="filters">
    <div class="field" style="grid-column:1/-1;">
      <label for="q">Recherche (ville, code postal, église, célébrant)</label>
      <input type="text" id="q" placeholder="Ex. Toulouse, 75007, Saint-Eugène, ICRSP…">
    </div>

    <div class="field">
      <label for="rite">Rite</label>
      <select id="rite">
        <option value="all">Tous les rites</option>
        <option value="tridentin">Tridentin (missel 1962)</option>
        <option value="paulvi-latin">Paul VI — Latin</option>
        <option value="paulvi-francais">Paul VI — Français</option>
        <option value="oriental">Rites orientaux catholiques</option>
      </select>
    </div>

    <div class="field">
      <label for="langue">Langue</label>
      <select id="langue">
        <option value="all">Toutes</option>
        <option value="latin">Latin</option>
        <option value="francais">Français</option>
      </select>
    </div>

    <div class="field">
      <label for="diocese">Diocèse</label>
      <select id="diocese"><option value="all">Tous</option></select>
    </div>

    <div class="field">
      <label for="communaute">Communauté</label>
      <select id="communaute"><option value="all">Toutes</option></select>
    </div>

    <div class="reset-row">
      <div id="resultCount"></div>
      <button id="resetBtn">Réinitialiser les filtres</button>
    </div>
  </div>

  <div class="legend" id="legend"></div>
</div>

<main>
  <div class="grid" id="grid"></div>
  <div class="more-row" id="moreRow" style="display:none;">
    <button id="moreBtn">Afficher plus de lieux</button>
  </div>
  <div class="empty" id="emptyState" style="display:none;">Aucun lieu ne correspond à ces filtres.</div>
</main>

{{DEPT_NAV}}

<section class="faq" aria-labelledby="faqTitle">
  <h2 id="faqTitle">Questions fréquentes</h2>
  <details>
    <summary>Comment trouver une messe près de chez moi ?</summary>
    <p>Utilisez le bouton de géolocalisation pour trier les lieux par proximité, ou entrez votre ville / code postal dans la recherche. Pour les horaires précis, cliquez sur « Horaires sur messes.info » sur la carte du lieu.</p>
  </details>
  <details>
    <summary>Qu'est-ce que la messe tridentine ?</summary>
    <p>La messe tridentine, ou forme extraordinaire du rite romain, est célébrée selon le missel romain de 1962, en latin. Elle a été confirmée comme légitime par le motu proprio Summorum Pontificum de Benoît XVI en 2007, avec des conditions révisées depuis par Traditionis Custodes (2021).</p>
  </details>
  <details>
    <summary>Quelle différence entre le rite tridentin et une messe Paul VI en latin ?</summary>
    <p>Le rite tridentin suit le missel de 1962. La messe Paul VI suit le missel de 1969/1970 issu du concile Vatican II (forme ordinaire) : elle peut être célébrée en français ou en latin selon les paroisses, avec la même structure liturgique que la messe habituelle.</p>
  </details>
  <details>
    <summary>Comment signaler une erreur ou un lieu manquant ?</summary>
    <p>Écrivez-nous via le lien en bas de page : chaque correction est intégrée à la prochaine mise à jour automatique.</p>
  </details>
  <div class="report-cta">
    Une erreur, un horaire changé, un lieu manquant ? <a href="mailto:contact@exemple.fr?subject=Correction%20annuaire%20messes">Signalez-le en un mail →</a>
  </div>
</section>

<footer>
  Rite <strong>Tridentin</strong> = forme extraordinaire du rite romain, célébrée selon le missel de 1962
  (motu proprio Summorum Pontificum / Ecclesia Dei) — toujours en latin.<br>
  Rite <strong>Paul VI</strong> = forme ordinaire du rite romain (missel de 1969/1970), qui peut être célébrée en
  latin ou en français selon les paroisses.<br><br>
  Communautés représentées — <strong>FSSP</strong> : Fraternité Sacerdotale Saint-Pierre ·
  <strong>ICRSP</strong> : Institut du Christ-Roi Souverain-Prêtre · <strong>IBP</strong> : Institut du Bon Pasteur ·
  <strong>FSTB</strong> : Fraternité Saint-Thomas-Becket · <strong>CRMD</strong> : Chanoines Réguliers de la Mère de
  Dieu · <strong>FSVF</strong> : Fraternité Saint-Vincent-Ferrier · <strong>MMD</strong> : Missionnaires de la
  Miséricorde Divine · <strong>Bénédictins</strong> : moines/moniales de l'ordre de Saint-Benoît ·
  <strong>Diocèse</strong> : prêtre incardiné dans le diocèse · <strong>Paroisse</strong> : église paroissiale générale ·
  <strong>FSSPX</strong> : Fraternité Sacerdotale Saint-Pie X (hors pleine communion canonique — voir note en en-tête) ·
  <strong>Fraternité de la Transfiguration</strong>, <strong>Capucins de Morgon</strong>,
  <strong>Dominicaines contemplatives</strong> : communautés proches de la FSSPX.<br><br>
  <strong>Annuaire gratuit et sans publicité.</strong> Pour aller plus loin :
  <a href="https://www.arteg.fr/">Librairie Artège</a> ·
  <a href="https://www.lelivrechretien.fr/">Le Livre Chrétien</a> ·
  <a href="https://www.amazon.fr/s?k=missel+1962">missels &amp; livres de prière</a>.<br><br>
  <a href="a-propos.html">À propos, sources des données et note FSSPX →</a>
</footer>

<!-- Données : fichier séparé pour éviter un HTML de plusieurs Mo -->
<script src="data.js"></script>
<script>
// ---------------------------------------------------------------
// Données générées automatiquement depuis la base SQLite
// Dernière génération : {{GENERATED_AT}}
// ---------------------------------------------------------------
const DATA = window.ANNUAIRE_DATA || [];

// ---------------------------------------------------------------
// Mapping communautés → labels complets
// ---------------------------------------------------------------
const communeLabels = {{LABELS_JS}};

// Centroïdes approximatifs des préfectures de département — utilisés
// uniquement pour les lieux sans GPS précis (fallback).
const DEPT_COORDS = {{DEPT_COORDS_JS}};

function haversine(lat1,lon1,lat2,lon2){
  const R=6371, toRad=x=>x*Math.PI/180;
  const dLat=toRad(lat2-lat1), dLon=toRad(lon2-lon1);
  const a=Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
  return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
}

let userPos = null; // {lat, lon}

function locateMe(){
  const btn=document.getElementById('geoBtn');
  const status=document.getElementById('geoStatus');
  if(!navigator.geolocation){
    status.textContent="Géolocalisation non disponible sur ce navigateur.";
    return;
  }
  btn.disabled=true;
  status.textContent="Localisation en cours…";
  navigator.geolocation.getCurrentPosition(
    pos=>{
      userPos = {lat:pos.coords.latitude, lon:pos.coords.longitude};
      status.textContent="Trié par proximité (GPS précis pour la plupart des lieux).";
      btn.disabled=false;
      visibleCount = PAGE_SIZE;
      render();
      document.getElementById('grid').scrollIntoView({behavior:'smooth', block:'start'});
    },
    err=>{
      status.textContent="Localisation refusée ou indisponible — utilisez plutôt la recherche.";
      btn.disabled=false;
    },
    {timeout:8000}
  );
}

let state = {rite:"all", langue:"all", diocese:"all", communaute:"all", q:""};
const PAGE_SIZE = 100;
let visibleCount = PAGE_SIZE;

function uniqueSorted(arr){return [...new Set(arr.filter(Boolean))].sort((a,b)=>a.localeCompare(b,'fr'));}

// --------- synchro état <-> URL (partage / retour arrière) ---------
function stateFromURL(){
  const p = new URLSearchParams(location.search);
  ['rite','langue','diocese','communaute','q'].forEach(k=>{
    if(p.has(k)) state[k]=p.get(k);
  });
}
function urlFromState(){
  const p = new URLSearchParams();
  Object.entries(state).forEach(([k,v])=>{ if(v && v!=='all') p.set(k,v); });
  const qs = p.toString();
  history.replaceState(null,'', qs ? ('?'+qs) : location.pathname);
}

function populateSelects(){
  const dioceseSel = document.getElementById('diocese');
  uniqueSorted(DATA.map(d=>d.dioc)).forEach(d=>{
    const o=document.createElement('option'); o.value=d; o.textContent=d; dioceseSel.appendChild(o);
  });
  const commSel = document.getElementById('communaute');
  uniqueSorted(DATA.map(d=>d.comm)).forEach(c=>{
    const o=document.createElement('option'); o.value=c; o.textContent=communeLabels[c]||c; commSel.appendChild(o);
  });
}

function buildLegend(){
  const legend=document.getElementById('legend');
  const counts={};
  DATA.forEach(d=>{counts[d.comm]=(counts[d.comm]||0)+1;});
  // Légende : communautés spéciales d'abord, "Paroisse" compacte
  const specials = Object.keys(counts).filter(c=>c!=='Paroisse').sort();
  const paroisse = counts['Paroisse']||0;
  let html = '';
  if(paroisse) html += `<span><b>Paroisse</b> · ${paroisse} lieu${paroisse>1?'x':''}</span>`;
  specials.forEach(c=>{
    html += `<span><b>${c}</b> · ${counts[c]} lieu${counts[c]>1?'x':''}</span>`;
  });
  legend.innerHTML = html;
}

function riteMatches(d, riteVal){
  if(riteVal==='all') return true;
  if(riteVal==='tridentin') return d.rite==='tridentin';
  if(riteVal==='paulvi-latin') return d.rite==='paulvi' && d.lang==='latin';
  if(riteVal==='paulvi-francais') return d.rite==='paulvi' && d.lang==='francais';
  if(riteVal==='oriental') return d.rite==='oriental';
  return true;
}

function matches(d){
  if(!riteMatches(d, state.rite)) return false;
  if(state.langue!=='all' && d.lang!==state.langue) return false;
  if(state.diocese!=='all' && d.dioc!==state.diocese) return false;
  if(state.communaute!=='all' && d.comm!==state.communaute) return false;
  if(state.q){
    const hay = ((d.ville||'')+' '+(d.lieu||'')+' '+(d.cel||'')+' '+(d.dioc||'')+' '+(d.dept||'')+' '+(d.adr||'')).toLowerCase();
    if(!hay.includes(state.q.toLowerCase())) return false;
  }
  return true;
}

function slugify(s){
  return (s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'');
}

function distFor(d){
  if(userPos && d.lat!=null && d.lon!=null){
    return haversine(userPos.lat,userPos.lon,d.lat,d.lon);
  }
  if(userPos){
    const coord = DEPT_COORDS[d.d];
    return coord ? haversine(userPos.lat,userPos.lon,coord[0],coord[1]) : null;
  }
  return null;
}

function render(){
  let results = DATA.filter(matches);

  if(userPos){
    results = results.map(d=>{ return {...d, _dist:distFor(d)}; }).sort((a,b)=>{
      if(a._dist==null) return 1;
      if(b._dist==null) return -1;
      return a._dist-b._dist;
    });
  } else {
    results = results.sort((a,b)=>((a.dept||'').localeCompare(b.dept||'','fr')) || (a.ville||'').localeCompare(b.ville||'','fr'));
  }

  const grid = document.getElementById('grid');
  const empty = document.getElementById('emptyState');
  const moreRow = document.getElementById('moreRow');
  document.getElementById('resultCount').innerHTML = `<strong>${results.length}</strong> lieu${results.length>1?'x':''} de culte`;

  if(results.length===0){
    grid.innerHTML='';
    empty.style.display='block';
    moreRow.style.display='none';
    return;
  }
  empty.style.display='none';

  const slice = results.slice(0, visibleCount);
  grid.innerHTML = slice.map(d=>{
    const cardId = slugify((d.ville||'')+'-'+(d.lieu||''));
    let riteTag;
    if(d.rite==='tridentin') riteTag = `<span class="tag rite-t">Tridentin · 1962</span>`;
    else if(d.rite==='oriental') riteTag = `<span class="tag rite-o">Rite oriental</span>`;
    else if(d.rite==='paulvi' && d.lang==='latin') riteTag = `<span class="tag rite-p">Paul VI · Latin</span>`;
    else if(d.rite==='paulvi' && d.lang==='francais') riteTag = `<span class="tag rite-p">Paul VI · Français</span>`;
    else riteTag = `<span class="tag lang">Messe</span>`;
    const langTag = d.lang ? `<span class="tag lang">${d.lang==='latin'?'Latin':'Français'}</span>` : '';
    const commTag = d.comm ? `<span class="tag comm">${d.comm}</span>` : '';
    const diocTag = d.dioc ? `<span class="tag diocese">${d.dioc}</span>` : '';
    const srcTag = d.src ? `<span class="tag src">${d.src}</span>` : '';
    const messesBtn = d.url ? `<a class="messes-btn" href="${d.url}" target="_blank" rel="noopener">Horaires sur messes.info</a>` : '';
    const gpsBtn = (d.lat!=null && d.lon!=null) ? `
      <a class="messes-btn gps" href="https://www.google.com/maps/search/?api=1&query=${d.lat},${d.lon}" target="_blank" rel="noopener" title="Ouvrir dans Google Maps">Google Maps</a>
      <a class="messes-btn gps" href="https://waze.com/ul?ll=${d.lat},${d.lon}&navigate=yes" target="_blank" rel="noopener" title="Ouvrir dans Waze">Waze</a>
      <a class="messes-btn gps" href="https://maps.apple.com/?q=${d.lat},${d.lon}" target="_blank" rel="noopener" title="Ouvrir dans Plans (Apple)">Apple Maps</a>` : '';
    return `
    <article class="card ${d.rite||''}" id="${cardId}" itemscope itemtype="https://schema.org/Church">
      <div class="card-top">
        <div class="card-ville" itemprop="name">${d.ville||''}</div>
        <div class="card-dept">${d.dept||''}${d._dist!=null?` · <span class="card-distance">~${Math.round(d._dist)} km</span>`:''}</div>
      </div>
      <div class="card-lieu">${d.lieu||''}</div>
      ${d.adr?`<div class="card-adresse" itemprop="address">${d.adr}</div>`:''}
      <div class="tags">
        ${riteTag}
        ${langTag}
        ${commTag}
        ${diocTag}
        ${srcTag}
      </div>
      <div class="card-detail">
        ${d.horaire?`<div class="row"><span class="label">Horaires</span> — ${d.horaire}</div>`:''}
        ${d.cel?`<div class="row"><span class="label">Célébrant</span> — ${d.cel}</div>`:''}
        ${d.tel?`<div class="row"><span class="label">Contact</span> — ${d.tel}</div>`:''}
      </div>
      <div class="card-actions">
        ${messesBtn}
        ${gpsBtn}
        <button class="share-btn" data-share="${cardId}">🔗 Copier le lien</button>
      </div>
    </article>
  `;}).join('');

  if(results.length > visibleCount){
    moreRow.style.display='block';
  } else {
    moreRow.style.display='none';
  }
  document.getElementById('trustCount').textContent = DATA.length;
}

document.getElementById('grid').addEventListener('click', e=>{
  const btn = e.target.closest('.share-btn');
  if(!btn) return;
  const url = location.origin + location.pathname + location.search + '#' + btn.dataset.share;
  navigator.clipboard?.writeText(url).then(()=>{
    const original = btn.textContent;
    btn.textContent = '✓ Lien copié';
    setTimeout(()=>btn.textContent=original, 1500);
  }).catch(()=>{});
});

document.getElementById('moreBtn').addEventListener('click', ()=>{
  visibleCount += PAGE_SIZE;
  render();
});

document.getElementById('geoBtn').addEventListener('click', locateMe);

// Rien à caler : seul le menu principal est sticky, les filtres défilent.

document.getElementById('rite').addEventListener('change', e=>{state.rite=e.target.value; visibleCount=PAGE_SIZE; urlFromState(); render();});
document.getElementById('langue').addEventListener('change', e=>{state.langue=e.target.value; visibleCount=PAGE_SIZE; urlFromState(); render();});
document.getElementById('diocese').addEventListener('change', e=>{state.diocese=e.target.value; visibleCount=PAGE_SIZE; urlFromState(); render();});
document.getElementById('communaute').addEventListener('change', e=>{state.communaute=e.target.value; visibleCount=PAGE_SIZE; urlFromState(); render();});
document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; visibleCount=PAGE_SIZE; urlFromState(); render();});
document.getElementById('resetBtn').addEventListener('click', ()=>{
  state = {rite:"all", langue:"all", diocese:"all", communaute:"all", q:""};
  userPos = null;
  visibleCount = PAGE_SIZE;
  document.getElementById('geoStatus').textContent='';
  document.getElementById('q').value='';
  document.getElementById('rite').value='all';
  document.getElementById('langue').value='all';
  document.getElementById('diocese').value='all';
  document.getElementById('communaute').value='all';
  urlFromState(); render();
});

populateSelects();
buildLegend();
stateFromURL();
document.getElementById('q').value = state.q;
document.getElementById('rite').value = state.rite;
document.getElementById('langue').value = state.langue;
document.getElementById('diocese').value = state.diocese;
document.getElementById('communaute').value = state.communaute;
render();

if(location.hash){
  const target = document.getElementById(location.hash.slice(1));
  if(target) setTimeout(()=>target.scrollIntoView({behavior:'smooth', block:'center'}), 300);
}
</script>
</body>
</html>
"""


def main():
    logger.info("=== Génération du site annuaire ===")
    if not DB_PATH.exists():
        logger.error("Base SQLite absente. Lancez d'abord create_db.py")
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        lieux = load_lieux(conn)
        logger.info(f"Lieux actifs chargés: {len(lieux)}")

        data_js = build_data_js(lieux)
        labels_js = build_labels_js()
        dept_coords_js = build_dept_coords_js()
        last_update = last_update_date(conn)
        nb, depts, dioceses = compute_stats(lieux)
        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Écrit data.js
        data_path = OUTPUT_DIR / "data.js"
        data_path.write_text(data_js, encoding="utf-8")
        logger.info(f"data.js écrit: {data_path} ({len(data_js)} octets, {nb} lieux)")

        # Écrit index.html
        html = HTML_TEMPLATE
        html = html.replace("{{LABELS_JS}}", labels_js)
        html = html.replace("{{DEPT_COORDS_JS}}", dept_coords_js)
        html = html.replace("{{LAST_UPDATE}}", last_update)
        html = html.replace("{{DEPT_COUNT}}", str(depts))
        html = html.replace("{{DEPT_NAV}}", build_dept_nav(conn))
        html = html.replace("{{GENERATED_AT}}", generated_at)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        HTML_OUTPUT.write_text(html, encoding="utf-8")
        logger.info(f"index.html écrit: {HTML_OUTPUT} ({len(html)} octets)")
        logger.info(f"Stats: {nb} lieux, {depts} départements, {dioceses} diocèses")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())