# 🕯️ Annuaire des Messes en France

Annuaire autonome, gratuit et auto-maintenu des **églises catholiques et messes en France** :
toutes les paroisses (messes.info / CEF), les messes en latin (rite tridentin 1962 & Paul VI) et les lieux FSSPX.

**Site :** `https://[ton-utilisateur].github.io/[nom-du-repo]/`  
**Mise à jour :** quotidienne (messes en latin) + hebdomadaire (annuaire national CEF)

---

## ✨ Fonctionnalités

- **45 000+ églises** de France (annuaire national messes.info/CEF) avec **GPS précis**
- **380+ messes en latin** référencées (tridentin + Paul VI) avec horaires détaillés
- **Filtres** : rite (tridentin/Paul VI), langue, diocèse, communauté, recherche ville/CP
- **Géolocalisation** : tri par proximité (GPS précis pour la quasi-totalité des lieux)
- **Lien « Horaires sur messes.info »** sur chaque carte pour les célébrations à jour
- **Sources citées** sur chaque carte (CEF, AMDG, La Porte Latine)
- **SEO** : JSON-LD, meta description, HTML sémantique, responsive

## 🏗️ Architecture

```
/
├── .github/workflows/update-annuaire.yml   # Workflow GitHub Actions (daily 3h UTC)
├── src/
│   ├── config.py           # Configuration centralisée (URLs, sélecteurs, seuils)
│   ├── create_db.py        # Création base SQLite + import données initiales
│   ├── scraper.py          # Parseurs modulaires (AMDG, Porte Latine, messes.info, trouverunemesse)
│   ├── update_manager.py   # Fusion, déduplication, désactivation, notifications
│   ├── generate_html.py    # Génération index.html (design original préservé)
│   └── utils.py            # Logging, fuzzy matching, géocodage, helpers
├── data/messes.db          # Base SQLite (commitée pour persistance)
├── output/index.html       # Site généré (servi par GitHub Pages)
├── backups/                # Sauvegardes auto avant chaque mise à jour
├── requirements.txt
└── .gitignore
```

## 🔄 Flux de mise à jour

```
Quotidien 3h00 UTC (workflow update-annuaire.yml)
    │
    ▼
scraper.py (amdg + portelatine) ──► update_manager.py ──► generate_html.py ──► commit+push
    │                                 │                          │
    │                                 ├─ backup SQLite           └─ output/index.html + data.js
    │                                 ├─ fusion + dédup
    │                                 └─ notification Telegram
    ▼
GitHub Pages redéploie automatiquement (1-2 min)

Hebdomadaire dimanche 4h00 UTC (workflow update-annuaire-cef.yml)
    │
    ▼
AnnuaireCEFParser (grille géographique ~130 points, ~45k églises)
    │
    ▼
update_manager.py ──► generate_html.py ──► commit+push
```

## 🚀 Démarrage rapide

### 1. Forker / cloner

```bash
git clone https://github.com/[TOI]/[nom-du-repo].git
cd [nom-du-repo]
```

### 2. Configurer les secrets GitHub

Dans `Settings → Secrets and variables → Actions → New repository secret` :

| Secret | Obligatoire ? | Description |
|--------|---------------|-------------|
| `TELEGRAM_BOT_TOKEN` | Non (recommandé) | Token du bot Telegram (voir §Notifications) |
| `TELEGRAM_CHAT_ID` | Non (recommandé) | ID du chat où envoyer les notifications |

### 3. Activer GitHub Pages

1. `Settings → Pages`
2. **Source** : `Deploy from a branch`
3. **Branch** : `main`, dossier `/` (racine — `index.html` y est copié automatiquement par le workflow)
4. Save

### 4. Lancer manuellement le workflow

1. `Actions` → `Mise à jour annuaire messes en latin`
2. Bouton **Run workflow** → branch `main`

### 5. Vérifier

- Le workflow passe (checklist verte)
- `output/index.html` est commité et poussé
- Le site répond : `https://[TOI].github.io/[nom-du-repo]/`

## 📊 Sources de données

| Source | URL | Contenu | Fréquence | Fiabilité |
|--------|-----|---------|-----------|-----------|
| **Messes.info (CEF)** | messes.info/annuaire | **Annuaire national : toutes les églises de France + GPS précis** | Hebdo (grille géographique) | ★★★★☆ |
| **AMDG** | amdg.asso.fr/lieux_messes_spv.htm | Messes tridentin (forme extraordinaire), toutes communautés en lien avec Rome | Hebdo (vendredi) | ★★★★★ |
| **La Porte Latine** | laportelatine.org/lieux | FSSPX + communautés amies (Transfiguration, Capucins Morgon, Dominicaines Avrillé) | Dynamique | ★★★★☆ |
| **Messes.info (horaires)** | messes.info/lieu | Horaires par date + GPS. Fallback HTML exploitable | Quotidien (vérification) | ★★★★☆ |
| **Trouver une messe** | trouverunemesse.com | Agrégateur basé sur messes.info (vérification croisée) | Quotidien (vérification) | ★★★☆☆ |

### Règles de fusion
- **Déduplication** : fuzzy matching (rapidfuzz, seuil 85) sur ville + lieu + rite + communauté ; URL messes.info unique pour l'annuaire national
- **Confiance** : 5 = 3+ sources · 4 = 2 sources · 3 = source fiable unique · 2 = source faible unique
- **Désactivation** : lieu absent de ≥ 2 sources sur 4 → `actif=0` (les lieux d'origine manuelle et l'annuaire national CEF sont protégés)
- **Priorité champs** : AMDG > Porte Latine > annuaire CEF > messes.info > trouverunemesse
- **Ajout de lieux** : **AMDG** (tridentin), **Porte Latine** (FSSPX) et **annuaire CEF** (églises générales) ajoutent des lieux. `trouverunemesse` et `messes.info` (horaires) sont des sources de **vérification**.

## 🔔 Notifications Telegram

### Créer un bot (1 minute)

1. Ouvrez Telegram → cherchez **@BotFather**
2. `/newbot` → nom → username
3. Copiez le **token** (ex: `123456:ABC-DEF...`)
4. Ouvrez votre bot → envoyez `/start`
5. Trouvez votre **chat ID** : envoyez un message au bot puis visitez `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`

### Configurer
```
Settings → Secrets → TELEGRAM_BOT_TOKEN = <token>
Settings → Secrets → TELEGRAM_CHAT_ID = <id numérique>
```

Chaque nuit, vous recevez un résumé :
```
🕐 Mise à jour 08/08/2026 03:01
🆕 Nouveaux : 3
✏️ Modifiés : 12
🚫 Désactivés : 1
⏱️ Durée : 42.5s

📍 Nouveaux lieux :
  • Lyon – Chapelle Saint-Irénée
  • ...
```

## 🗄️ Persistance & sauvegardes

- **Base SQLite** commitée dans le repo → persiste entre les runs, versionnée par git
- **Backups automatiques** : copie locale `backups/messes_YYYYMMDD_HHMMSS.db` avant chaque mise à jour (14 conservés sur le runner, non commités)
- **Restaurer** : `git checkout HEAD~1 -- data/messes.db` (via l'historique git) ou télécharger le backup depuis l'artifact GitHub Actions (`Settings → Artifacts`)

## 🌐 Domaine personnalisé gratuit

### Option A : sous-domaine .github.io (défaut)
Rien à faire.

### Option B : domaine eu.org (recommandé)

1. Allez sur [nic.eu.org](https://nic.eu.org) → `Register a domain`
2. Choisissez un nom (ex: `messes-latin-france.eu.org`), type `Host`
3. Ajoutez 4 enregistrements DNS A (IP de GitHub Pages) :
   - `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   *(ou 1 CNAME `messes-latin-france.eu.org → [TOI].github.io`)*
4. Validez : confirmation par email, activation sous quelques jours
5. Dans le repo : `Settings → Pages → Custom domain` → `messes-latin-france.eu.org`
6. **Activer le CNAME automatique** : dans les *Settings du repo → Secrets and variables → Actions → Variables*, créez `CUSTOM_DOMAIN = messes-latin-france.eu.org`. Le workflow écrira automatiquement le fichier `CNAME` à chaque mise à jour.
7. **Mettre à jour les URLs canoniques** : dans `src/config.py`, remplacez `BASE_URL` par `https://messes-latin-france.eu.org`. Les canonical, sitemap et robots de toutes les pages suivront automatiquement.
8. Activez le HTTPS dans `Settings → Pages` (GitHub l'active automatiquement après quelques minutes).

> 💡 **Prêt à l'emploi** : toute la bascule technique est déjà en place (variable `BASE_URL` + support `CUSTOM_DOMAIN` dans les 2 workflows). Seule la valeur de `BASE_URL` reste à changer le jour J.

### Option C : domaine à prix coûtant
Un `.fr` coûte ~8-12€/an — même procédure, remplacez `BASE_URL` et `CUSTOM_DOMAIN` par votre domaine.

> ❌ **Éviter Freenom** (.tk/.ml/.ga/.cf/.gq) : instable, récupérations de domaines fréquentes.

## 🐛 Dépannage

| Problème | Solution |
|----------|----------|
| Workflow échoue sur `requests` | Vérifier que `requirements.txt` est committé et que pip a accès réseau |
| Site ne se met pas à jour | Vérifier `Actions` → dernier run → step "Commit et push" |
| "No module named lxml" | `pip install -r requirements.txt` en local puis committer le code |
| GitHub Pages 404 | Vérifier `Settings → Pages` → branch/dossier corrects (main + / ou /output) |
| Désactivations massives | Le scrap peut échouer (site down) → relancer manuellement le workflow |
| Base corrompue | Restaurer un backup : `cp backups/messes_*.db data/messes.db` |
| Notification Telegram absente | Vérifier les 2 secrets + que le bot a été démarré (`/start`) |

## 📈 Limites connues

- **GitHub Actions** : 2000 min/mois (≈ 55 min/jour max pour un run quotidien) — large marge
- **Stockage repo** : 500 Mo — base SQLite ≈ quelques centaines de Ko
- **messes.info** : version GWT inexploitable → fallback HTML uniquement (structure documentée)
- **Géolocalisation** : centroïdes département pour le tri ; GPS précis seulement si messes.info les fournit

## 📄 Licence

Données issues de sources publiques citées (AMDG, La Porte Latine, messes.info, trouverunemesse). Code sous licence MIT.
