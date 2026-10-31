#!/usr/bin/env python3
"""Récupère sur LibriVox la description des livres audio du catalogue.

Pour chaque numéro LibriVox de catalogue.csv, le script interroge l'API publique de LibriVox
et enregistre dans donnees/librivox.json la liste des chapitres (titre, durée, lecteur,
adresse du MP3 sur archive.org). La webapp est ensuite construite à partir de ce fichier,
sans dépendre de LibriVox au moment de la publication.

    python3 scripts/actualiser.py              # seulement les livres absents du fichier
    python3 scripts/actualiser.py --tout       # tout récupérer à nouveau
    python3 scripts/actualiser.py --chercher "Maupassant"   # trouver des numéros LibriVox
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from commun import AGENT, API_LIBRIVOX, ecrire_cache, ids_librivox, lire_cache, lire_catalogue, secondes


def appel(params, essais=3):
    url = API_LIBRIVOX + "?" + urllib.parse.urlencode(dict(params, format="json"))
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for n in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r).get("books", [])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if n == essais - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if n == essais - 1:
                raise
        time.sleep(3 * (n + 1))
    return []


def lecteurs(sections):
    noms = []
    for s in sections:
        for r in s.get("readers") or []:
            nom = (r.get("display_name") or "").strip()
            if nom and nom not in noms:
                noms.append(nom)
    return noms


def resume(livre):
    sections = []
    for s in livre.get("sections") or []:
        sections.append({
            "n": int(s.get("section_number") or len(sections) + 1),
            "titre": (s.get("title") or "").strip(),
            "mp3": (s.get("listen_url") or "").replace("http://", "https://"),
            "duree": int(s.get("playtime") or 0),
            "lecteurs": [r["display_name"] for r in s.get("readers") or [] if r.get("display_name")],
        })
    complet = bool(sections) and all(s["mp3"] for s in sections)
    return {
        "titre": livre.get("title", ""),
        "langue": livre.get("language", ""),
        "auteurs": [f"{a.get('first_name', '')} {a.get('last_name', '')}".strip() for a in livre.get("authors") or []],
        "page": livre.get("url_librivox", ""),
        "archive": livre.get("url_iarchive", ""),
        "zip": (livre.get("url_zip_file") or "").replace(" ", "%20"),
        "rss": livre.get("url_rss", ""),
        "texte": livre.get("url_text_source", ""),
        "duree": secondes(livre.get("totaltime")) or sum(s["duree"] for s in sections),
        "lecteurs": lecteurs(livre.get("sections") or []),
        "complet": complet,
        "sections": sections,
    }


def chercher(terme):
    vus = {}
    for cle in ("author", "title"):
        for prefixe in ("", "^"):
            for b in appel({cle: prefixe + terme, "limit": 200}):
                if b.get("language") == "French":
                    vus[b["id"]] = b
    if not vus:
        print("Rien trouvé en français. Essayez le nom de famille seul, ou le début du titre sans article.")
    for b in sorted(vus.values(), key=lambda b: b["title"]):
        auteurs = ", ".join(f"{a['first_name']} {a['last_name']}".strip() for a in b["authors"])
        print(f"{b['id']:>6}  {b['title']}  —  {auteurs}  ({b['totaltime'] or 'en cours'})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tout", action="store_true", help="récupérer à nouveau tous les livres")
    p.add_argument("--chercher", metavar="TERME", help="chercher un auteur ou un titre sur LibriVox (en français)")
    args = p.parse_args()

    if args.chercher:
        chercher(args.chercher)
        return

    cache = lire_cache()
    voulus = []
    for ligne in lire_catalogue():
        for i in ids_librivox(ligne):
            if i not in voulus:
                voulus.append(i)

    a_faire = [i for i in voulus if args.tout or i not in cache or not cache[i].get("complet")]
    print(f"{len(voulus)} livres LibriVox dans le catalogue, {len(a_faire)} à récupérer.")
    erreurs = 0
    for n, i in enumerate(a_faire, 1):
        try:
            livres = appel({"id": i, "extended": 1})
        except Exception as e:  # noqa: BLE001
            print(f"  [{n}/{len(a_faire)}] {i} : erreur ({e})")
            erreurs += 1
            continue
        if not livres:
            print(f"  [{n}/{len(a_faire)}] {i} : introuvable sur LibriVox")
            erreurs += 1
            continue
        cache[i] = resume(livres[0])
        etat = "" if cache[i]["complet"] else "  ⚠ enregistrement pas encore terminé"
        print(f"  [{n}/{len(a_faire)}] {i} : {cache[i]['titre']} ({len(cache[i]['sections'])} chapitres){etat}")
        time.sleep(0.5)

    # On retire du fichier les livres qui ne sont plus dans le catalogue.
    for i in list(cache):
        if i not in voulus:
            del cache[i]
    ecrire_cache(cache)
    print("Terminé." if not erreurs else f"Terminé avec {erreurs} erreur(s).")
    sys.exit(1 if erreurs and erreurs == len(a_faire) else 0)


if __name__ == "__main__":
    main()
