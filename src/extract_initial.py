"""
Extrait le tableau DATA du fichier HTML original (uploadé par l'utilisateur)
et génère un fichier JSON des 119 lieux → data/initial_data.json

Usage :
    python extract_initial.py <chemin_vers_le_html>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def extract_data_from_html(html_path: str) -> list[dict]:
    text = Path(html_path).read_text(encoding="utf-8")
    # Capture le bloc const DATA = [ ... ];
    m = re.search(r'const DATA = \[(.*?)\];', text, re.S)
    if not m:
        raise ValueError("Bloc 'const DATA' introuvable dans le HTML")
    raw = m.group(1)

    # Chaque entrée est {ville:"...",dept:"...",...} sur une ligne
    entries = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        # Extrait paires clé:"valeur" (attention aux apostrophes françaises)
        fields = {}
        for key, val in re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', line):
            fields[key] = val
        if fields.get("ville"):
            entries.append(fields)
    return entries


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_initial.py <fichier.html>")
        return 1
    html_path = sys.argv[1]
    entries = extract_data_from_html(html_path)
    print(f"Entrées extraites: {len(entries)}")

    out = Path(__file__).resolve().parent.parent / "data" / "initial_data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Écrit dans: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())