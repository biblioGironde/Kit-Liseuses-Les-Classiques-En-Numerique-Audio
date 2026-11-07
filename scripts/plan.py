#!/usr/bin/env python3
"""Prépare le travail de la voix de synthèse : quels chapitres lire, répartis en lots.

Lit donnees/textes.csv (livres prêts) et donnees/synthese.json (chapitres déjà publiés), et
écrit plan.json : une liste de lots d'environ 2 h 30 d'écoute, chacun lu par une machine.

    python3 scripts/plan.py --max-lots 60 [--livres voltaire-candide,emile-zola-germinal]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from commun import RACINE  # noqa: E402

TEXTES = RACINE / "donnees" / "textes.csv"
SYNTHESE = RACINE / "donnees" / "synthese.json"
CACHE = RACINE / "textes"
CAR_PAR_LOT = 180_000  # ≈ 2 h 30 d'écoute, soit 3 à 4 h de calcul : sous la limite de 6 h par machine


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-lots", type=int, default=60)
    p.add_argument("--livres", default="", help="identifiants séparés par des virgules (vide = tous)")
    p.add_argument("--sortie", default="plan.json")
    p.add_argument("--voix", default="estelle", help="voix des livres pas encore commencés")
    p.add_argument("--vitesse", default="0.9", help="vitesse des livres pas encore commencés")
    p.add_argument("--resume", default="", help="fichier Markdown où écrire le bilan")
    args = p.parse_args()

    from synthese import lire_epub
    fait = json.loads(SYNTHESE.read_text(encoding="utf-8")) if SYNTHESE.exists() else {}
    filtre = {x.strip() for x in args.livres.split(",") if x.strip()}
    with open(TEXTES, newline="", encoding="utf-8") as f:
        textes = [l for l in csv.DictReader(f) if l["statut"] == "ok" and (not filtre or l["id"] in filtre)]

    lots, restant_car, livres_en_attente = [], 0, 0
    for t in textes:
        deja = set((fait.get(t["id"]) or {}).get("chapitres", {}))
        chemin = CACHE / f"{t['id']}.epub"
        if not chemin.exists():
            print(f"  ! {t['id']} : EPUB absent du cache (lancer scripts/textes.py)")
            continue
        chapitres = lire_epub(chemin)
        a_lire = [(n, sum(len(x) for _, x in ch)) for n, ch in enumerate(chapitres, 1) if str(n) not in deja]
        if not a_lire:
            continue
        livres_en_attente += 1
        reglages = fait.get(t["id"]) or {}
        base = {"id": t["id"], "auteur": t["auteur"], "titre": t["titre"],
                "voix": reglages.get("voix", args.voix), "vitesse": str(reglages.get("vitesse", args.vitesse))}
        courant, taille = [], 0
        for n, car in a_lire:
            restant_car += car
            if courant and taille + car > CAR_PAR_LOT:
                lots.append({**base, "chapitres": ",".join(map(str, courant)), "car": taille})
                courant, taille = [], 0
            courant.append(n)
            taille += car
        if courant:
            lots.append({**base, "chapitres": ",".join(map(str, courant)), "car": taille})

    total = len(lots)
    lots = lots[:args.max_lots]
    for k, lot in enumerate(lots, 1):
        lot["lot"] = k
    Path(args.sortie).write_text(json.dumps(lots, ensure_ascii=False), encoding="utf-8")
    if args.resume:
        with open(TEXTES, newline="", encoding="utf-8") as f:
            tous = list(csv.DictReader(f))
        lignes = ["## Textes Wikisource", "", "| Livre | Page Wikisource | Chapitres | Écoute estimée | Lu | État |",
                  "|---|---|---|---|---|---|"]
        for l in tous:
            e = fait.get(l["id"]) or {}
            lu = f"{len(e.get('chapitres', {}))}/{e.get('total', l['chapitres'])}" if e else "—"
            etat = (l["statut"] + (" — " + l["remarque"] if l.get("remarque") else "")).replace("|", "/")
            lignes.append(f"| {l['auteur']} — {l['titre']} | {l['page']} | {l['chapitres']} | {l['heures']} h | {lu} | {etat} |")
        lignes += ["", f"**{len(lots)} lots lancés pour ce passage, {total - len(lots)} restants ensuite.**"]
        Path(args.resume).write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"{livres_en_attente} livres à lire, {total} lots en tout (≈ {restant_car / 1150 / 60:.0f} h d'écoute) ; "
          f"{len(lots)} lots pour ce passage.")


if __name__ == "__main__":
    main()
