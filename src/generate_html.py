"""
Génère le fichier index.html à partir de la base SQLite.
Préserve le design original (palette, polices, layout) et injecte les données
dans le tableau DATA JavaScript.

Le template HTML est identique à l'original, avec :
- les données injectées depuis SQLite
- la date de dernière mise à jour dynamique
- la source affichée pour chaque lieu
- les 4 communautés manquantes ajoutées au mapping
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
               langue, communaute, celebrant, horaires, contact,
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
            "diocese": row[3],
            "lieu": row[4],
            "adresse": row[5] or "",
            "rite": row[6],
            "langue": row[7],
            "communaute": row[8],
            "celebrant": row[9] or "",
            "horaires": row[10] or "",
            "contact": row[11] or "",
            "source": row[12],
            "coord_lat": row[13],
            "coord_lon": row[14],
        })
    return lieux


def build_data_js(lieux: list[dict]) -> str:
    """Construit le tableau DATA JavaScript (format identique à l'original)."""
    lines = []
    for l in lieux:
        def esc(v: str) -> str:
            return json.dumps(v, ensure_ascii=False)
        lines.append(
            '{ville:' + esc(l['ville']) +
            ',dept:' + esc(l['dept']) +
            ',diocese:' + esc(l['diocese']) +
            ',lieu:' + esc(l['lieu']) +
            ',adresse:' + esc(l['adresse']) +
            ',rite:' + esc(l['rite']) +
            ',langue:' + esc(l['langue']) +
            ',communaute:' + esc(l['communaute']) +
            ',celebrant:' + esc(l['celebrant']) +
            ',horaires:' + esc(l['horaires']) +
            ',contact:' + esc(l['contact']) +
            ',source:' + esc(l['source']) +
            '},'
        )
    return '\n'.join(lines)


def build_labels_js() -> str:
    """Construit le mapping communeLabels (complété des 4 communautés manquantes)."""
    lines = []
    for code, label in COMMUNE_LABELS.items():
        lines.append(f'  {json.dumps(code, ensure_ascii=False)}: {json.dumps(label, ensure_ascii=False)}')
    return '{\n' + ',\n'.join(lines) + '\n}'


def build_dept_coords_js() -> str:
    """Construit le mapping DEPT_COORDS (centroïdes départements)."""
    lines = []
    for code, (lat, lon) in sorted(DEPT_COORDS.items()):
        lines.append(f'  "{code}":[{lat:.4f},{lon:.4f}]')
    return '{\n' + ',\n'.join(lines) + '\n}'


def last_update_date(conn: sqlite3.Connection) -> str:
    """Retourne la date de dernière mise à jour (du log ou des lieux)."""
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM maj_log")
    row = cur.fetchone()
    if row and row[0]:
        try:
            dt = datetime.fromisoformat(row[0])
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    cur.execute("SELECT MAX(derniere_maj) FROM lieux")
    row = cur.fetchone()
    if row and row[0]:
        try:
            dt = datetime.fromisoformat(row[0])
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return datetime.now().strftime("%d/%m/%Y")


def compute_dioceses(lieux: list[dict]) -> int:
    """Nombre de diocèses distincts (pour le trust-bar)."""
    return len({l["diocese"] for l in lieux if l["diocese"]})


# ── Template HTML ──────────────────────────────────────────────────────
# Le template reprend exactement le design original (voir fichier source).
# Les parties dynamiques sont remplacées par des placeholders :
#   {{DATA_JS}}, {{LABELS_JS}}, {{DEPT_COORDS_JS}}, {{TRUST_COUNT}},
#   {{DIOCESE_COUNT}}, {{LAST_UPDATE}}
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Messe en latin près de chez vous : rite tridentin &amp; Paul VI — Annuaire France</title>
<meta name="description" content="Trouvez une messe traditionnelle (rite tridentin, missel 1962) ou une messe Paul VI en latin près de chez vous. Filtrez par diocèse, communauté (FSSP, ICRSP, IBP, FSSPX…) et langue. Horaires vérifiés, sources citées.">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#6d2438">

<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="Messes traditionnelles en France">
<meta property="og:title" content="Messe en latin près de chez vous : rite tridentin &amp; Paul VI">
<meta property="og:description" content="Annuaire filtrable des messes en latin en France — rite, langue, diocèse, communauté. Horaires vérifiés, sources citées.">
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
    max-width:640px;
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

  /* ---------- filters ---------- */
  .filters-wrap{
    max-width:1100px;
    margin:0 auto;
    padding:1.4rem 1.5rem 0;
    position:sticky;
    top:0;
    z-index:10;
    background:var(--parchment);
  }
  .filters{
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
    margin-top:0.5rem;
  }
  .share-btn{
    font-family:'Inter',sans-serif;
    font-size:0.7rem;
    font-weight:600;
    background:none;
    border:1px solid var(--ink);
    padding:0.28rem 0.55rem;
    cursor:pointer;
    color:var(--ink);
    border-radius:20px;
  }
  .share-btn:hover{background:var(--ink); color:var(--parchment);}
  .card-distance{
    font-family:'Inter',sans-serif;
    font-size:0.68rem;
    font-weight:600;
    color:var(--burgundy);
    white-space:nowrap;
  }

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
  "name":"Messes traditionnelles en France",
  "description":"Annuaire filtrable des messes en latin en France : rite tridentin (1962) et Paul VI, par diocèse, langue et communauté.",
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
      "name":"Qu'est-ce que la messe tridentine ?",
      "acceptedAnswer":{"@type":"Answer","text":"La messe tridentine, ou forme extraordinaire du rite romain, est célébrée selon le missel romain de 1962, en latin. Elle a été confirmée comme légitime par le motu proprio Summorum Pontificum de Benoît XVI en 2007, avec des conditions révisées depuis par Traditionis Custodes (2021)."}
    },
    {
      "@type":"Question",
      "name":"Quelle différence entre le rite tridentin et une messe Paul VI en latin ?",
      "acceptedAnswer":{"@type":"Answer","text":"Le rite tridentin suit le missel de 1962. La messe Paul VI, elle, suit le missel de 1969/1970 issu du concile Vatican II (forme ordinaire) : elle peut être célébrée en français ou en latin selon les paroisses, avec la même structure liturgique que la messe habituelle."}
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

<nav class="breadcrumb" aria-label="Fil d'Ariane">
  <a href="#">Accueil</a> › <span aria-current="page">Messes traditionnelles en France</span>
</nav>

<header>
  <div class="eyebrow">Annuaire liturgique · France</div>
  <h1>Messe en latin <em>près de chez vous</em></h1>
  <p class="subtitle">Rite tridentin (missel 1962) et messe Paul VI en latin — filtrez par diocèse, langue et communauté célébrante.</p>

  <div class="trust-bar">
    <div><b id="trustCount">—</b> lieux référencés</div>
    <div><b>{{DIOCESE_COUNT}}</b> diocèses couverts</div>
    <div><b>{{LAST_UPDATE}}</b> dernière mise à jour des sources</div>
  </div>

  <div class="cta-row">
    <button class="btn-primary" id="geoBtn">📍 Trouver la messe la plus proche de moi</button>
    <span id="geoStatus"></span>
  </div>

  <div class="source-note">
    <strong>Sources des données :</strong> AMDG (amdg.asso.fr, mise à jour hebdomadaire),
    La Porte Latine (laportelatine.org/lieux, lieux desservis par la FSSPX et communautés amies),
    trouverunemesse.fr / horairesmesses.com (agrégateurs croisés avec messes.info pour vérifier les messes Paul VI en latin).
    Liste <strong>non exhaustive</strong>, mise à jour automatiquement chaque jour.
    <strong>Vérifiez toujours les horaires avant de vous déplacer</strong> — ils changent en été, à Noël, à Pâques.<br><br>
    <strong>Note sur la FSSPX :</strong> la Fraternité Sacerdotale Saint-Pie X et les « communautés amies » qui lui
    sont proches ne sont pas en pleine communion canonique avec Rome — à la différence de FSSP, ICRSP, IBP et des prêtres diocésains
    listés ailleurs sur cette page. Ce site les signale toutes les deux pour être exhaustif sur l'offre de messes en latin, sans prendre position.
  </div>
</header>

<div class="filters-wrap">
  <div class="filters">
    <div class="field" style="grid-column:1/-1;">
      <label for="q">Recherche (ville, lieu, célébrant)</label>
      <input type="text" id="q" placeholder="Ex. Toulouse, Saint-Eugène, ICRSP…">
    </div>

    <div class="field">
      <label>Rite</label>
      <div class="rite-toggle" id="riteToggle">
        <button data-val="all" class="active">Tous</button>
        <button data-val="tridentin">Tridentin</button>
        <button data-val="paulvi">Paul VI</button>
      </div>
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
  <div class="empty" id="emptyState" style="display:none;">Aucun lieu ne correspond à ces filtres.</div>
</main>

<section class="faq" aria-labelledby="faqTitle">
  <h2 id="faqTitle">Questions fréquentes</h2>
  <details>
    <summary>Qu'est-ce que la messe tridentine ?</summary>
    <p>La messe tridentine, ou forme extraordinaire du rite romain, est célébrée selon le missel romain de 1962, en latin. Elle a été confirmée comme légitime par le motu proprio Summorum Pontificum de Benoît XVI en 2007, avec des conditions révisées depuis par Traditionis Custodes (2021).</p>
  </details>
  <details>
    <summary>Quelle différence entre le rite tridentin et une messe Paul VI en latin ?</summary>
    <p>Le rite tridentin suit le missel de 1962. La messe Paul VI suit le missel de 1969/1970 issu du concile Vatican II (forme ordinaire) : elle peut être célébrée en français ou en latin selon les paroisses, avec la même structure liturgique que la messe habituelle.</p>
  </details>
  <details>
    <summary>Quelle est la différence entre FSSP, ICRSP, IBP et FSSPX ?</summary>
    <p>FSSP, ICRSP et IBP sont des instituts de droit pontifical en pleine communion avec Rome, dont les prêtres célèbrent la forme extraordinaire avec l'accord de l'évêque du lieu. La FSSPX n'est pas en pleine communion canonique avec Rome ; ses lieux sont signalés séparément sur cet annuaire, sans prise de position.</p>
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
  <strong>Diocèse</strong> : prêtre incardiné dans le diocèse, hors institut ou fraternité dédiée ·
  <strong>FSSPX</strong> : Fraternité Sacerdotale Saint-Pie X (hors pleine communion canonique — voir note en en-tête) ·
  <strong>Fraternité de la Transfiguration</strong>, <strong>Capucins de Morgon</strong>,
  <strong>Dominicaines contemplatives</strong> : communautés proches de la FSSPX.
</footer>

<script>
// ---------------------------------------------------------------
// Données générées automatiquement depuis la base SQLite
// Dernière génération : {{GENERATED_AT}}
// ---------------------------------------------------------------
const DATA = [
{{DATA_JS}}
];

// ---------------------------------------------------------------
// Mapping communautés → labels complets
// ---------------------------------------------------------------
const communeLabels = {{LABELS_JS}};

// Centroïdes approximatifs des préfectures de département — utilisés
// uniquement pour un tri "par proximité" indicatif.
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
      status.textContent="Trié par proximité (approximatif, au niveau du département).";
      btn.disabled=false;
      render();
      document.getElementById('grid').scrollIntoView({behavior:'smooth', block:'start'});
    },
    err=>{
      status.textContent="Localisation refusée ou indisponible — utilisez plutôt les filtres.";
      btn.disabled=false;
    },
    {timeout:8000}
  );
}

let state = {rite:"all", langue:"all", diocese:"all", communaute:"all", q:""};

function uniqueSorted(arr){return [...new Set(arr)].sort((a,b)=>a.localeCompare(b,'fr'));}

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
  uniqueSorted(DATA.map(d=>d.diocese)).forEach(d=>{
    const o=document.createElement('option'); o.value=d; o.textContent=d; dioceseSel.appendChild(o);
  });
  const commSel = document.getElementById('communaute');
  uniqueSorted(DATA.map(d=>d.communaute)).forEach(c=>{
    const o=document.createElement('option'); o.value=c; o.textContent=communeLabels[c]||c; commSel.appendChild(o);
  });
}

function buildLegend(){
  const legend=document.getElementById('legend');
  const counts={};
  DATA.forEach(d=>{counts[d.communaute]=(counts[d.communaute]||0)+1;});
  legend.innerHTML = Object.keys(counts).sort().map(c=>
    `<span><b>${c}</b> · ${counts[c]} lieu${counts[c]>1?'x':''}</span>`
  ).join('');
}

function matches(d){
  if(state.rite!=='all' && d.rite!==state.rite) return false;
  if(state.langue!=='all' && d.langue!==state.langue) return false;
  if(state.diocese!=='all' && d.diocese!==state.diocese) return false;
  if(state.communaute!=='all' && d.communaute!==state.communaute) return false;
  if(state.q){
    const hay = (d.ville+' '+d.lieu+' '+d.celebrant+' '+d.diocese+' '+d.dept).toLowerCase();
    if(!hay.includes(state.q.toLowerCase())) return false;
  }
  return true;
}

function slugify(s){
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'');
}

function render(){
  let results = DATA.filter(matches);

  if(userPos){
    results = results.map(d=>{
      const code = d.dept.split(' ')[0];
      const coord = DEPT_COORDS[code];
      const dist = coord ? haversine(userPos.lat,userPos.lon,coord[0],coord[1]) : null;
      return {...d, _dist:dist};
    }).sort((a,b)=>{
      if(a._dist==null) return 1;
      if(b._dist==null) return -1;
      return a._dist-b._dist;
    });
  } else {
    results = results.sort((a,b)=>a.dept.localeCompare(b.dept,'fr'));
  }

  const grid = document.getElementById('grid');
  const empty = document.getElementById('emptyState');
  document.getElementById('resultCount').innerHTML = `<strong>${results.length}</strong> lieu${results.length>1?'x':''} de culte`;

  if(results.length===0){
    grid.innerHTML='';
    empty.style.display='block';
    return;
  }
  empty.style.display='none';

  grid.innerHTML = results.map(d=>{
    const cardId = slugify(d.ville+'-'+d.lieu);
    return `
    <article class="card ${d.rite}" id="${cardId}" itemscope itemtype="https://schema.org/Church">
      <div class="card-top">
        <div class="card-ville" itemprop="name">${d.ville}</div>
        <div class="card-dept">${d.dept}${d._dist!=null?` · <span class="card-distance">~${Math.round(d._dist)} km</span>`:''}</div>
      </div>
      <div class="card-lieu">${d.lieu}</div>
      ${d.adresse?`<div class="card-adresse" itemprop="address">${d.adresse}</div>`:''}
      <div class="tags">
        <span class="tag ${d.rite==='tridentin'?'rite-t':'rite-p'}">${d.rite==='tridentin'?'Tridentin · 1962':'Paul VI'}</span>
        <span class="tag lang">${d.langue==='latin'?'Latin':'Français'}</span>
        <span class="tag comm">${d.communaute}</span>
        <span class="tag diocese">${d.diocese}</span>
        ${d.source?`<span class="tag src">${d.source}</span>`:''}
      </div>
      <div class="card-detail">
        <div class="row"><span class="label">Horaires</span> — ${d.horaires}</div>
        <div class="row"><span class="label">Célébrant</span> — ${d.celebrant}</div>
        ${d.contact?`<div class="row"><span class="label">Contact</span> — ${d.contact}</div>`:''}
      </div>
      <div class="card-actions">
        <button class="share-btn" data-share="${cardId}">🔗 Copier le lien</button>
      </div>
    </article>
  `;}).join('');

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

document.getElementById('geoBtn').addEventListener('click', locateMe);

document.getElementById('riteToggle').addEventListener('click', e=>{
  const btn = e.target.closest('button');
  if(!btn) return;
  [...btn.parentElement.children].forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  state.rite = btn.dataset.val;
  urlFromState(); render();
});
document.getElementById('langue').addEventListener('change', e=>{state.langue=e.target.value; urlFromState(); render();});
document.getElementById('diocese').addEventListener('change', e=>{state.diocese=e.target.value; urlFromState(); render();});
document.getElementById('communaute').addEventListener('change', e=>{state.communaute=e.target.value; urlFromState(); render();});
document.getElementById('q').addEventListener('input', e=>{state.q=e.target.value; urlFromState(); render();});
document.getElementById('resetBtn').addEventListener('click', ()=>{
  state = {rite:"all", langue:"all", diocese:"all", communaute:"all", q:""};
  userPos = null;
  document.getElementById('geoStatus').textContent='';
  document.getElementById('q').value='';
  document.getElementById('langue').value='all';
  document.getElementById('diocese').value='all';
  document.getElementById('communaute').value='all';
  [...document.getElementById('riteToggle').children].forEach(b=>b.classList.remove('active'));
  document.getElementById('riteToggle').children[0].classList.add('active');
  urlFromState(); render();
});

populateSelects();
buildLegend();
stateFromURL();
document.getElementById('q').value = state.q;
document.getElementById('langue').value = state.langue;
document.getElementById('diocese').value = state.diocese;
document.getElementById('communaute').value = state.communaute;
[...document.getElementById('riteToggle').children].forEach(b=>{
  b.classList.toggle('active', b.dataset.val===state.rite);
});
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
    logger.info("=== Génération index.html ===")
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
        diocese_count = compute_dioceses(lieux)
        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

        html = HTML_TEMPLATE
        html = html.replace("{{DATA_JS}}", data_js)
        html = html.replace("{{LABELS_JS}}", labels_js)
        html = html.replace("{{DEPT_COORDS_JS}}", dept_coords_js)
        html = html.replace("{{LAST_UPDATE}}", last_update)
        html = html.replace("{{DIOCESE_COUNT}}", str(diocese_count))
        html = html.replace("{{GENERATED_AT}}", generated_at)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        HTML_OUTPUT.write_text(html, encoding="utf-8")
        logger.info(f"HTML généré: {HTML_OUTPUT} ({len(html)} octets, {len(lieux)} lieux)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())