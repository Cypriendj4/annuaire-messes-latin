# 🚀 Setup Google Search Console — guide minimal (15 min, une seule fois)

Ce guide crée les accès qui rendent l'agent autonome sur Search Console.
Après ces 15 minutes, plus rien à faire : l'agent soumet les sitemaps,
lit les performances et envoie un rapport hebdomadaire automatique.

---

## Étape 1 — Créer le compte Google dédié (5 min)

1. Va sur https://accounts.google.com → « Créer un compte » → « Pour ma vie professionnelle »
2. Email : `annuaire.messes.france@gmail.com` (ou autre, au choix)
3. Mot de passe fort, récupération par téléphone (obligatoire)
4. Garde ce compte **exclusivement pour les outils Google du site** (Search Console, AdSense plus tard)

✅ Fait quand : tu peux te connecter à gmail.com avec ce compte.

---

## Étape 2 — Créer le projet + activer l'API + la clé (10 min)

1. Ouvre https://console.cloud.google.com **connecté avec le compte dédié**
2. En haut, à côté du logo → « Sélectionner un projet » → « Nouveau projet »
   → Nom : `annuaire-messes` → Créer
3. Assure-toi que le projet `annuaire-messes` est bien sélectionné (menu du haut)
4. Menu ☰ → « API et services » → « Bibliothèque »
   - Cherche **Search Console API** → clique → **Activer**
   - (optionnel) Cherche **AdSense Management API** → **Activer** (pour plus tard)
5. Menu ☰ → « API et services » → « Identifiants » → **« + Créer des identifiants »**
   → **ID client OAuth** → Type d'application : **Application de bureau** → Créer
6. Sur le client créé → bouton **« Télécharger le JSON »**
   → le fichier téléchargé s'appelle `client_secret.json`

✅ Fait quand : tu as le fichier `client_secret.json` sur ton ordinateur.

---

## Étape 3 — Donner le fichier à l'agent (1 min)

Dépose `client_secret.json` dans :
```
/workspace/annuaire-messes-latin/client_secret.json
```
⚠️ Ce fichier est **gitignoré** : il ne sera jamais publié sur GitHub.

✅ Fait quand : le fichier est dans le dossier du projet.

---

## Étape 4 — L'agent fait le reste (automatique)

L'agent lance :
```
python3 src/google_setup.py
```
Une URL d'autorisation Google s'affiche → tu te connectes avec le compte
dédié et tu cliques « Autoriser » (30 secondes).

Ensuite, automatiquement :
- ✅ Site ajouté à Search Console
- ✅ Sitemap soumis (221 URLs)
- ✅ Vérification de la propriété (balise meta injectée si besoin)
- ✅ Test de lecture des performances

---

## Après : ce que l'agent peut faire seul

| Tâche | Méthode |
|-------|---------|
| Rapport hebdomadaire clics/impressions/positions | Cron automatique |
| Vérifier l'indexation (pages indexées vs non) | API |
| Soumettre les nouveaux sitemaps après chaque mise à jour | API |
| Alerter si le trafic chute ou si une page disparaît de l'index | Cron + comparaison |

---

## ❓ FAQ

**Pourquoi je ne peux pas créer le compte moi-même ?**
Google bloque la création de compte automatisée (SMS, captcha, politique anti-bot).
C'est une barrière volontaire — aucun outil ne la contourne légalement.

**Et AdSense ?**
L'API sera branchée, mais Google doit d'abord **approuver le compte**
(dossier : revenus estimés, politique de contenu, site en ligne depuis
quelques mois). C'est une décision humaine de Google, il faut patienter.

**Et si je perds le fichier client_secret.json ?**
Tu peux le re-télécharger à tout moment depuis
Console Cloud → Identifiants → le client OAuth → Télécharger le JSON.

**Le token expire ?**
Le refresh token est stocké dans `data/google_token.json` (gitignoré).
Tant que l'application reste en mode « Test » dans Google Cloud, le token
peut expirer tous les 7 jours ; si ça arrive, l'agent relance simplement
le device flow (30 secondes de validation). Pour un accès permanent sans
revalidation, on peut publier l'application dans Google Cloud (2 clics,
gratuit) — l'agent le fera quand le compte sera prêt.
