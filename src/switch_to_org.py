#!/usr/bin/env python3
"""
Bascule vers l'organisation GitHub (ex: messes-france.github.io).

Prérequis (fait par l'utilisateur dans le navigateur) :
  1. Organisation créée sur GitHub (ex: messes-france)
  2. Repo annuaire-messes-latin TRANSFÉRÉ vers cette organisation
     (Settings → Danger Zone → Transfer ownership)

Ce script fait :
  1. Renomme le repo en <org>.github.io (URL racine propre)
  2. Active GitHub Pages sur la racine (branch main, path /)
  3. Met à jour BASE_URL dans src/config.py
  4. Affiche la commande pour pointer le remote local vers la nouvelle URL

Usage : python3 src/switch_to_org.py messes-france
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

GH_TOKEN_ENV = "GH_TOKEN"


def gh_api(method: str, path: str, payload=None) -> dict:
    token = os.environ.get(GH_TOKEN_ENV, "")
    if not token:
        print(f"❌ Variable d'environnement {GH_TOKEN_ENV} absente.")
        sys.exit(1)
    url = f"https://api.github.com{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"❌ API GitHub {method} {path} → {e.code}: {body[:250]}")
        sys.exit(1)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 switch_to_org.py <nom-org>")
        return 1
    org = sys.argv[1].strip().lower()
    new_repo_name = f"{org}.github.io"
    new_url = f"https://{org}.github.io"

    print(f"=== Bascule vers l'organisation {org} ===")
    print(f"Cible: {new_url}\n")

    # 1. Vérifier que le repo est bien transféré (il existe sous l'org)
    try:
        repo = gh_api("GET", f"/repos/{org}/annuaire-messes-latin")
        print(f"✅ Repo trouvé sous l'org: {repo['full_name']}")
    except SystemExit:
        print(f"❌ Le repo {org}/annuaire-messes-latin n'existe pas.")
        print("   → Avez-vous transféré le repo ? (Settings → Danger Zone → Transfer ownership)")
        return 1

    # 2. Renommer en <org>.github.io
    if repo["name"] != new_repo_name:
        gh_api("PATCH", f"/repos/{org}/annuaire-messes-latin", {"name": new_repo_name})
        print(f"✅ Repo renommé: {org}/{new_repo_name}")
    else:
        print(f"ℹ️  Repo déjà nommé {new_repo_name}")

    # 3. Activer Pages sur la racine
    try:
        pages = gh_api("GET", f"/repos/{org}/{new_repo_name}/pages")
        print(f"ℹ️  Pages déjà actif: source={pages.get('source', {}).get('branch')} path={pages.get('source', {}).get('path')}")
    except SystemExit:
        gh_api("POST", f"/repos/{org}/{new_repo_name}/pages",
               {"source": {"branch": "main", "path": "/"}})
        print(f"✅ Pages activé sur {org}/{new_repo_name} (branch main, path /)")

    # 4. BASE_URL dans config.py
    root = Path(__file__).resolve().parent.parent
    cfg = root / "src" / "config.py"
    text = cfg.read_text(encoding="utf-8")
    new_text = text.replace('BASE_URL = "https://cypriendj4.github.io/annuaire-messes-latin"',
                            f'BASE_URL = "{new_url}"')
    if new_text != text:
        cfg.write_text(new_text, encoding="utf-8")
        print(f"✅ src/config.py → BASE_URL = {new_url}")
    else:
        print(f"ℹ️  BASE_URL déjà configuré — vérifiez src/config.py")

    # 5. Remote local
    print("\n=== Commandes pour le repo local ===")
    print(f"  git remote set-url origin https://github.com/{org}/{new_repo_name}.git")
    print(f"  git push -u origin main")
    print("\n⚠️  Ne poussez PAS avant d'avoir régénéré le site avec le nouveau BASE_URL :")
    print("  python3 src/generate_html.py && python3 src/generate_dept_pages.py && python3 src/generate_pages.py")
    print("  cp output/index.html index.html && cp output/data.js data.js && cp -r output/departements ./departements")
    print("  cp output/sitemap.xml sitemap.xml && cp output/robots.txt robots.txt")
    print("  cp output/messes-en-latin.html messes-en-latin.html && cp output/rites-orientaux.html rites-orientaux.html && cp output/a-propos.html a-propos.html")

    print("\n=== Vérification finale ===")
    print(f"  curl -I https://{new_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
