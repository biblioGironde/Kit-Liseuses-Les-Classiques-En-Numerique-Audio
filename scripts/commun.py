"""Fonctions partagées par les scripts du Kit Les Classiques en audio."""
import csv
import json
import re
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "catalogue.csv"
CACHE = RACINE / "donnees" / "librivox.json"

# librivox : numéro(s) du livre audio sur LibriVox. Plusieurs numéros séparés par une espace
#            = un livre publié en plusieurs parties (Fables livre 1, livre 2…).
#            Vide = pas d'enregistrement LibriVox (la webapp propose alors d'autres sites).
# sections : facultatif, plage de chapitres à garder quand l'enregistrement contient plusieurs
#            œuvres (ex. « 21-36 » pour Eugénie Grandet dans un tome de La Comédie humaine).
# epub     : titre exact du livre dans le catalogue de Kit-Liseuses-Les-Classiques-En-Numerique.
COLONNES = ["siecle", "auteur", "titre", "annee", "librivox", "sections", "epub"]

SIECLES = {
    "15": "XVe siècle — fin du Moyen Âge",
    "16": "XVIe siècle — Renaissance",
    "17": "XVIIe siècle — classicisme",
    "18": "XVIIIe siècle — Lumières",
    "19": "XIXe siècle",
    "20": "XXe siècle",
}

URL_EPUB = "https://bibliogironde.github.io/Kit-Liseuses-Les-Classiques-En-Numerique/"
DEPOT_EPUB = "https://github.com/biblioGironde/Kit-Liseuses-Les-Classiques-En-Numerique"
API_LIBRIVOX = "https://librivox.org/api/feed/audiobooks/"
AGENT = "Kit-Liseuses-Les-Classiques-En-Numerique-Audio/1.0 (biblio.gironde ; https://github.com/biblioGironde)"


def sans_accents(texte):
    """Supprime accents et caractères spéciaux (noms de fichiers sûrs pour les lecteurs MP3)."""
    texte = texte.replace("œ", "oe").replace("Œ", "Oe").replace("æ", "ae")
    texte = re.sub(r"[’‘'`]", " ", texte)
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    texte = re.sub(r"[^A-Za-z0-9 \-]", "", texte)
    return re.sub(r"\s+", " ", texte).strip()


def identifiant(ligne):
    """« voltaire-candide » : sert d'ancre dans l'adresse de la webapp."""
    return sans_accents(f"{ligne['auteur']} {ligne['titre']}").lower().replace(" ", "-")[:80]


def ids_librivox(ligne):
    return [i for i in ligne["librivox"].split() if i.isdigit()]


def lire_catalogue():
    with open(CATALOGUE, newline="", encoding="utf-8") as f:
        lignes = list(csv.DictReader(f))
    for l in lignes:
        for c in COLONNES:
            l[c] = (l.get(c) or "").strip()
    return lignes


def lire_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def ecrire_cache(cache):
    CACHE.parent.mkdir(exist_ok=True)
    donnees = dict(sorted(cache.items(), key=lambda kv: int(kv[0])))
    CACHE.write_text(json.dumps(donnees, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def secondes(duree):
    """« 3:52:57 » ou « 03:02:25 » -> secondes."""
    try:
        parts = [int(p) for p in str(duree).split(":")]
    except ValueError:
        return 0
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def duree_lisible(s):
    h, m = divmod(round(s / 60), 60)
    if h and m:
        return f"{h} h {m:02d}"
    if h:
        return f"{h} h"
    return f"{max(m, 1)} min"
