#!/usr/bin/env python3
"""Publie les chapitres lus par la voix de synthèse dans les Releases du dépôt (une par livre)
et tient à jour donnees/synthese.json, que la webapp utilise.

    python3 scripts/assembler.py --lots dossier_des_lots --voix estelle --vitesse 0.9

Chaque sous-dossier de --lots contient les MP3 d'un lot, son rapport et un fichier lot.json
({"id": …}). Quand tous les chapitres d'un livre sont publiés, un ZIP du livre entier est ajouté.
Nécessite la commande gh (GitHub CLI) et la variable GH_TOKEN.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from commun import RACINE, identifiant, lire_catalogue  # noqa: E402

SYNTHESE = RACINE / "donnees" / "synthese.json"
TEXTES = RACINE / "donnees" / "textes.csv"
DEPOT = os.environ.get("GITHUB_REPOSITORY", "biblioGironde/Kit-Liseuses-Les-Classiques-En-Numerique-Audio")


def gh(*args, check=True):
    return subprocess.run(["gh", *args, "-R", DEPOT], check=check, capture_output=True, text=True)


def creer_release(tag, livre, voix, page):
    if gh("release", "view", tag, check=False).returncode == 0:
        return
    notes = (f"{livre['auteur']}, *{livre['titre']}* — lu par une voix de synthèse (IA).\n\n"
             f"Voix : Pocket TTS © Kyutai (CC BY 4.0), voix « {voix} ».\n"
             f"Texte du domaine public : Wikisource ({page}).\n\n"
             "Ces enregistrements sont placés dans le domaine public (CC0 1.0).")
    gh("release", "create", tag, "--title", f"{livre['titre']} — {livre['auteur']} (voix de synthèse)", "--notes", notes)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lots", required=True)
    p.add_argument("--voix", default="estelle")
    p.add_argument("--vitesse", default="0.9")
    args = p.parse_args()

    fait = json.loads(SYNTHESE.read_text(encoding="utf-8")) if SYNTHESE.exists() else {}
    livres = {identifiant(l): l for l in lire_catalogue()}
    with open(TEXTES, newline="", encoding="utf-8") as f:
        textes = {l["id"]: l for l in csv.DictReader(f)}

    touches = set()
    for dossier in sorted(Path(args.lots).iterdir()):
        info = dossier / "lot.json"
        if not info.exists():
            continue
        ident = json.loads(info.read_text())["id"]
        livre, texte = livres.get(ident), textes.get(ident, {})
        if not livre:
            continue
        rapports = [r for f in dossier.glob("rapport-*.json") for r in json.loads(f.read_text(encoding="utf-8"))]
        if not rapports:
            continue
        tag = f"ia-{ident}"
        entree = fait.setdefault(ident, {
            "tag": tag, "voix": args.voix, "vitesse": float(args.vitesse), "modele": "Pocket TTS (Kyutai), french_24l",
            "page": texte.get("page", ""), "chapitres": {}, "termine": False, "zip": "",
        })
        creer_release(tag, livre, entree["voix"], entree["page"])
        fichiers = [str(dossier / r["fichier"]) for r in rapports if (dossier / r["fichier"]).exists()]
        if fichiers:
            gh("release", "upload", tag, *fichiers, "--clobber")
        for r in rapports:
            if (dossier / r["fichier"]).exists():
                entree["chapitres"][str(r["chapitre"])] = {"t": r["titre"], "d": round(r["duree"]), "f": r["fichier"]}
            entree["total"] = r.get("total", entree.get("total"))
        print(f"  {ident} : {len(fichiers)} chapitres publiés ({len(entree['chapitres'])}/{entree.get('total')})")
        touches.add(ident)

    for ident in touches:
        e = fait[ident]
        if e.get("total") and len(e["chapitres"]) >= e["total"] and not e["termine"]:
            with tempfile.TemporaryDirectory() as tmp:
                gh("release", "download", e["tag"], "-p", "*.mp3", "-D", tmp, "--clobber")
                nom = f"{ident}.zip"
                with zipfile.ZipFile(Path(tmp) / nom, "w", zipfile.ZIP_STORED) as z:
                    for n in sorted(e["chapitres"], key=int):
                        f = Path(tmp) / e["chapitres"][n]["f"]
                        if f.exists():
                            z.write(f, f.name)
                gh("release", "upload", e["tag"], str(Path(tmp) / nom), "--clobber")
            e.update(termine=True, zip=nom)
            print(f"  ✓ {ident} terminé : ZIP publié")

    SYNTHESE.parent.mkdir(exist_ok=True)
    SYNTHESE.write_text(json.dumps(dict(sorted(fait.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
