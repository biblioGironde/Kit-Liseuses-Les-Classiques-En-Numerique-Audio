#!/usr/bin/env python3
"""Construit le site publié sur GitHub Pages, et SOURCES.md.

    python3 scripts/construire.py

Le site est écrit dans le dossier site/ :
    index.html         la webapp (écoute, téléchargement, copie sur lecteur MP3)
    catalogue.json     la liste des livres
    livres/<id>.json   les chapitres de chaque livre (chargés à la demande)

Les fichiers audio ne sont pas copiés : ils restent hébergés par LibriVox sur archive.org.
"""
import json
import re
import shutil
import urllib.parse

from commun import (DEPOT_EPUB, RACINE, SIECLES, URL_EPUB, duree_lisible, identifiant, ids_librivox,
                    lire_cache, lire_catalogue)

SITE = RACINE / "site"


def plage(texte, total):
    """« 21-36 » -> {21, …, 36} ; vide -> tous."""
    if not texte:
        return None
    garder = set()
    for morceau in texte.replace(" ", "").split(","):
        if "-" in morceau:
            a, b = morceau.split("-", 1)
            garder.update(range(int(a), int(b or total) + 1))
        elif morceau:
            garder.add(int(morceau))
    return garder


def recherche_litteratureaudio(ligne):
    nom = ligne["auteur"].split()[-1] if ligne["auteur"] != "Anonyme" else ""
    return "https://www.litteratureaudio.com/?s=" + urllib.parse.quote_plus(f"{ligne['titre']} {nom}".strip())


def construire_livre(ligne, cache):
    ids = ids_librivox(ligne)
    parties, lecteurs, duree, nb = [], [], 0, 0
    for i in ids:
        lv = cache.get(i)
        if not lv or not lv.get("complet"):
            return None
        garder = plage(ligne["sections"], len(lv["sections"])) if len(ids) == 1 else None
        chapitres = []
        for pos, s in enumerate(lv["sections"], 1):
            if garder and pos not in garder:
                continue
            titre = re.sub(r"^(Chapter|Section|Part)\s*", lambda m: {"Chapter": "Chapitre ", "Section": "Section ",
                           "Part": "Partie "}[m.group(1)], s["titre"]) if s["titre"] else f"Chapitre {pos}"
            chapitres.append({"t": titre, "mp3": s["mp3"], "d": s["duree"],
                              "l": ", ".join(s["lecteurs"])})
            for nom in s["lecteurs"]:
                if nom not in lecteurs:
                    lecteurs.append(nom)
        d = sum(c["d"] for c in chapitres)
        duree += d
        nb += len(chapitres)
        parties.append({
            "titre": lv["titre"] if len(ids) > 1 else "",
            "librivox": lv["page"], "archive": lv["archive"], "texte": lv["texte"],
            # le ZIP contient tout l'enregistrement : on ne le propose pas pour un extrait
            "zip": "" if garder else lv["zip"],
            "rss": "" if garder else lv["rss"],
            "duree": d, "chapitres": chapitres,
        })
    return {"parties": parties, "lecteurs": lecteurs, "duree": duree, "nb": nb}


def main():
    lignes = lire_catalogue()
    cache = lire_cache()
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "livres").mkdir(parents=True)

    catalogue, manquants, sources = [], [], []
    for ligne in lignes:
        ident = identifiant(ligne)
        entree = {
            "id": ident, "siecle": ligne["siecle"], "auteur": ligne["auteur"], "titre": ligne["titre"],
            "annee": ligne["annee"], "epub": ligne["epub"], "autres": recherche_litteratureaudio(ligne),
        }
        if ids_librivox(ligne):
            livre = construire_livre(ligne, cache)
            if not livre:
                manquants.append(ligne)
                continue
            (SITE / "livres" / f"{ident}.json").write_text(
                json.dumps(livre, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            entree.update(duree=livre["duree"], nb=livre["nb"], lecteurs=livre["lecteurs"][:6],
                          nbLecteurs=len(livre["lecteurs"]))
            sources.append((ligne, livre))
        catalogue.append(entree)

    donnees = {"siecles": SIECLES, "epub": URL_EPUB, "livres": catalogue}
    (SITE / "catalogue.json").write_text(json.dumps(donnees, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
    shutil.copy(RACINE / "app" / "index.html", SITE / "index.html")
    (SITE / ".nojekyll").write_text("")
    ecrire_sources(sources)

    ecoute = sum(1 for e in catalogue if "duree" in e)
    total = sum(e.get("duree", 0) for e in catalogue)
    print(f"Site construit : {ecoute} livres audio ({duree_lisible(total)} d'écoute), "
          f"{len(catalogue) - ecoute} titres renvoyant vers d'autres sites.")
    for l in manquants:
        print(f"  ⚠ {l['auteur']} — {l['titre']} : numéro LibriVox absent de donnees/librivox.json "
              f"(lancer scripts/actualiser.py)")


def ecrire_sources(sources):
    lignes = [
        "# Sources et droits",
        "",
        "*Fichier généré par `scripts/construire.py`, ne pas modifier à la main.*",
        "",
        "Tous les enregistrements proviennent de [LibriVox](https://librivox.org), dont les bénévoles",
        "lisent des textes du domaine public et placent leurs enregistrements dans le **domaine public**.",
        "Les fichiers MP3 sont hébergés par LibriVox sur [archive.org](https://archive.org) ; ce dépôt",
        "ne contient que leur catalogue. Les textes eux-mêmes sont dans le domaine public en France",
        "(auteurs morts depuis plus de 70 ans) et aux États-Unis (publiés avant 1931).",
        "",
        f"Le texte de la plupart de ces œuvres est disponible en EPUB dans [Kit-Liseuses-Les-Classiques-En-Numerique]({DEPOT_EPUB}).",
        "",
    ]
    siecle = None
    for ligne, livre in sources:
        if ligne["siecle"] != siecle:
            siecle = ligne["siecle"]
            lignes += ["", f"## {SIECLES.get(siecle, siecle)}", ""]
        liens = []
        for p in livre["parties"]:
            nom = p["titre"] or "LibriVox"
            liens.append(f"[{nom}]({p['librivox']})")
        lus = ", ".join(livre["lecteurs"][:8]) + (" et d'autres" if len(livre["lecteurs"]) > 8 else "")
        extrait = f" — chapitres {ligne['sections']} de l'enregistrement" if ligne["sections"] else ""
        lignes.append(f"- **{ligne['auteur']}**, *{ligne['titre']}* ({duree_lisible(livre['duree'])}{extrait}) — "
                      f"lu par {lus} — {' · '.join(liens)}")
    lignes += ["", "## Autres sites de livres audio gratuits", "",
               "Ils ne sont pas repris dans ce dépôt : la webapp y renvoie par un lien.", "",
               "- [Littérature audio](https://www.litteratureaudio.com) : très grand catalogue, écoute gratuite ; "
               "les enregistrements restent la propriété de leurs lecteurs (pas de redistribution sans leur accord).",
               "- [Audiocité](https://www.audiocite.net) : enregistrements sous licence Creative Commons ou Art libre ; "
               "la licence varie d'un livre à l'autre, à vérifier sur chaque fiche avant toute réutilisation.",
               ""]
    (RACINE / "SOURCES.md").write_text("\n".join(lignes), encoding="utf-8")


if __name__ == "__main__":
    main()
