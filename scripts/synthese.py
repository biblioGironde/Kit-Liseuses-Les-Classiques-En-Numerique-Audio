#!/usr/bin/env python3
"""Lit un livre à voix haute avec une voix de synthèse libre (Pocket TTS de Kyutai).

Le texte vient d'un EPUB exporté de Wikisource (texte du domaine public). Chaque chapitre
devient un fichier MP3, normalisé et étiqueté, placé sous licence CC0.

    python3 scripts/synthese.py --epub "https://ws-export.wmcloud.org/?lang=fr&page=Candide,_ou_l’Optimisme/Garnier_1877&format=epub-3" \\
        --auteur Voltaire --titre Candide --chapitres 1-3 --sortie audio/

    --chapitres   « 1-3 », « 1,4,7 » ou vide pour tout le livre (numérotation des chapitres trouvés)
    --lot N/M     ne traiter qu'un chapitre sur M (pour répartir le travail sur plusieurs machines)
    --liste       afficher les chapitres trouvés, sans rien lire
    --voix        une voix fournie avec le modèle (voir VOIX_LIBRES)

Dépendances : pip install pocket-tts num2words  ;  ffmpeg
"""
import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from posixpath import dirname, join, normpath

# Voix fournies avec Pocket TTS dont l'enregistrement d'origine est libre de droits,
# d'après https://huggingface.co/kyutai/tts-voices (CC0, sauf mention).
# On écarte les voix issues de jeux de données non commerciaux (Expresso, EARS : cosette, jean).
VOIX_LIBRES = {
    "estelle": "voix enregistrée par Kyutai (CC0) — voix française par défaut",
    "marius": "don de voix Unmute (CC0)",
    "javert": "don de voix Unmute (CC0)",
    "caro_davy": "Voice Zero (CC0)",
    "bill_boerst": "Voice Zero (CC0)",
    "peter_yearsley": "Voice Zero (CC0)",
    "stuart_bell": "Voice Zero (CC0)",
}
MODELE = "french_24l"
AGENT = "Kit-Liseuses-Les-Classiques-En-Numerique-Audio/1.0 (biblio.gironde)"

# ---------------------------------------------------------------- lecture de l'EPUB

IGNORER = {"script", "style", "sup", "head", "title", "figure", "figcaption", "table", "nav"}
CLASSES_IGNOREES = ("reference", "references", "mw-references-wrap", "pagenum", "headertemplate",
                    "ws-noexport", "noprint", "mw-cite-backlink", "footnote", "note")
BLOCS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "br", "section", "dd", "dt", "tr"}
TITRES = {"h1", "h2", "h3", "h4"}


class Extracteur(HTMLParser):
    """Transforme un chapitre XHTML en paragraphes, en gardant à part les titres."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pile = []          # pour chaque balise ouverte : True si on l'ignore
        self.morceaux = []      # [(type, texte)]
        self.courant = []
        self.dans_titre = 0

    def _ignore(self):
        return any(self.pile)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        ign = tag in IGNORER or any(c in CLASSES_IGNOREES for c in classes) or a.get("epub:type") in ("footnote", "noteref")
        if tag in BLOCS:
            self._couper()
        if tag in TITRES and not ign:
            self.dans_titre += 1
        if tag == "br":
            self.courant.append(" ")
            return
        self.pile.append(ign)

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.courant.append(" ")

    def handle_endtag(self, tag):
        if tag == "br":
            return
        if self.pile:
            self.pile.pop()
        if tag in BLOCS:
            self._couper(titre=tag in TITRES and self.dans_titre > 0)
        if tag in TITRES and self.dans_titre:
            self.dans_titre -= 1

    def handle_data(self, data):
        if not self._ignore():
            self.courant.append(data)

    def _couper(self, titre=False):
        texte = re.sub(r"\s+", " ", "".join(self.courant)).strip()
        self.courant = []
        if texte:
            self.morceaux.append(("titre" if (titre or self.dans_titre) else "texte", texte))


def lire_epub(chemin):
    """Renvoie [(titre de la table des matières, [(type, texte), …]), …] dans l'ordre de lecture."""
    z = zipfile.ZipFile(chemin)
    conteneur = z.read("META-INF/container.xml").decode()
    opf = re.search(r'full-path="([^"]+)"', conteneur).group(1)
    base = dirname(opf)
    opf_txt = z.read(opf).decode()
    manifeste = {m.group(1): m.group(2) for m in
                 re.finditer(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf_txt)}
    manifeste.update({m.group(2): m.group(1) for m in
                      re.finditer(r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', opf_txt)})
    ordre = re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf_txt)
    chapitres = []
    for idref in ordre:
        href = manifeste.get(idref)
        if not href:
            continue
        nom = normpath(join(base, html.unescape(href)))
        if re.search(r"(title|about|nav|toc|cover|couverture|credits?)\.x?html$", nom, re.I):
            continue
        ex = Extracteur()
        ex.feed(z.read(nom).decode("utf-8", "replace"))
        ex._couper()
        morceaux = [(t, x) for t, x in ex.morceaux if re.search(r"\w", x)]
        textes = [x for t, x in morceaux if t == "texte"]
        if sum(len(x) for _, x in morceaux) < 200:
            continue
        # page de titre ou table des matières : beaucoup de lignes très courtes
        if textes and sum(len(x) for x in textes) / len(textes) < 70 and len(textes) > 8:
            continue
        chapitres.append(morceaux)
    return chapitres


# ---------------------------------------------------------------- préparation du texte

ORDINAUX = {1: "premier"}


def romain_vers_entier(r):
    valeurs = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total, prec = 0, 0
    for c in reversed(r.upper()):
        v = valeurs[c]
        total = total - v if v < prec else total + v
        prec = max(prec, v)
    return total


def en_lettres(n, ordinal=False):
    from num2words import num2words
    if ordinal and n in ORDINAUX:
        return ORDINAUX[n]
    return num2words(n, lang="fr")


ABREVIATIONS = [
    (r"\bMM\.\s", "messieurs "), (r"\bM\.\s", "monsieur "), (r"\bMme\b\.?", "madame"),
    (r"\bMlle\b\.?", "mademoiselle"), (r"\bMgr\b\.?", "monseigneur"), (r"\bSt\.?\s", "saint "),
    (r"\bSte\.?\s", "sainte "), (r"\bDr\.?\s", "docteur "), (r"\betc\.", "et cetera."),
    (r"\bc\.-à-d\.", "c'est-à-dire"), (r"\bp\. ex\.", "par exemple"),
]


def noms_propres(morceaux):
    """Mots écrits avec une majuscule au milieu d'une phrase dans le texte : Candide, Westphalie…"""
    majuscules, minuscules = set(), set()
    for typ, txt in morceaux:
        if typ != "texte":
            continue
        for m in re.finditer(r"(?<![.!?«]\s)(?<!^)\b([A-ZÉÈÀÂÎÔÛÇ][a-zéèêëàâîïôöûüç]+)", txt):
            majuscules.add(m.group(1).lower())
        minuscules.update(re.findall(r"\b[a-zéèêëàâîïôöûüç]+\b", txt))
    return majuscules - minuscules


def preparer_titre(t, noms=frozenset()):
    """« CHAPITRE I. COMMENT CANDIDE… » -> « Chapitre premier. Comment Candide… »"""
    t = re.sub(r"\b(CHAPITRE|Chapitre|CHAP\.|Chap\.|LIVRE|Livre|PARTIE|Partie|ACTE|Acte|SCÈNE|Scène|LETTRE|Lettre)"
               r"\s+([IVXLCDM]+)\b\.?",
               lambda m: f"{m.group(1).capitalize().replace('Chap.', 'Chapitre')} "
                         f"{en_lettres(romain_vers_entier(m.group(2)), ordinal=True)}.", t)
    if re.fullmatch(r"[IVXLCDM]+\.?", t.strip()):
        t = f"{en_lettres(romain_vers_entier(t.strip(' .')), ordinal=True).capitalize()}."
    if sum(c.isupper() for c in t) > 0.6 * max(1, sum(c.isalpha() for c in t)):
        t = t.lower()
        t = re.sub(r"\b\w+\b", lambda m: m.group(0).capitalize() if m.group(0) in noms else m.group(0), t)
        t = re.sub(r"(^|[.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), t)
    return preparer_texte(t)


def preparer_texte(t):
    t = unicodedata.normalize("NFC", t)
    t = t.replace(" ", " ").replace(" ", " ").replace("…", "...").replace("—", ", ").replace("–", ", ")
    for motif, rempl in ABREVIATIONS:
        t = re.sub(motif, rempl, t)
    # siècles et rois : « XVIIIe siècle », « Louis XIV »
    t = re.sub(r"\b([IVXLC]+)e\s+siècle", lambda m: f"{en_lettres(romain_vers_entier(m.group(1)))}ième siècle"
               .replace("unième", "premier").replace("cinqième", "cinquième").replace("neufième", "neuvième"), t)
    t = re.sub(r"\b(Louis|Henri|Charles|François|Philippe|Jean|Léon|Pie|Grégoire|Innocent|Clément)\s+([IVXL]+)\b",
               lambda m: f"{m.group(1)} {en_lettres(romain_vers_entier(m.group(2)), ordinal=True)}", t)
    # nombres en chiffres
    t = re.sub(r"\b(\d{1,3}(?:[  .]\d{3})+|\d+)(er|re|e|ème)?\b",
               lambda m: en_lettres(int(re.sub(r"\D", "", m.group(1))))
               + ("ième" if m.group(2) in ("e", "ème") else "") if not m.group(2) in ("er", "re")
               else ("premier" if m.group(2) == "er" else "première"), t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def preparer_chapitre(morceaux):
    """[(type, texte)] -> [(type, texte prêt à lire)] ; fusionne les titres consécutifs."""
    sortie = []
    noms = noms_propres(morceaux)
    for typ, txt in morceaux:
        prep = preparer_titre(txt, noms) if typ == "titre" else preparer_texte(txt)
        if not prep:
            continue
        if typ == "titre" and sortie and sortie[-1][0] == "titre":
            sep = " " if sortie[-1][1].endswith((".", "!", "?")) else ". "
            sortie[-1] = ("titre", sortie[-1][1] + sep + prep)
        else:
            sortie.append((typ, prep))
    for i, (typ, txt) in enumerate(sortie):
        if typ == "titre" and not txt.endswith((".", "!", "?")):
            sortie[i] = (typ, txt + ".")
    return sortie


def nom_chapitre(morceaux, n):
    for typ, txt in morceaux:
        if typ == "titre":
            return txt[:120]
    return f"Chapitre {n}"


# ---------------------------------------------------------------- synthèse

def plage(texte, total):
    if not texte:
        return list(range(1, total + 1))
    garder = set()
    for m in texte.replace(" ", "").split(","):
        if "-" in m:
            a, b = m.split("-", 1)
            garder.update(range(int(a or 1), int(b or total) + 1))
        elif m:
            garder.add(int(m))
    return sorted(n for n in garder if 1 <= n <= total)


def sans_accents(t):
    t = t.replace("œ", "oe").replace("Œ", "Oe").replace("æ", "ae")
    t = re.sub(r"[’‘'`]", " ", t)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 \-]", "", t)).strip()


def phrases(texte):
    """Découpe un paragraphe en phrases, pour marquer une pause entre elles."""
    morceaux = re.split(r"(?<=[.!?…])\s+(?=[«A-ZÉÈÀÂÎÔÛÇ0-9])", texte)
    return [m for m in morceaux if m.strip()]


def synthetiser(modele, voix, paragraphes, wav, pause=1.0):
    """pause : multiplie la durée des silences (1 = normal, 1.5 = lecture plus posée)."""
    import numpy as np
    import scipy.io.wavfile
    sr = modele.sample_rate
    silence = lambda s: np.zeros(int(sr * s * pause), dtype="float32")
    blocs = [silence(0.4)]
    for typ, txt in paragraphes:
        morceaux = [txt] if typ == "titre" else phrases(txt)
        for i, ph in enumerate(morceaux):
            audio = modele.generate_audio(voix, ph)
            blocs.append(audio.numpy().astype("float32").reshape(-1))
            if i < len(morceaux) - 1:
                blocs.append(silence(0.25))
        blocs.append(silence(1.3 if typ == "titre" else 0.6))
    son = np.concatenate(blocs)
    scipy.io.wavfile.write(wav, sr, son)
    return len(son) / sr


def filtre_vitesse(vitesse):
    """Ralentit (ou accélère) sans changer la hauteur de la voix."""
    if abs(vitesse - 1) < 0.005:
        return ""
    filtres = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    if re.search(r"\brubberband\b", filtres):
        return f"rubberband=tempo={vitesse}:pitchq=quality:transients=smooth,"
    return f"atempo={vitesse},"


def encoder_mp3(wav, mp3, tags, vitesse=1.0):
    meta = []
    for k, v in tags.items():
        meta += ["-metadata", f"{k}={v}"]
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav),
                    "-af", filtre_vitesse(vitesse) + "highpass=f=60,loudnorm=I=-18:TP=-1.5:LRA=11",
                    "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k",
                    "-id3v2_version", "3", *meta, str(mp3)], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--epub", required=True, help="fichier EPUB ou adresse (export Wikisource)")
    p.add_argument("--auteur", default="")
    p.add_argument("--titre", default="")
    p.add_argument("--chapitres", default="", help="« 1-3 », « 2,5 » ; vide = tous")
    p.add_argument("--lot", default="1/1", help="N/M : ne traiter qu'un chapitre sur M, en commençant au N-ième")
    p.add_argument("--voix", default="estelle", choices=sorted(VOIX_LIBRES))
    p.add_argument("--vitesse", type=float, default=1.0,
                   help="vitesse de lecture : 0.9 = 10 %% plus lent (sans changer la voix) ; entre 0.7 et 1.2")
    p.add_argument("--pause", type=float, default=1.0,
                   help="durée des silences entre phrases et paragraphes : 1.5 = 50 %% plus longs")
    p.add_argument("--sortie", default="audio")
    p.add_argument("--liste", action="store_true", help="afficher les chapitres trouvés et s'arrêter")
    p.add_argument("--texte-seul", action="store_true", help="écrire le texte préparé, sans synthèse")
    args = p.parse_args()
    if not 0.7 <= args.vitesse <= 1.2:
        sys.exit("--vitesse doit être comprise entre 0.7 et 1.2")

    epub = args.epub
    if re.match(r"https?://", epub):
        dest = Path(tempfile.mkdtemp()) / "livre.epub"
        req = urllib.request.Request(epub, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=300) as r:
            dest.write_bytes(r.read())
        epub = dest
    chapitres = lire_epub(epub)
    if not chapitres:
        sys.exit("Aucun chapitre trouvé dans l'EPUB.")
    choisis = plage(args.chapitres, len(chapitres))
    n_lot, m_lot = (int(x) for x in args.lot.split("/"))
    choisis = [c for i, c in enumerate(choisis) if i % m_lot == n_lot - 1]

    if args.liste:
        for i, ch in enumerate(chapitres, 1):
            print(f"{i:3}  {nom_chapitre(ch, i)}  ({sum(len(x) for _, x in ch)} car.)")
        return

    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    chiffres = max(2, len(str(len(chapitres))))
    modele = voix = None
    if not args.texte_seul:
        from pocket_tts import TTSModel
        t0 = time.time()
        modele = TTSModel.load_model(language=MODELE)
        voix = modele.get_state_for_audio_prompt(args.voix)
        print(f"Modèle {MODELE} et voix « {args.voix} » chargés en {time.time() - t0:.0f} s", flush=True)

    rapport = []
    for n in choisis:
        prep = preparer_chapitre(chapitres[n - 1])
        nom = nom_chapitre(prep, n)
        base = f"{n:0{chiffres}d} - {sans_accents(nom)[:70]}".strip()
        (sortie / f"{base}.txt").write_text("\n\n".join(t for _, t in prep) + "\n", encoding="utf-8")
        if args.texte_seul:
            print(f"{n:3}  {nom}")
            continue
        t0 = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "c.wav"
            synthetiser(modele, voix, prep, wav, pause=args.pause)
            encoder_mp3(wav, sortie / f"{base}.mp3", {
                "title": nom, "artist": args.auteur, "album": args.titre, "track": f"{n}/{len(chapitres)}",
                "genre": "Livre audio", "language": "fra",
                "copyright": "CC0 1.0 — biblio.gironde",
                "comment": (f"Voix de synthèse (IA) : Pocket TTS © Kyutai, CC BY 4.0, voix {args.voix} "
                            f"({VOIX_LIBRES[args.voix]}). Texte du domaine public (Wikisource). "
                            "Enregistrement placé dans le domaine public (CC0)."),
            }, vitesse=args.vitesse)
            calcul = time.time() - t0
            duree = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                          "csv=p=0", str(sortie / f"{base}.mp3")],
                                         capture_output=True, text=True).stdout or 0)
        rapport.append({"chapitre": n, "titre": nom, "duree": round(duree, 1), "calcul": round(calcul, 1),
                        "caracteres": sum(len(t) for _, t in prep), "fichier": f"{base}.mp3"})
        print(f"{n:3}  {nom[:60]:60}  {duree / 60:5.1f} min d'audio en {calcul / 60:5.1f} min "
              f"(×{duree / calcul:.2f} temps réel)", flush=True)
    if rapport:
        lot = args.lot.replace("/", "-sur-")
        (sortie / f"rapport-{lot}.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
