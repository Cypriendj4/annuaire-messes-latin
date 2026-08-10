"""
Configuration centralisée pour l'annuaire des messes en latin.
Toutes les valeurs par défaut ici ; les secrets (tokens) via variables d'environnement.
"""
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "messes.db"
HTML_OUTPUT = OUTPUT_DIR / "index.html"

# ── Sources ────────────────────────────────────────────────────────────
SOURCES = {
    "amdg": {
        "name": "AMDG — Association Ad Majorem Dei Gloriam",
        "base_url": "https://www.amdg.asso.fr",
        "list_url": "https://www.amdg.asso.fr/lieux_messes_spv.htm",
        "encoding": "windows-1252",
        "frequency": "weekly",
        "reliability": 5,
        "parser": "AMDGParser",
        "notes": "Source de référence pour messes tridentin (forme extraordinaire). MAJ chaque vendredi.",
    },
    "portelatine": {
        "name": "La Porte Latine — FSSPX & communautés amies",
        "base_url": "https://laportelatine.org",
        "list_url": "https://laportelatine.org/lieux",
        "encoding": "utf-8",
        "frequency": "dynamic",
        "reliability": 4,
        "parser": "PorteLatineParser",
        "notes": "WordPress + Elementor. CPT 'lieux' paginé. FSSPX + Fraternité Transfiguration, Capucins Morgon, Dominicaines Avrillé.",
    },
    "trouverunemesse": {
        "name": "Trouver une messe (agrégateur messes.info)",
        "base_url": "https://trouverunemesse.com",
        "search_url": "https://trouverunemesse.com/recherche.php",
        "encoding": "utf-8",
        "frequency": "daily",
        "reliability": 3,
        "parser": "TrouverUneMesseParser",
        "notes": "Requêtage par ville. Données dérivées de messes.info. Utile pour Paul VI en latin + vérification croisée.",
    },
    "messes_info": {
        "name": "Messes.info (CEF) — fallback HTML",
        "base_url": "https://messes.info",
        "annuaire_url": "https://messes.info/annuaire/",
        "horaires_url": "https://messes.info/horaires/",
        "encoding": "utf-8",
        "frequency": "daily",
        "reliability": 4,
        "parser": "MessesInfoParser",
        "notes": "GWT inutilisable. Fallback HTML (#htmlversion) exploitable. Donne GPS précis + horaires Paul VI + date MAJ par lieu.",
    },
}

# ── Scraping params ────────────────────────────────────────────────────
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 1.0  # secondes entre requêtes
MAX_RETRIES = 3
CACHE_EXPIRE_DAYS = 1
USER_AGENT = "AnnuaireMessesLatin/1.0 (+https://github.com/tonuser/annuaire-messes-latin; contact@exemple.fr)"

# ── Fuzzy matching ─────────────────────────────────────────────────────
FUZZY_THRESHOLD = 85  # score 0-100 pour considérer deux lieux comme identiques

# ── GitHub Actions / Notifications ─────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ── Communautés / labels UI ────────────────────────────────────────────
COMMUNE_LABELS = {
    "FSSP": "FSSP — Fraternité Sacerdotale Saint-Pierre",
    "ICRSP": "ICRSP — Institut du Christ-Roi Souverain-Prêtre",
    "IBP": "IBP — Institut du Bon Pasteur",
    "FSTB": "FSTB — Fraternité Saint-Thomas-Becket",
    "CRMD": "CRMD — Chanoines Réguliers de la Mère de Dieu",
    "FSVF": "FSVF — Fraternité Saint-Vincent-Ferrier",
    "MMD": "MMD — Missionnaires de la Miséricorde Divine",
    "Bénédictins": "Bénédictins",
    "Diocèse": "Diocèse (clergé diocésain)",
    "FSSPX": "FSSPX — Fraternité Sacerdotale Saint-Pie X",
    "Fraternité de la Transfiguration": "Fraternité de la Transfiguration (proche FSSPX)",
    "Capucins de Morgon": "Capucins de Morgon (proche FSSPX)",
    "Dominicaines contemplatives": "Dominicaines contemplatives d'Avrillé (proche FSSPX)",
}

FSSPX_COMMUNITIES = {
    "FSSPX",
    "Fraternité de la Transfiguration",
    "Capucins de Morgon",
    "Dominicaines contemplatives",
}

# ── Rites & langues (valeurs canoniques) ──────────────────────────────
RITES = ("tridentin", "paulvi")
LANGUES = ("latin", "francais")

# ── Centroïdes départements (pour tri proximité approximatif) ──────────
DEPT_COORDS = {
    "01": (46.2058, 5.2259), "02": (49.5641, 3.6208), "03": (46.5654, 3.3327),
    "04": (44.0919, 6.2356), "05": (44.5594, 6.0819), "06": (43.7102, 7.2620),
    "07": (44.9334, 4.8924), "08": (49.7667, 4.7167), "09": (42.9647, 1.6053),
    "10": (48.2973, 4.0744), "11": (43.2130, 2.3491), "12": (44.3506, 2.5754),
    "13": (43.2965, 5.3698), "14": (49.1829, -0.3707), "15": (44.9282, 2.4441),
    "16": (45.6484, 0.1562), "17": (46.1603, -1.1511), "18": (47.0810, 2.3987),
    "19": (45.2649, 1.7719), "2A": (41.9192, 8.7386), "2B": (42.6886, 9.4478),
    "21": (47.3220, 5.0415), "22": (48.5142, -2.7653), "23": (45.8333, 1.9333),
    "24": (45.1848, 0.7213), "25": (47.2378, 6.0241), "26": (44.9334, 4.8924),
    "27": (49.0270, 1.1510), "28": (48.4439, 1.4894), "29": (47.9960, -4.1023),
    "30": (43.8367, 4.3601), "31": (43.6047, 1.4442), "32": (43.6455, 0.5857),
    "33": (44.8378, -0.5792), "34": (43.6108, 3.8767), "35": (48.1173, -1.6778),
    "36": (46.8107, 1.6911), "37": (47.3941, 0.6848), "38": (45.1885, 5.7245),
    "39": (46.6743, 5.5523), "40": (43.8905, -0.4995), "41": (47.5861, 1.3359),
    "42": (45.4397, 4.3872), "43": (45.0432, 3.8845), "44": (47.2184, -1.5536),
    "45": (47.9029, 1.9093), "46": (44.4479, 1.4353), "47": (44.2049, 0.6212),
    "48": (44.5178, 3.5000), "49": (47.4784, -0.5632), "50": (49.1147, -1.0900),
    "51": (48.9563, 4.3650), "52": (48.1147, 5.3348), "53": (48.0730, -0.7688),
    "54": (48.6921, 6.1844), "55": (48.7706, 5.1614), "56": (47.6582, -2.7603),
    "57": (49.1193, 6.1757), "58": (46.9897, 3.1590), "59": (50.6292, 3.0573),
    "60": (49.4295, 2.0808), "61": (48.4322, 0.0913), "62": (50.2926, 2.7773),
    "63": (45.7772, 3.0870), "64": (43.2951, -0.3708), "65": (43.2327, 0.0781),
    "66": (42.6886, 2.8948), "67": (48.5734, 7.7521), "68": (47.7500, 7.3333),
    "69": (45.7640, 4.8357), "70": (47.6379, 6.1563), "71": (46.7833, 4.8500),
    "72": (48.0061, 0.1996), "73": (45.5646, 5.9178), "74": (45.8992, 6.1294),
    "75": (48.8566, 2.3522), "76": (49.4432, 1.0993), "77": (48.5582, 2.6984),
    "78": (48.8049, 2.1204), "79": (46.3238, -0.4577), "80": (49.8941, 2.2957),
    "81": (43.9289, 2.1457), "82": (44.0167, 1.3500), "83": (43.1242, 5.9280),
    "84": (43.9493, 4.8055), "85": (46.6667, -1.4167), "86": (46.5833, 0.3333),
    "87": (45.8333, 1.2500), "88": (48.1703, 6.4493), "89": (47.7955, 3.5694),
    "90": (47.6386, 6.8634), "91": (48.6815, 2.3356), "92": (48.8333, 2.2500),
    "93": (48.9167, 2.4167), "94": (48.7969, 2.3820), "95": (49.0142, 2.0808),
    "971": (16.2383, -61.5344), "972": (14.6415, -61.0242), "973": (4.9333, -52.3300),
    "974": (-20.8807, 55.4500), "976": (-12.7823, 45.2278),
}

# ── Ville principales pour requêtage trouverunemesse ───────────────────
VILLES_PRINCIPALES = [
    "Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Montpellier",
    "Strasbourg", "Bordeaux", "Lille", "Rennes", "Reims", "Le Havre", "Saint-Étienne",
    "Toulon", "Grenoble", "Dijon", "Angers", "Nîmes", "Villeurbanne", "Le Mans",
    "Aix-en-Provence", "Clermont-Ferrand", "Brest", "Limoges", "Tours", "Amiens",
    "Metz", "Perpignan", "Besançon", "Boulogne-Billancourt", "Orléans", "Mulhouse",
    "Rouen", "Caen", "Nancy", "Saint-Denis", "Argenteuil", "Roubaix", "Tourcoing",
    "Montreuil", "Avignon", "Nanterre", "Vitry-sur-Seine", "Créteil", "Dunkerque",
    "Poitiers", "Asnières-sur-Seine", "Colombes", "Versailles", "Courbevoie",
    "Fort-de-France", "Cayenne", "Saint-Denis (974)", "Saint-Paul", "Mamoudzou",
    "Ajaccio", "Bastia", "Calais", "Arras", "Douai", "Valenciennes", "Lens",
    "Béthune", "Cambrai", "Maubeuge", "Saint-Quentin", "Laon", "Soissons",
    "Château-Thierry", "Meaux", "Melun", "Fontainebleau", "Provins", "Sens",
    "Auxerre", "Nevers", "Bourges", "Vierzon", "Châteauroux", "Issoudun",
    "Le Blanc", "Guéret", "Aubusson", "Tulle", "Brive-la-Gaillarde", "Ussel",
    "Périgueux", "Bergerac", "Sarlat", "Nontron", "Ribérac", "Mont-de-Marsan",
    "Dax", "Agen", "Villeneuve-sur-Lot", "Marmande", "Nérac", "Cahors",
    "Figeac", "Gourdon", "Montauban", "Castelsarrasin", "Moissac", "Albi",
    "Castres", "Lavaur", "Gaillac", "Rodez", "Villefranche-de-Rouergue",
    "Millau", "Saint-Affrique", "Mende", "Florac", "Le Puy-en-Velay", "Brioude",
    "Yssingeaux", "Privas", "Aubenas", "Annonay", "Tournon-sur-Rhône",
    "Valence", "Die", "Nyons", "Gap", "Briançon", "Barcelonnette", "Digne-les-Bains",
    "Sisteron", "Forcalquier", "Manosque", "Draguignan", "Brignoles", "Toulon",
    "Hyères", "Saint-Raphaël", "Fréjus", "Cannes", "Antibes", "Grasse",
    "Cagnes-sur-Mer", "Vence", "Menton", "Nice", "Villefranche-sur-Mer",
    "Beausoleil", "Monaco",
]