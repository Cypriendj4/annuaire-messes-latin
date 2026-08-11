"""
Génère les pages SEO secondaires :
- messes-en-latin.html   → les 504 messes tridentines + Paul VI latin
- rites-orientaux.html   → les églises de rites orientaux catholiques
- a-propos.html          → sources, méthodologie, note FSSPX (déplacée du header)
- departements/index.html → index des départements (maillage SEO)

Chaque page reçoit le menu sticky commun (même nav que l'accueil).
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, OUTPUT_DIR, DEPT_COORDS
from utils import setup_logging, slugify

logger = setup_logging("generate_pages")

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


# ── Menu sticky commun (préfixe = "" à la racine, "../" dans departements/) ──
def build_nav(prefix: str = "") -> str:
    """Menu sticky commun. prefix vaut "" à la racine ou "../" dans departements/."""
    return f"""<nav class="main-nav" aria-label="Navigation principale">
  <a href="{prefix}index.html" class="brand">🕯️ Messes en France</a>
  <div class="nav-links">
    <a href="{prefix}messes-en-latin.html">Messes en latin</a>
    <a href="{prefix}rites-orientaux.html">Rites orientaux</a>
    <a href="{prefix}departements/index.html">Départements</a>
    <a href="{prefix}a-propos.html">À propos</a>
  </div>
</nav>"""


PAGE_CSS = """
  :root{--ink:#221f2b;--parchment:#efe7d6;--burgundy:#6d2438;--gold:#a9822f;--slate:#5b5847;--card:#faf6ec;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--parchment);background-image:radial-gradient(rgba(109,36,56,0.05) 1px,transparent 1px);background-size:22px 22px;color:var(--ink);font-family:'Inter',sans-serif;line-height:1.6;}
  .main-nav{position:sticky;top:0;z-index:20;display:flex;justify-content:space-between;align-items:center;gap:1rem;background:var(--parchment);border-bottom:2px solid var(--ink);padding:0.7rem 1.5rem;max-width:1100px;margin:0 auto;}
  .main-nav .brand{font-family:'Fraunces',serif;font-weight:600;color:var(--burgundy);text-decoration:none;font-size:1.05rem;white-space:nowrap;}
  .nav-links{display:flex;gap:0.4rem;flex-wrap:wrap;}
  .nav-links a{font-size:0.8rem;font-weight:600;color:var(--ink);text-decoration:none;padding:0.35rem 0.7rem;border:1px solid var(--ink);background:var(--card);}
  .nav-links a:hover{background:var(--ink);color:var(--parchment);}
  .wrap{max-width:1100px;margin:0 auto;padding:2rem 1.5rem;}
  h1{font-family:'Fraunces',serif;font-weight:600;font-size:clamp(1.7rem,3.2vw,2.4rem);margin:0 0 0.5rem;}
  .eyebrow{font-size:0.72rem;letter-spacing:0.18em;text-transform:uppercase;color:var(--burgundy);font-weight:600;margin-bottom:0.5rem;}
  .subtitle{color:var(--slate);max-width:760px;margin-bottom:1.5rem;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem;}
  .card{background:var(--card);border:1px solid var(--ink);padding:1rem;border-left:6px solid var(--gold);}
  .card.tridentin{border-left-color:var(--burgundy);}
  .card-top{display:flex;justify-content:space-between;gap:0.6rem;}
  .card-ville{font-family:'Fraunces',serif;font-weight:600;font-size:1.15rem;}
  .card-dept{font-size:0.7rem;color:var(--slate);white-space:nowrap;padding-top:0.2rem;}
  .card-lieu{font-size:0.85rem;margin:0.2rem 0;}
  .card-adresse{font-size:0.78rem;color:var(--slate);}
  .tags{margin:0.5rem 0;}
  .tag{font-size:0.68rem;font-weight:600;padding:0.2rem 0.5rem;border-radius:20px;border:1px solid var(--ink);margin-right:0.3rem;display:inline-block;}
  .tag.rite-t{background:var(--burgundy);color:#fff;border-color:var(--burgundy);}
  .tag.rite-p{background:var(--gold);color:#221f2b;border-color:var(--gold);}
  .tag.rite-o{background:#3a5a40;color:#fff;border-color:#3a5a40;}
  .card-detail{font-size:0.8rem;border-top:1px dashed var(--ink);padding-top:0.5rem;margin-top:0.5rem;}
  .card-detail .label{color:var(--burgundy);font-weight:600;}
  .card-actions{margin-top:0.6rem;}
  .messes-btn{font-size:0.7rem;font-weight:600;background:var(--burgundy);color:#fff;border:1px solid var(--burgundy);padding:0.28rem 0.55rem;border-radius:20px;text-decoration:none;display:inline-block;}
  .messes-btn.site{background:#3a5a40;border-color:#3a5a40;}
  .tel-link{font-size:0.72rem;font-weight:600;color:var(--ink);border:1px solid var(--ink);background:#fff;padding:0.28rem 0.55rem;border-radius:20px;text-decoration:none;display:inline-block;margin-left:0.3rem;}
  .back{display:inline-block;margin-bottom:1.2rem;color:var(--burgundy);font-weight:600;text-decoration:none;font-size:0.85rem;}
  .prose{background:var(--card);border:1px solid var(--ink);padding:1.5rem;max-width:760px;}
  .prose h2{font-family:'Fraunces',serif;font-size:1.3rem;margin:1.5rem 0 0.5rem;}
  .prose h2:first-child{margin-top:0;}
  .prose p,.prose li{font-size:0.92rem;color:var(--slate);}
  .prose li{margin-bottom:0.3rem;}
  .dept-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:0.4rem;list-style:none;padding:0;}
  .dept-list a{color:var(--burgundy);text-decoration:none;font-size:0.85rem;border-bottom:1px solid var(--line,#ddd);padding:0.3rem 0.2rem;display:block;}
  .dept-list a:hover{background:var(--card);text-decoration:underline;}
  footer{margin-top:3rem;border-top:1px solid var(--ink);padding-top:1rem;font-size:0.78rem;color:var(--slate);}
  footer a{color:var(--burgundy);}
  @media (max-width:640px){.main-nav{flex-direction:column;align-items:flex-start;}.nav-links{width:100%;}}
"""


def page_shell(title: str, desc: str, body: str, prefix: str = "", last_update: str = "",
               canonical: str = "") -> str:
    """Enveloppe HTML commune avec menu sticky + footer."""
    if not canonical:
        canonical = "https://cypriendj4.github.io/annuaire-messes-latin/" + canonical
    footer = f"""
<footer>
  Annuaire des messes en France — données sources : messes.info (CEF), AMDG, La Porte Latine.
  {f'Dernière mise à jour : {last_update}.' if last_update else ''}
  <a href="{prefix}a-propos.html">À propos et sources</a>
</footer>"""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>{PAGE_CSS}</style>
</head>
<body>
{build_nav(prefix)}
<div class="wrap">
  {body}
</div>
{footer}
</body>
</html>"""


# ── Pages ──────────────────────────────────────────────────────────────
def build_messes_latin(conn, last_update) -> str:
    cur = conn.cursor()
    cur.execute("""
        SELECT ville, dept_code, dept_nom, diocese, lieu, adresse, rite, langue,
               communaute, celebrant, horaires, contact, url_detail
        FROM lieux WHERE actif=1 AND rite IN ('tridentin','paulvi') AND langue='latin'
        ORDER BY dept_code, ville
    """)
    lieux = cur.fetchall()
    nb = len(lieux)
    nb_trid = sum(1 for l in lieux if l[6] == 'tridentin')
    nb_paul = nb - nb_trid

    cards = ""
    for l in lieux:
        ville, dc, dn, dioc, lieu, adr, rite, lang, comm, cel, hor, tel, url = l
        dept = f"{dc} – {dn}" if dn else dc
        rite_tag = "Tridentin · 1962" if rite == 'tridentin' else "Paul VI · Latin"
        hor_html = f'<div class="row"><span class="label">Horaires</span> — {hor}</div>' if hor and "voir site" not in hor.lower() else ""
        cel_html = f'<div class="row"><span class="label">Célébrant</span> — {cel[:120]}</div>' if cel else ""
        # Téléphone : premier numéro du contact
        tel_link = ""
        if tel:
            m_tel = re.search(r'(\b0\d(?:\s?\d){8}\b)', tel)
            if m_tel:
                num = re.sub(r'\s+', '', m_tel.group(1))
                tel_link = f'<a class="tel-link" href="tel:{num}">📞 {m_tel.group(1)}</a>'
        # Site web du lieu (extrait du contact "Site : https://...")
        site_link = ""
        m_site = re.search(r'https?://[^\s\)]+', tel or "")
        if m_site:
            site_link = f'<a class="messes-btn site" href="{m_site.group(0)}" target="_blank" rel="noopener">🌐 Site du lieu</a>'
        # Lien horaires à jour : messes.info si dispo, sinon source AMDG / Porte Latine
        url_html = f'<a class="messes-btn" href="{url}" target="_blank" rel="noopener">Horaires sur messes.info</a>' if url else ""
        if not url and site_link:
            url_html = site_link
        if not url and not site_link:
            src_label = "Voir la source (AMDG)" if hor or tel else ""
            if src_label:
                url_html = f'<a class="messes-btn site" href="https://www.amdg.asso.fr/" target="_blank" rel="noopener">{src_label}</a>'
        # Communauté
        comm_tag = f'<span class="tag">{comm}</span>' if comm else ""
        cards += f"""
    <article class="card {rite}" itemscope itemtype="https://schema.org/Church">
      <div class="card-top">
        <div class="card-ville" itemprop="name">{ville}</div>
        <div class="card-dept">{dept}</div>
      </div>
      <div class="card-lieu">{lieu}</div>
      {f'<div class="card-adresse">{adr}</div>' if adr else ''}
      <div class="tags"><span class="tag {'rite-t' if rite=='tridentin' else 'rite-p'}">{rite_tag}</span>{comm_tag}<span class="tag">{dioc or ''}</span></div>
      {f'<div class="card-detail">{hor_html}{cel_html}</div>' if (hor or cel) else ''}
      <div class="card-actions">{url_html}{tel_link}</div>
    </article>"""

    body = f"""
    <a class="back" href="index.html">← Retour à l'annuaire interactif</a>
    <div class="eyebrow">Rite · France</div>
    <h1>Messes en latin en France</h1>
    <p class="subtitle">{nb} lieux de célébration en latin : <strong>{nb_trid} messes tridentines</strong> (forme extraordinaire, missel 1962) et <strong>{nb_paul} messe Paul VI en latin</strong>. Filtrez et localisez chaque lieu sur l'annuaire interactif.</p>
    <div class="grid">{cards}
    </div>"""
    return page_shell(
        f"Messes en latin en France : {nb_trid} messes tridentines & Paul VI latin — Annuaire",
        f"Annuaire des {nb} messes en latin en France : rite tridentin (missel 1962) et Paul VI en latin, par ville et département. Horaires et contacts.",
        body, last_update=last_update,
        canonical="messes-en-latin.html")


def build_rites_orientaux(conn, last_update) -> str:
    cur = conn.cursor()
    cur.execute("""
        SELECT ville, dept_code, dept_nom, lieu, adresse, communaute, url_detail
        FROM lieux WHERE actif=1 AND rite='oriental' ORDER BY dept_code, ville
    """)
    lieux = cur.fetchall()
    nb = len(lieux)
    cards = ""
    for l in lieux:
        ville, dc, dn, lieu, adr, comm, url = l
        dept = f"{dc} – {dn}" if dn else dc
        url_html = f'<a class="messes-btn" href="{url}" target="_blank" rel="noopener">Horaires sur messes.info</a>' if url else ""
        cards += f"""
    <article class="card">
      <div class="card-top">
        <div class="card-ville">{ville}</div>
        <div class="card-dept">{dept}</div>
      </div>
      <div class="card-lieu">{lieu}</div>
      {f'<div class="card-adresse">{adr}</div>' if adr else ''}
      <div class="tags"><span class="tag rite-o">Rite oriental</span></div>
      <div class="card-actions">{url_html}</div>
    </article>"""

    body = f"""
    <a class="back" href="index.html">← Retour à l'annuaire interactif</a>
    <div class="eyebrow">Rites orientaux catholiques · France</div>
    <h1>Les églises de rites orientaux catholiques en France</h1>
    <p class="subtitle">{nb} lieux de culte de rites orientaux catholiques recensés en France : byzantin, syriaque, maronite, chaldéen, arménien… Ils sont en pleine communion avec Rome mais suivent leurs traditions liturgiques propres.</p>
    <div class="grid">{cards}
    </div>"""
    return page_shell(
        f"Églises de rites orientaux catholiques en France ({nb} lieux) — Annuaire",
        f"Les {nb} églises de rites orientaux catholiques en France : byzantin, maronite, syriaque, chaldéen, arménien. Adresses et horaires.",
        body, last_update=last_update,
        canonical="rites-orientaux.html")


def build_a_propos(conn, last_update) -> str:
    body = """
    <a class="back" href="index.html">← Retour à l'annuaire interactif</a>
    <div class="eyebrow">À propos</div>
    <h1>À propos de cet annuaire</h1>
    <div class="prose">
      <h2>Sources des données</h2>
      <ul>
        <li><strong>messes.info</strong> (Conférence des Évêques de France) — annuaire national des églises, avec adresses et coordonnées GPS.</li>
        <li><strong>AMDG</strong> (amdg.asso.fr) — messes tridentines (forme extraordinaire), mise à jour hebdomadaire.</li>
        <li><strong>La Porte Latine</strong> (laportelatine.org/lieux) — lieux desservis par la FSSPX et communautés amies.</li>
      </ul>
      <p>Liste <strong>non exhaustive</strong>, mise à jour automatiquement. Pour chaque lieu, un lien « Horaires sur messes.info » donne les célébrations à jour.</p>

      <h2>⚠️ Vérifiez toujours les horaires</h2>
      <p>Les horaires changent en été, à Noël, à Pâques, et évoluent au fil des affectations de prêtres. Confirmez toujours avant de vous déplacer.</p>

      <h2>Note sur la FSSPX</h2>
      <p>La Fraternité Sacerdotale Saint-Pie X et les « communautés amies » qui lui sont proches ne sont pas en pleine communion canonique avec Rome — à la différence de FSSP, ICRSP, IBP et des prêtres diocésains listés ailleurs sur ce site. Cet annuaire les signale toutes les deux pour être exhaustif sur l'offre de messes, sans prendre position.</p>

      <h2>Comment sont classés les lieux ?</h2>
      <ul>
        <li><strong>Tridentin</strong> — forme extraordinaire du rite romain (missel 1962), toujours en latin.</li>
        <li><strong>Paul VI en latin</strong> — forme ordinaire (missel 1969/1970) célébrée en latin.</li>
        <li><strong>Paul VI en français</strong> — forme ordinaire célébrée en français (la grande majorité des paroisses).</li>
        <li><strong>Rites orientaux catholiques</strong> — byzantin, maronite, syriaque, chaldéen, arménien, etc.</li>
      </ul>

      <h2>Une erreur, un lieu manquant ?</h2>
      <p>Écrivez-nous à <a href="mailto:contact@exemple.fr?subject=Correction%20annuaire%20messes">contact@exemple.fr</a> — chaque correction est intégrée à la prochaine mise à jour automatique.</p>
    </div>"""
    return page_shell(
        "À propos et sources — Annuaire des messes en France",
        "Sources des données de l'annuaire des messes en France : messes.info (CEF), AMDG, La Porte Latine. Méthodologie, note FSSPX, contact.",
        body, last_update=last_update,
        canonical="a-propos.html")


def build_dept_index(conn, last_update) -> str:
    cur = conn.cursor()
    cur.execute("""
        SELECT dept_code, COUNT(*) FROM lieux
        WHERE actif=1 AND dept_code != '' GROUP BY dept_code ORDER BY dept_code
    """)
    rows = cur.fetchall()
    items = []
    for code, count in rows:
        nom = DEPT_NAMES.get(code, code)
        slug = slugify(nom)
        items.append(f'<li><a href="{code}-{slug}/">{code} · {nom} <small>({count} lieux)</small></a></li>')
    body = f"""
    <a class="back" href="../index.html">← Retour à l'annuaire interactif</a>
    <div class="eyebrow">Navigation · Départements</div>
    <h1>Tous les départements de France</h1>
    <p class="subtitle">{len(rows)} départements couverts. Choisissez une page pour voir la liste complète des églises et messes de votre département.</p>
    <ul class="dept-list">{''.join(items)}</ul>"""
    return page_shell(
        "Messes par département — les 101 départements de France",
        "Accédez aux pages départementales : liste des églises catholiques et messes pour chaque département de France métropolitaine et d'outre-mer.",
        body, prefix="../", last_update=last_update,
        canonical="departements/index.html")


def update_sitemap(extra_pages: list[str]) -> None:
    """Ajoute les pages secondaires au sitemap existant."""
    base = "https://cypriendj4.github.io/annuaire-messes-latin"
    sitemap_path = OUTPUT_DIR / "sitemap.xml"
    if not sitemap_path.exists():
        return
    xml = sitemap_path.read_text(encoding="utf-8")
    additions = []
    for page in extra_pages:
        loc = f"{base}/{page}"
        if loc not in xml:
            additions.append(f'<url><loc>{loc}</loc></url>')
    if additions:
        xml = xml.replace("</urlset>", "\n".join(additions) + "\n</urlset>")
        sitemap_path.write_text(xml, encoding="utf-8")
        logger.info(f"Sitemap enrichi: +{len(additions)} URLs")


def main() -> int:
    if not DB_PATH.exists():
        logger.error("Base absente")
        return 1
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(derniere_maj) FROM lieux")
        row = cur.fetchone()
        last_update = (row[0][:10] if row and row[0] else datetime.now().strftime("%d/%m/%Y"))
        last_update = last_update.replace("-", "/")

        (OUTPUT_DIR / "messes-en-latin.html").write_text(build_messes_latin(conn, last_update), encoding="utf-8")
        (OUTPUT_DIR / "rites-orientaux.html").write_text(build_rites_orientaux(conn, last_update), encoding="utf-8")
        (OUTPUT_DIR / "a-propos.html").write_text(build_a_propos(conn, last_update), encoding="utf-8")
        dept_dir = OUTPUT_DIR / "departements"
        dept_dir.mkdir(parents=True, exist_ok=True)
        (dept_dir / "index.html").write_text(build_dept_index(conn, last_update), encoding="utf-8")

        update_sitemap(["messes-en-latin.html", "rites-orientaux.html", "a-propos.html",
                        "departements/index.html"])
        logger.info("Pages secondaires générées")
        print("PAGES_OK")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
