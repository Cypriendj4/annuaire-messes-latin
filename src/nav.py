"""
Menu de navigation principal — partagé par tous les générateurs.
Catégories + sous-catégories, SEO-friendly (liens texte), responsive
(hamburger mobile, dropdowns desktop).

Usage :
  from nav import build_nav, NAV_CSS
  # dans <style> : NAV_CSS
  # dans <body> : build_nav(prefix)   (prefix="" à la racine, "../" ailleurs)
"""

# ── Villes majeures (top 12 par nombre de lieux) ───────────────────────
# (dept, slug, label) — slugs vérifiés dans output/villes/
MAJOR_CITIES = [
    ("75", "paris", "Paris"),
    ("69", "lyon", "Lyon"),
    ("13", "marseille", "Marseille"),
    ("31", "toulouse", "Toulouse"),
    ("33", "bordeaux", "Bordeaux"),
    ("06", "nice", "Nice"),
    ("44", "nantes", "Nantes"),
    ("67", "strasbourg", "Strasbourg"),
    ("34", "montpellier", "Montpellier"),
    ("35", "rennes", "Rennes"),
    ("38", "grenoble", "Grenoble"),
    ("83", "toulon", "Toulon"),
]

# ── Départements majeurs (top 12) ──────────────────────────────────────
MAJOR_DEPTS = [
    ("75", "paris", "Paris"),
    ("13", "bouches-du-rhone", "Bouches-du-Rhône"),
    ("69", "rhone", "Rhône"),
    ("31", "haute-garonne", "Haute-Garonne"),
    ("33", "gironde", "Gironde"),
    ("59", "nord", "Nord"),
    ("06", "alpes-maritimes", "Alpes-Maritimes"),
    ("44", "loire-atlantique", "Loire-Atlantique"),
    ("67", "bas-rhin", "Bas-Rhin"),
    ("34", "herault", "Hérault"),
    ("35", "ille-et-vilaine", "Ille-et-Vilaine"),
    ("38", "isere", "Isère"),
]


NAV_CSS = """
  /* ---------- navigation principale sticky (menu) ---------- */
  .main-nav{
    position:sticky; top:0; z-index:30;
    display:flex; justify-content:space-between; align-items:center; gap:1rem;
    background:var(--parchment); border-bottom:2px solid var(--ink);
    padding:0.7rem 1.5rem; max-width:1100px; margin:0 auto;
  }
  .main-nav .brand{
    font-family:'Fraunces',serif; font-weight:600; color:var(--burgundy);
    text-decoration:none; font-size:1.05rem; white-space:nowrap;
  }
  .nav-links{display:flex; gap:0.35rem; flex-wrap:wrap; align-items:center;}
  .nav-links > a, .nav-links .nav-item > button{
    font-size:0.8rem; font-weight:600; color:var(--ink); text-decoration:none;
    padding:0.35rem 0.65rem; border:1px solid var(--ink); background:var(--card);
    cursor:pointer; font-family:'Inter',sans-serif;
  }
  .nav-links > a:hover, .nav-links .nav-item > button:hover,
  .nav-links > a.active{background:var(--ink); color:var(--parchment);}
  .nav-item{position:relative;}
  .nav-item > button{display:flex; align-items:center; gap:0.3rem;}
  .nav-item > button::after{content:"▾"; font-size:0.65rem;}
  .submenu{
    position:absolute; top:100%; left:0; min-width:230px; z-index:40;
    background:var(--card); border:1px solid var(--ink); box-shadow:4px 4px 0 rgba(34,31,43,0.25);
    display:none; padding:0.35rem;
  }
  .nav-item.open .submenu{display:block;}
  .submenu a{
    display:block; font-size:0.78rem; color:var(--ink); text-decoration:none;
    padding:0.4rem 0.6rem; border-bottom:1px dashed var(--line);
  }
  .submenu a:hover{background:var(--parchment); color:var(--burgundy);}
  .submenu a.submenu-all{font-weight:600; color:var(--burgundy); border-bottom:2px solid var(--ink);}
  .nav-toggle{
    display:none; font-size:1.2rem; line-height:1; padding:0.3rem 0.6rem;
    background:var(--card); border:1px solid var(--ink); cursor:pointer; color:var(--ink);
  }
  /* ---------- responsive mobile ---------- */
  @media (max-width:800px){
    .nav-toggle{display:block;}
    .main-nav{flex-wrap:wrap; padding:0.6rem 1rem;}
    .nav-links{
      display:none; width:100%; flex-direction:column; gap:0.25rem;
      border-top:1px solid var(--line); padding-top:0.5rem; margin-top:0.3rem;
    }
    .nav-links.open{display:flex;}
    .nav-links > a, .nav-links .nav-item > button{width:100%; text-align:left;}
    .nav-item{width:100%;}
    .submenu{position:static; box-shadow:none; width:100%; margin-left:0.8rem; border-left:2px solid var(--line);}
    .nav-item > button::after{content:"+"; margin-left:auto;}
    .nav-item.open > button::after{content:"–";}
  }
"""


def build_nav(prefix: str = "") -> str:
    """Retourne le <nav> complet avec catégories et sous-catégories."""
    cities_links = "\n".join(
        f'      <a href="{prefix}villes/{dc}-{slug}/">{label}</a>'
        for dc, slug, label in MAJOR_CITIES
    )
    depts_links = "\n".join(
        f'      <a href="{prefix}departements/{dc}-{slug}/">{label}</a>'
        for dc, slug, label in MAJOR_DEPTS
    )
    html = """<nav class="main-nav" aria-label="Navigation principale">
  <a href="{prefix}index.html" class="brand">🕯️ Messes en France</a>
  <button class="nav-toggle" id="navToggle" aria-label="Ouvrir le menu" aria-expanded="false">☰</button>
  <div class="nav-links" id="navLinks">
    <a href="{prefix}index.html">Accueil</a>

    <div class="nav-item">
      <button type="button">Messes en latin</button>
      <div class="submenu">
        <a class="submenu-all" href="{prefix}messes-en-latin.html">Toutes les messes en latin</a>
        <a href="{prefix}rites-orientaux.html">Rites orientaux catholiques</a>
      </div>
    </div>

    <div class="nav-item">
      <button type="button">Par département</button>
      <div class="submenu">
        <a class="submenu-all" href="{prefix}departements/index.html">Tous les départements (101)</a>
{depts_links}
      </div>
    </div>

    <div class="nav-item">
      <button type="button">Par ville</button>
      <div class="submenu">
        <a class="submenu-all" href="{prefix}villes/index.html">Toutes les villes</a>
{cities_links}
      </div>
    </div>

    <a href="{prefix}a-propos.html">À propos</a>
  </div>
</nav>""".format(prefix=prefix, depts_links=depts_links, cities_links=cities_links)
    return html + NAV_SCRIPT


# Script du menu (constante non-f-string : accolades JS simples)
NAV_SCRIPT = """
<script>
(function(){
  const toggle = document.getElementById('navToggle');
  const links = document.getElementById('navLinks');
  if(!toggle || !links) return;
  toggle.addEventListener('click', ()=>{
    const open = links.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  document.querySelectorAll('.nav-item > button').forEach(btn=>{
    btn.addEventListener('click', e=>{
      e.preventDefault();
      const item = btn.parentElement;
      const wasOpen = item.classList.contains('open');
      document.querySelectorAll('.nav-item.open').forEach(i=>i.classList.remove('open'));
      if(!wasOpen) item.classList.add('open');
    });
  });
  document.addEventListener('click', e=>{
    if(!e.target.closest('.nav-item') && !e.target.closest('.nav-toggle')){
      document.querySelectorAll('.nav-item.open').forEach(i=>i.classList.remove('open'));
    }
  });
})();
</script>"""
