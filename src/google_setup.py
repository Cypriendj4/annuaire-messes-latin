#!/usr/bin/env python3
"""
Configuration Google Search Console pour l'annuaire.

Usage (une seule fois, après avoir créé le client OAuth2 dans Google Cloud) :
  1. Créer un projet Google Cloud → activer Search Console API
  2. Créer des identifiants OAuth2 (type : application de bureau)
  3. Exporter :
       export GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
       export GOOGLE_CLIENT_SECRET="xxx"
     ou créer un fichier client_secret.json téléchargé depuis Google Cloud
  4. python3 src/google_setup.py

Ce script :
  - Obtient un refresh token (device flow, l'utilisateur valide dans le navigateur)
  - Stocke le token dans data/google_token.json (jamais commité)
  - Ajoute le site à Search Console
  - Soumet le sitemap
  - Lit les performances (clics, impressions) en test
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = ROOT / "data" / "google_token.json"
SITE_URL = "https://messes-france.github.io/"
SITEMAP = "https://messes-france.github.io/sitemap.xml"

SCOPES = [
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/webmasters.readonly",
]


def get_credentials():
    # 1. Token existant ?
    if TOKEN_PATH.exists():
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            return creds

    # 2. Flow device : affiche une URL à ouvrir
    from google_auth_oauthlib.flow import InstalledAppFlow
    print("=" * 60)
    print("AUTHENTIFICATION GOOGLE — une seule fois")
    print("=" * 60)
    print("Un navigateur va s'ouvrir (ou une URL à copier).")
    print("Connectez-vous avec le compte Google dédié et autorisez l'accès.")
    print("=" * 60)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(ROOT / "client_secret.json"), scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob")
    creds = flow.run_console()

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅ Token stocké: {TOKEN_PATH}")
    return creds


def get_service(creds):
    from googleapiclient.discovery import build
    return build("searchconsole", "v1", credentials=creds)


def main():
    creds = get_credentials()

    service = get_service(creds)

    # 1. Liste les propriétés existantes
    sites = service.sites().list().execute()
    existing = [s["siteUrl"] for s in sites.get("siteEntry", [])]
    print(f"Propriétés actuelles: {existing}")

    # 2. Ajoute le site si absent
    if SITE_URL not in existing:
        try:
            service.sites().add(siteUrl=SITE_URL).execute()
            print(f"✅ Site ajouté à Search Console: {SITE_URL}")
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ Ajout site: {e}")
            print("   (le site doit d'abord être vérifié — voir étape suivante)")

    # 3. Soumet le sitemap
    try:
        service.sitemaps().submit(siteUrl=SITE_URL, feedpath=SITEMAP).execute()
        print(f"✅ Sitemap soumis: {SITEMAP}")
    except Exception as e:
        print(f"⚠️ Sitemap: {e}")

    # 4. Test : performances 7 derniers jours
    try:
        import datetime
        today = datetime.date.today()
        start = today - datetime.timedelta(days=7)
        body = {
            "startDate": start.isoformat(),
            "endDate": today.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 5,
        }
        res = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
        rows = res.get("rows", [])
        print(f"📊 Performances (7 j): {len(rows)} requêtes top")
        for r in rows:
            print(f"   {r['keys'][0]}: {r['clicks']} clics / {r['impressions']} impressions")
    except Exception as e:
        print(f"⚠️ Performances: {e}")

    print("\n✅ Configuration terminée.")


if __name__ == "__main__":
    sys.exit(main())
