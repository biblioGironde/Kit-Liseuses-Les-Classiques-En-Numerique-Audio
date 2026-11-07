#!/usr/bin/env python3
"""Trouve, pour chaque livre du catalogue, le texte Wikisource à faire lire par la voix de synthèse.

Le texte vient du catalogue de Kit-Liseuses-Les-Classiques-En-Numerique (colonne « epub » de
catalogue.csv) :
  - si l'EPUB du dépôt des liseuses vient de Wikisource, on reprend ce fichier tel quel ;
  - s'il vient de la Bibliothèque numérique romande (licence non commerciale), on va chercher
    le même texte sur Wikisource, pour que l'enregistrement puisse être placé sous CC0.

Le résultat est écrit dans donnees/textes.csv. Chaque EPUB est téléchargé dans textes/ et
vérifié : nombre de chapitres, nombre de caractères, durée d'écoute estimée.

    python3 scripts/textes.py              # complète les lignes manquantes
    python3 scripts/textes.py --tout       # tout revérifier

Pour imposer une édition Wikisource, remplir la colonne « page » de donnees/textes.csv
(ex. « Le Père Goriot (1910) ») et effacer le statut : la ligne sera revérifiée.
"""
import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from commun import RACINE, identifiant, lire_catalogue  # noqa: E402
from synthese import lire_epub  # noqa: E402

DEPOT_EPUB = "biblioGironde/Kit-Liseuses-Les-Classiques-En-Numerique"
BRUT = f"https://raw.githubusercontent.com/{DEPOT_EPUB}/main/"
API_WS = "https://fr.wikisource.org/w/api.php"
WSEXPORT = "https://ws-export.wmcloud.org/"
FICHIER = RACINE / "donnees" / "textes.csv"
CACHE = RACINE / "textes"
COLONNES = ["id", "auteur", "titre", "origine", "page", "epub", "statut", "chapitres", "caracteres", "heures", "remarque"]
AGENT = "Kit-Liseuses-Les-Classiques-En-Numerique-Audio/1.0 (biblio.gironde)"
CAR_PAR_MINUTE = 1150  # mesuré sur Candide : environ 1 150 caractères par minute d'écoute à la vitesse 0,9

# Éditions Wikisource choisies quand la page de l'œuvre renvoie vers plusieurs éditions.
EDITIONS = {
    "Le Misanthrope": "Le Misanthrope/Édition Louandre, 1910",
    "Tartuffe": "Tartuffe ou l’Imposteur/Édition Louandre, 1910",
    "Candide": "Candide, ou l’Optimisme/Garnier 1877",
    "Le Comte de Monte-Cristo (tome 1)": "Le Comte de Monte-Cristo",
}


def requete(url, essais=4):
    for n in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or n == essais - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if n == essais - 1:
                raise
        time.sleep(15 * (n + 1))


def ws_api(**params):
    params.update(format="json", formatversion="2")
    return json.loads(requete(API_WS + "?" + urllib.parse.urlencode(params)))


def ws_resoudre(page):
    """Renvoie (page à exporter, remarque). Choisit une édition si la page est une page d'homonymie."""
    d = ws_api(action="query", titles=page, redirects=1, prop="pageprops|links", pllimit=500, plnamespace=0)
    p = d["query"]["pages"][0]
    if p.get("missing"):
        return None, "page Wikisource introuvable"
    titre = p["title"]
    if "disambiguation" not in p.get("pageprops", {}):
        return titre, ""
    editions = [l["title"] for l in p.get("links", [])
                if l["title"].startswith((titre + " (", titre + "/")) and not l["title"].endswith(("/Éditions", "/Concordance"))]
    if not editions:
        return None, "plusieurs éditions sur Wikisource : choisir la page à la main"
    # on préfère la plus récente (orthographe plus proche de l'actuelle)
    def annee(t):
        m = re.findall(r"(1[5-9]\d\d)", t)
        return int(m[-1]) if m else 0
    choix = sorted(editions, key=annee)[-1]
    return choix, f"édition choisie automatiquement parmi {len(editions)} : à vérifier"


def ws_export(page):
    return WSEXPORT + "?" + urllib.parse.urlencode({"lang": "fr", "page": page, "format": "epub-3", "fonts": ""})


def catalogue_epub():
    texte = requete(BRUT + "catalogue.csv").decode("utf-8")
    return list(csv.DictReader(io.StringIO(texte)))


def nom_fichier_epub(ligne):
    from commun import sans_accents
    return f"epub/{ligne['siecle']}/{sans_accents(ligne['auteur'])} - {sans_accents(ligne['titre'])}.epub"


def lire_fichier():
    if not FICHIER.exists():
        return {}
    with open(FICHIER, newline="", encoding="utf-8") as f:
        return {l["id"]: l for l in csv.DictReader(f)}


def ecrire_fichier(lignes):
    FICHIER.parent.mkdir(exist_ok=True)
    with open(FICHIER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES)
        w.writeheader()
        for l in lignes:
            w.writerow({c: l.get(c, "") for c in COLONNES})


def verifier(ligne):
    """Télécharge l'EPUB et compte chapitres et caractères."""
    CACHE.mkdir(exist_ok=True)
    chemin = CACHE / f"{ligne['id']}.epub"
    if not chemin.exists() or chemin.stat().st_size < 1000:
        chemin.write_bytes(requete(ligne["epub"]))
    chapitres = lire_epub(chemin)
    car = sum(len(x) for ch in chapitres for _, x in ch)
    ligne.update(chapitres=str(len(chapitres)), caracteres=str(car), heures=f"{car / CAR_PAR_MINUTE / 60:.1f}")
    if car < 8000:
        return "texte trop court : la page Wikisource n'est sans doute qu'un sommaire"
    return ""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tout", action="store_true", help="tout revérifier")
    args = p.parse_args()

    existant = lire_fichier()
    epubs = catalogue_epub()
    sortie = []
    for ligne in lire_catalogue():
        if not ligne["epub"]:
            continue
        ident = identifiant(ligne)
        e = next((x for x in epubs if x["titre"] == ligne["epub"] and x["auteur"] == ligne["auteur"]), None)
        if not e or "indisponible" in e["statut"]:
            continue
        l = existant.get(ident, {})
        l.update(id=ident, auteur=ligne["auteur"], titre=ligne["titre"])
        if l.get("statut") == "ok" and not args.tout:
            sortie.append(l)
            continue
        try:
            if not l.get("page") and e["source"] == "wikisource" and e["statut"] == "ok":
                l.update(origine="Wikisource (EPUB du dépôt des liseuses)", page=e["wikisource"],
                         epub=BRUT + urllib.parse.quote(nom_fichier_epub(e)))
                remarque = ""
            else:
                page = l.get("page") or EDITIONS.get(ligne["epub"]) or e["wikisource"]
                tome = re.search(r"\(tome (\d+)\)", ligne["epub"])
                if tome and "Misérables" in ligne["epub"]:
                    page = f"Les Misérables/Tome {tome.group(1)}"
                page, remarque = ws_resoudre(page)
                if not page:
                    l.update(statut=remarque)
                    sortie.append(l)
                    print(f"  ✗ {ligne['auteur']} — {ligne['titre']} : {remarque}")
                    continue
                l.update(origine="Wikisource (export)", page=page, epub=ws_export(page))
                time.sleep(1)
            probleme = verifier(l)
            l["statut"] = probleme or "ok"
            l["remarque"] = remarque
        except Exception as ex:  # noqa: BLE001
            l["statut"] = f"erreur : {ex}"
        sortie.append(l)
        print(f"  {'✓' if l['statut'] == 'ok' else '!'} {ligne['auteur']} — {ligne['titre']} : {l.get('page')} "
              f"({l.get('chapitres') or '?'} chapitres, {l.get('heures') or '?'} h) {'' if l['statut'] == 'ok' else l['statut']} {l.get('remarque', '')}",
              flush=True)
        ecrire_fichier(sortie + [x for k, x in existant.items() if k not in {s['id'] for s in sortie}])
    ecrire_fichier(sortie)
    ok = [l for l in sortie if l["statut"] == "ok"]
    print(f"\n{len(ok)} livres prêts ({sum(float(l['heures'] or 0) for l in ok):.0f} h d'écoute estimées), "
          f"{len(sortie) - len(ok)} à vérifier.")


if __name__ == "__main__":
    main()
