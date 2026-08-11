#!/usr/bin/env python3
"""
Rapport hebdomadaire Google Search Console — envoyé automatiquement.

Usage :
  export GOOGLE_TOKEN=data/google_token.json   (ou défaut)
  python3 src/gsc_report.py

Sortie : rapport clics / impressions / CTR / position sur 7 jours,
top requêtes, pages indexées. Si aucun token → message clair (rien à faire).
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = ROOT / "data" / "google_token.json"
SITE_URL = "https://messes-france.github.io/"


def main():
    if not TOKEN_PATH.exists():
        print("⚠️ Pas de token Google — lancez d'abord python3 src/google_setup.py")
        return 1

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH),
            ["https://www.googleapis.com/auth/webmasters.readonly"])
        if creds and creds.refresh_token and (not creds.valid):
            creds.refresh(Request())

        service = build("searchconsole", "v1", credentials=creds)

        today = datetime.date.today()
        start = today - datetime.timedelta(days=7)

        # 1. Vue globale 7 jours
        body = {
            "startDate": start.isoformat(),
            "endDate": today.isoformat(),
            "dimensions": [],
        }
        res = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
        rows = res.get("rows", [])
        if not rows:
            print("📊 Aucune donnée sur les 7 derniers jours (site récent ou non indexé).")
        else:
            r = rows[0]
            clicks = r.get("clicks", 0)
            impr = r.get("impressions", 0)
            ctr = r.get("ctr", 0) * 100
            pos = r.get("position", 0)
            print(f"📊 Search Console — {start} → {today}")
            print(f"   Clics: {clicks} | Impressions: {impr} | CTR: {ctr:.1f}% | Position moy: {pos:.1f}")

        # 2. Top requêtes
        body2 = {
            "startDate": start.isoformat(),
            "endDate": today.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 10,
        }
        res2 = service.searchanalytics().query(siteUrl=SITE_URL, body=body2).execute()
        top = res2.get("rows", [])
        if top:
            print("\n🏆 Top requêtes (7 j) :")
            for r in top:
                print(f"   « {r['keys'][0]} » — {r['clicks']} clics / {r['impressions']} impressions / pos {r['position']:.1f}")

        # 3. Pages indexées (sitemap status)
        try:
            sitemaps = service.sitemaps().list(siteUrl=SITE_URL).execute()
            for s in sitemaps.get("sitemap", []):
                path = s.get("path", "")
                if "sitemap.xml" in path:
                    print(f"\n🗺️ Sitemap : {s.get('contents', [{}])[0].get('submitted', '?')} soumises, "
                          f"{s.get('contents', [{}])[0].get('indexed', '?')} indexées")
        except Exception as e:
            print(f"\n⚠️ Sitemap status: {e}")

        print("\n✅ Rapport terminé.")
        return 0
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
