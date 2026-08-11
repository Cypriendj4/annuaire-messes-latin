#!/usr/bin/env python3
"""
Bascule vers le domaine personnalisé — À LANCER LE JOUR J (une seule fois).

Prérequis (fait par l'utilisateur sur nic.eu.org, ~20 min) :
  1. Compte créé sur https://nic.eu.org (email de validation)
  2. Domaine demandé : messes-en-france.eu.org
  3. Approbation reçue (2-15 jours)
  4. DNS configuré sur nic.eu.org :
       A 185.199.108.153 / 185.199.109.153 / 185.199.110.153 / 185.199.111.153
     (ou CNAME messes-en-france.eu.org → cypriendj4.github.io)

Ce script fait :
  1. Met à jour BASE_URL dans src/config.py
  2. Crée le fichier CNAME (requis par GitHub Pages)
  3. Crée la variable GitHub CUSTOM_DOMAIN (via API)
  4. Active le custom domain dans GitHub Pages (via API)
  5. Attend la vérification DNS + HTTPS (via API)

Usage : python3 src/switch_domain.py messes-en-france.eu.org
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = "Cypriendj4/annuaire-messes-latin"
GH_TOKEN_ENV = "GH_TOKEN"


def gh_api(method: str, path: str, payload=None) -> dict:
    token = os.environ.get(GH_TOKEN_ENV, "")
    if not token:
        print(f"❌ Variable d'environnement {GH_TOKEN_ENV} absente — exportez votre token GitHub.")
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
        print(f"❌ API GitHub {method} {path} → {e.code}: {body[:200]}")
        sys.exit(1)


def set_variable(name: str, value: str) -> None:
    payload = {"name": name, "value": value}
    try:
        gh_api("POST", f"/repos/{REPO}/actions/variables", payload)
        print(f"✅ Variable GitHub créée: {name} = {value}")
    except SystemExit:
        print(f"   → Créez-la manuellement : Repo → Settings → Secrets and variables → Actions → Variables")


def set_pages_domain(domain: str) -> None:
    pages = gh_api("GET", f"/repos/{REPO}/pages")
    cname = pages.get("cname")
    if cname == domain:
        print(f"✅ Custom domain déjà actif: {cname}")
        return
    payload = {"cname": domain, "source": {"branch": "main", "path": "/"}}
    try:
        gh_api("PUT", f"/repos/{REPO}/pages", payload)
        print(f"✅ Custom domain demandé: {domain}")
    except SystemExit:
        print("   (si 422 : activez d'abord le DNS — vérifiez les enregistrements A/CNAME)")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 switch_domain.py <domaine>")
        return 1
    domain = sys.argv[1].strip().lower().lstrip("https://").rstrip("/")
    root = Path(__file__).resolve().parent.parent
    base_url = f"https://{domain}"

    print(f"=== Bascule vers {domain} ===")

    # 1. BASE_URL dans config.py
    cfg = root / "src" / "config.py"
    text = cfg.read_text(encoding="utf-8")
    new_text = text.replace('BASE_URL = "https://cypriendj4.github.io/annuaire-messes-latin"',
                            f'BASE_URL = "{base_url}"')
    if new_text != text:
        cfg.write_text(new_text, encoding="utf-8")
        print(f"✅ src/config.py → BASE_URL = {base_url}")
    else:
        print(f"ℹ️  BASE_URL déjà configuré (ou format inattendu) — vérifiez src/config.py")

    # 2. Fichier CNAME (commit direct dans le repo)
    cname_file = root / "CNAME"
    cname_file.write_text(domain + "\n", encoding="utf-8")
    print(f"✅ CNAME écrit: {domain}")

    # 3. Variable GitHub (à créer manuellement — l'API ne gère pas les variables de repo)
    set_variable("CUSTOM_DOMAIN", domain)

    # 4. Custom domain dans GitHub Pages
    set_pages_domain(domain)

    print("\n=== Prochaines étapes ===")
    print(f"1. Commit + push du CNAME et de config.py (le workflow régénérera les URLs)")
    print(f"2. GitHub Pages vérifie le DNS automatiquement (quelques minutes à quelques heures)")
    print(f"3. HTTPS actif automatiquement (Settings → Pages → Enforce HTTPS)")
    print(f"4. Ancienne URL redirigera vers la nouvelle (GitHub le fait automatiquement)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
