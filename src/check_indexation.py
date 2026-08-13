#!/usr/bin/env python3
"""
Surveillance d'indexation Google pour messes-france.github.io.

Comportement watchdog :
- 0 résultat indexé  → sortie VIDE (silence — rien de nouveau)
- 1ère indexation    → alerte complète (passage 0 → N)
- déjà indexé        → silence (pas de spam)

Prérequis : serveur Camoufox (camofox-browser) actif sur localhost:9377.
État persistant : ~/.hermes/cron/output/indexation_state.json
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

SITE = "messes-france.github.io"
STATE_FILE = Path.home() / ".hermes" / "cron" / "output" / "indexation_state.json"
CAMOFOX = "http://localhost:9377"
UA = {"User-Agent": "curl/8.5.0", "Content-Type": "application/json"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
    return urllib.request.urlopen(req, timeout=15)


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=UA, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=60))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"count": 0, "alerted": False}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def check_health():
    try:
        d = json.load(urllib.request.urlopen(CAMOFOX + "/health", timeout=8))
        return d.get("ok", False)
    except Exception:
        return False


def main():
    # 1. Camoufox actif ?
    if not check_health():
        print("⚠️ Serveur Camoufox indisponible — surveillance d'indexation impossible. "
              "Vérifier que camofox-browser tourne (port 9377).")
        return 1

    # 2. Recherche Google site:
    try:
        r = post(CAMOFOX + "/tabs/open",
                 {"userId": "hermes", "url": f"https://www.google.com/search?q=site%3A{SITE}",
                  "listItemId": "idx-check"})
        tab = r.get("tabId", "")
        time.sleep(5)
        snap = get(f"{CAMOFOX}/tabs/{tab}/snapshot?userId=hermes&format=text").read().decode()
        ev = post(f"{CAMOFOX}/tabs/{tab}/evaluate", {
            "userId": "hermes",
            "expression": "(() => { const s = document.querySelector('#result-stats'); "
                          "return JSON.stringify({stats: s ? s.textContent : '', "
                          "count: document.querySelectorAll('a h3').length}); })()"})
        res = json.loads(ev.get("result", "{}"))
        # Fermer l'onglet
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"{CAMOFOX}/tabs/{tab}?userId=hermes", method="DELETE"), timeout=10)
        except Exception:
            pass

        count = int(res.get("count", 0))
        stats = res.get("stats", "")

        # Captcha / trafic inhabituel → ne pas conclure (silence)
        if "unusual traffic" in stats.lower() or "captcha" in stats.lower():
            return 0

        state = load_state()

        # 1ère indexation : passage 0 → N
        if count > 0 and not state.get("alerted"):
            state.update({"count": count, "alerted": True, "first_seen": time.strftime("%Y-%m-%d %H:%M")})
            save_state(state)
            print(f"🎉 PREMIÈRE INDEXATION GOOGLE !\n"
                  f"site:{SITE} montre maintenant {count} résultat(s) : {stats}\n\n"
                  f"Prochaines étapes :\n"
                  f"1. Vérifier le rapport Performances dans Search Console\n"
                  f"2. Lancer la création de contenu éditorial (voir to-do)\n"
                  f"3. Suivre l'évolution dans les semaines qui viennent")
            return 0

        # Déjà indexé → silence
        if count > 0:
            return 0

        # 0 résultat → silence (rien de nouveau)
        save_state({"count": 0, "alerted": state.get("alerted", False)})
        return 0

    except Exception as e:
        print(f"⚠️ Erreur lors de la vérification d'indexation : {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
