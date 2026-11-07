# Kit Liseuses — Les Classiques en numérique (audio)

Des livres audio gratuits et libres de droits des grands classiques de la littérature
française, du XVIe au XXe siècle, et une webapp pour les écouter, les télécharger ou les
copier sur un lecteur MP3 ou une clé USB.

**Webapp :** https://bibliogironde.github.io/Kit-Liseuses-Les-Classiques-En-Numerique-Audio/

C'est le pendant audio de [Kit-Liseuses-Les-Classiques-En-Numerique](https://github.com/biblioGironde/Kit-Liseuses-Les-Classiques-En-Numerique)
(les mêmes œuvres en EPUB pour les liseuses). Quand le texte d'un livre audio y est
disponible, la webapp le signale par la mention « Texte ».

## Ce que fait la webapp

- **Écouter** directement dans le navigateur, sur ordinateur, tablette ou téléphone,
  chapitre par chapitre. La page retient où l'on s'est arrêté (« Reprendre »).
  Vitesse réglable, retour et avance de 30 secondes, commandes sur l'écran verrouillé du téléphone.
- **Copier sur un lecteur MP3 ou une clé USB** (Chrome ou Edge sur ordinateur) : on
  branche l'appareil, on le choisit dans la fenêtre, et les chapitres sont copiés dans
  `Livres audio/Auteur - Titre/01 - ….mp3`. Une copie interrompue reprend là où elle s'était arrêtée.
- **Télécharger** tout le livre en ZIP, ou un chapitre à la fois.
- **Écouter en podcast** : chaque livre a un flux RSS LibriVox à coller dans une appli de podcasts.
- Pour les titres du catalogue EPUB qui n'ont pas encore d'enregistrement libre, un lien
  renvoie vers la recherche de [Littérature audio](https://www.litteratureaudio.com).

Chaque livre a sa propre adresse (par exemple `…/Kit-Liseuses-Les-Classiques-En-Numerique-Audio/#voltaire-candide`),
pratique pour un QR code sur une affiche ou un marque-page.

## D'où viennent les enregistrements

Tous les livres audio viennent de **[LibriVox](https://librivox.org)** : des bénévoles du monde
entier y lisent des textes du domaine public et placent leurs enregistrements dans le
**domaine public**. On peut donc les écouter, les copier, les prêter et les diffuser librement,
y compris en bibliothèque.

Les fichiers MP3 restent hébergés par LibriVox sur archive.org : ce dépôt ne contient que le
catalogue (quelques centaines de Ko). Un roman pèse souvent plusieurs centaines de Mo, ce que
GitHub ne permet pas de stocker confortablement.

Les autres sites de livres audio gratuits ne sont pas repris dans le dépôt :

| Site | Écoute | Redistribution |
|---|---|---|
| [LibriVox](https://librivox.org) | gratuite | libre (domaine public) — **la source de ce dépôt** |
| [Audiocité](https://www.audiocite.net) | gratuite | selon la licence de chaque livre (Creative Commons, Art libre) |
| [Littérature audio](https://www.litteratureaudio.com) | gratuite | non : les enregistrements restent la propriété des lecteurs |

Le détail des lecteurs de chaque livre est dans [`SOURCES.md`](SOURCES.md).

## Organisation du dépôt

```
catalogue.csv            la liste des livres (à modifier pour en ajouter)
donnees/librivox.json    les chapitres de chaque livre, récupérés sur LibriVox (généré)
app/index.html           la webapp
scripts/actualiser.py    récupère les fiches LibriVox ; cherche un livre sur LibriVox
scripts/construire.py    génère le site et SOURCES.md
SOURCES.md               lecteurs et liens LibriVox de chaque livre (généré)
```

## Ajouter un livre

1. Trouver son numéro LibriVox. Soit sur le site (le numéro figure dans l'adresse du flux RSS
   de la fiche, par exemple `librivox.org/rss/1870`), soit avec le script :

   ```bash
   python3 scripts/actualiser.py --chercher "Maupassant"
   python3 scripts/actualiser.py --chercher "Germinal"
   ```

2. Ajouter une ligne à `catalogue.csv` :

   | colonne | contenu |
   |---|---|
   | `siecle` | 15 à 20 |
   | `auteur`, `titre`, `annee` | comme dans le catalogue EPUB |
   | `librivox` | le numéro LibriVox. Plusieurs numéros séparés par une espace pour un livre publié en plusieurs parties (les 12 livres des *Fables*, les tomes des *Mémoires d'outre-tombe*…). Vide : pas d'enregistrement, la webapp renvoie vers Littérature audio. |
   | `sections` | facultatif : les chapitres à garder quand l'enregistrement réunit plusieurs œuvres. Par exemple `21-36` pour *Eugénie Grandet*, lu dans un tome de *La Comédie humaine*. |
   | `epub` | le titre exact du livre dans le catalogue de Kit-Liseuses-Les-Classiques-En-Numerique, s'il y est |

3. Pousser sur `main`. L'action GitHub récupère la fiche LibriVox, reconstruit la webapp et met à
   jour `SOURCES.md`.

Ne mettre que des œuvres d'auteurs morts avant 1956 (domaine public en France) ; LibriVox,
de son côté, n'enregistre que des œuvres publiées avant 1931 (domaine public aux États-Unis).
LibriVox enregistre aussi des traductions françaises d'auteurs étrangers : vérifier que le
traducteur est lui aussi mort depuis plus de 70 ans.

Un enregistrement encore en cours sur LibriVox (chapitres manquants) est ignoré jusqu'à ce
qu'il soit terminé : il apparaîtra tout seul à la publication suivante.

## Voix de synthèse (en test)

Pour remplacer les lectures LibriVox de qualité inégale, le dépôt peut faire lire un livre
par une voix de synthèse libre, **Pocket TTS** de [Kyutai](https://kyutai.org) (modèle français,
licence CC BY 4.0), directement sur les machines gratuites de GitHub Actions.

*Actions → Lire un livre en voix de synthèse → Run workflow*, puis indiquer :

- l'adresse de l'EPUB exporté de **Wikisource** (texte du domaine public), de la forme
  `https://ws-export.wmcloud.org/?lang=fr&page=<titre de la page Wikisource>&format=epub-3` ;
- les chapitres à lire (`1-3`, ou vide pour tout le livre) et le nombre de machines en parallèle ;
- la vitesse (`0.9` par défaut : 10 % plus lent que la voix d'origine, sans changer son timbre)
  et la longueur des silences entre phrases et paragraphes (`1.2` par défaut) ;
- la voix : seules les voix de Pocket TTS dont l'enregistrement d'origine est libre (CC0) sont proposées
  (`estelle`, voix française par défaut, `marius`, `javert`, `caro_davy`…).

Le script `scripts/synthese.py` découpe l'EPUB en chapitres, prépare le texte pour la lecture
(chiffres romains et nombres en toutes lettres, abréviations, titres en majuscules), lit chaque
chapitre, normalise le volume et produit des MP3 étiquetés « voix de synthèse ». Le bilan de
l'action indique la vitesse obtenue ; les MP3 sont téléchargeables dans l'onglet de l'action,
ou publiés dans une Release si la case est cochée.

Les fichiers produits sont placés sous **CC0** (domaine public), avec la mention
« Pocket TTS © Kyutai, CC BY 4.0 ».

Pour voir les chapitres d'un EPUB et le texte qui sera lu, sans rien générer :

```bash
pip install num2words
python3 scripts/synthese.py --epub "<adresse>" --liste
python3 scripts/synthese.py --epub "<adresse>" --chapitres 1 --texte-seul --sortie essai/
```

## Tester en local

Il faut Python 3.8 ou plus récent, sans bibliothèque à installer.

```bash
python3 scripts/actualiser.py      # seulement les livres nouveaux du catalogue
python3 scripts/construire.py
cd site && python3 -m http.server 8000   # puis ouvrir http://localhost:8000
```

`python3 scripts/actualiser.py --tout` récupère à nouveau toutes les fiches (utile si LibriVox
a corrigé un enregistrement). On peut aussi le faire depuis GitHub : *Actions → Publier le
catalogue → Run workflow*, en cochant la case.

## Activer GitHub Pages (une seule fois)

Dans le dépôt : *Settings → Pages → Build and deployment → Source : GitHub Actions*.
