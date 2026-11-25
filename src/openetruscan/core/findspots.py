"""Findspot strings → places, precision, and current location.

The CIE records findspots as Latin phrases (``Clusii in agro``, ``Clusino``,
``Ager Clusinus``) and often appends where the object was kept when the
editor saw it (``nunc in museo publico Clusino``). Some strings name only
the collection (``in museo publico Clusino GA.``), and a few are not places
at all but object descriptions copied into the wrong field.

:func:`classify_findspot` splits a string into

* ``role`` — ``findspot``, ``current_location``, ``findspot_and_current``,
  ``description`` or ``unknown``;
* ``place_key`` — a key into ``reference/places.csv`` (Pleiades-backed);
* ``precision`` — ``site``, ``city``, ``territory`` or ``region``;
* ``current_location`` — the custody clause, verbatim.

The rules are deliberately narrow. A string they do not recognise is
``unknown``, never guessed; ``reference/findspot_gazetteer.csv`` records the
outcome for every string in the corpus and takes manual overrides.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PRECISIONS = ("site", "city", "territory", "region")
ROLES = ("findspot", "current_location", "findspot_and_current", "description", "unknown")

#: Radius (metres) of a place attribution at each precision, around the
#: place's representative point. Nothing writes it to a record.
UNCERTAINTY_M = {"site": 1_000, "city": 3_000, "territory": 20_000, "region": 75_000}

# Place-name stems as they appear in CIE Latin, Larth English and Italian.
# Order matters only where stems overlap (Volsinii Veteres before Volsinii).
_PLACE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("clusium", r"clus(?:ii|ium|ino|inus|ina|inae|inis|io|i)\b|chiusi(?:na|no)?\b"),
    ("perusia", r"perusi(?:a|ae|no|nus|na|nis|i)\b|perugia\b"),
    ("volaterrae", r"volaterr(?:is|ae|as|arum|ano|anus|ana|a)\b|volterra\b"),
    ("tarquinii", r"tarquini(?:i|is|ensis|ensi|a|o)?\b|corneto\b"),
    ("caere", r"caer(?:e|ite|etanus|etano|etana|etani)\b|cerveteri\b"),
    ("volsinii_veteres", r"orvieto\b|urbs ?vetus\b|volsini(?:i|is|ensis|ensi|um)?\b"),
    ("volsinii", r"bolsena\b"),
    ("vulci", r"vulc(?:i|entanus|entano|ente)\b|volc(?:i|entanus|entano|ente)\b"),
    ("arretium", r"arreti(?:um|o|nus|no|na|i)\b|arezzo\b"),
    ("cortona", r"corton(?:a|ae|ensis|ensi|ese)\b"),
    ("veii", r"vei(?:i|is|entanus|ente)\b|veio\b"),
    ("faesulae", r"faesul(?:ae|is|anus|ano)\b|fiesole\b"),
    ("rusellae", r"rusell(?:ae|is|anus|ano)\b|roselle\b"),
    ("vetulonia", r"vetuloni(?:a|ae|ensis)\b"),
    ("populonia", r"populoni(?:a|ae|um|ensis)\b"),
    ("saena", r"\bsaen(?:a|ae|am|ensis|ensi)\b|\bsien(?:a|am)\b|\bsenensis\b"),
    ("florentia", r"florenti(?:a|ae|no|nus|na)\b|firenze\b"),
    ("pisae", r"\bpis(?:ae|is|anus|ano)\b"),
    ("spina", r"\bspina\b"),
    ("adria", r"\b(?:h?atria|adria)\b"),
    ("pyrgi", r"\bpyrgi\b"),
    ("ager_faliscus", r"falisc(?:us|o|a|i)\b"),
    ("falerii", r"\bfaleri(?:i|is)\b"),
    ("felsina", r"\bfelsina\b|\bbononi(?:a|ae)\b|\bbologna\b"),
    ("kainua", r"\bmarzabotto\b"),
    ("placentia", r"\bplacenti(?:a|ae)\b|\bpiacenza\b"),
    ("capua", r"\bcapu(?:a|ae)\b"),
    ("nola", r"\bnola\b"),
    ("pontecagnano", r"\bpontecagnano\b"),
    ("suana", r"\bsuana\b|\bsovana\b"),
    ("tuscana", r"\btuscan(?:a|ia|iensis)\b"),
    ("orcla", r"\bnorchia\b"),
    ("blera", r"\bblera\b|\bbieda\b"),
    ("musarna", r"\bmusarna\b"),
    ("visentium", r"\bvisenti(?:um|o)\b|\bbisenzio\b"),
    ("graviscae", r"\bgraviscae\b|\bgravisca\b"),
    ("ferentium", r"\bferenti(?:um|o)\b|\bferento\b"),
    ("horta", r"\bhorta\b|\borte\b"),
    ("saturnia", r"\bsaturnia\b"),
    ("heba", r"\bheba\b|\bmagliano\b"),
    ("cosa", r"\bcosa\b|\bansedonia\b"),
    ("sarteano", r"\bsarteano\b"),
    ("cetona", r"\bcetona\b"),
    ("castiglione_del_lago", r"castiglione del lago"),
    ("poggio_civitate", r"poggio civitate|\bmurlo\b"),
    ("asciano", r"\basciano\b"),
    ("capena", r"\bcapen(?:a|as|ate|atis)\b"),
    ("narce", r"\bnarce\b"),
    ("nepet", r"\bnepi\b|\bnepet\b"),
    ("sutrium", r"\bsutri(?:um)?\b"),
    ("campania", r"\bcampani(?:a|ae)\b|^campana$"),
    ("aemilia", r"\baemili(?:a|ae)\b"),
    ("latium", r"\blati(?:um|o)\b"),
    ("etruria", r"\betruri(?:a|ae)\b"),
)
_COMPILED = tuple((k, re.compile(p)) for k, p in _PLACE_PATTERNS)

_TERRITORY = re.compile(
    r"\bin agro\b|\bager\b|\bagri\b|\bagro\b|\bcum agro\b|\bterritori|\bprope\b|"
    r"\bnon procul\b|\bhaud procul\b|\bin vicinia\b|\bvicinia\b|\bdintorni\b|\bnei pressi\b|"
    r"\bcontrada\b|\bcapenas\b"
)
_CUSTODY = re.compile(
    r"\bin museo\b|\bmuseo\b|\bmusei\b|\bmus\.|\bin collectione\b|\bcollection|\bin aedibus\b|"
    r"\bin villa\b|\bnella villa\b|\bin horto\b|\bapud\b|\bin bibliotheca\b|\bin palatio\b|"
    r"\bin domo\b|\bin ecclesia\b|\bin episcopio\b|\bhorto episcopii\b"
)
_NUNC = re.compile(r"\bnunc\b")
# Collections named only by the city adjective of a museum ("Parisiensi",
# "in museo Mannhemiensi"): the object is kept there, it was not found there.
_MUSEUM_CITY = re.compile(
    r"^(?:in museo )?(?:parisi(?:ensi|is)|mannhemiensi|berolinensi|londinensi|britannico|"
    r"vindobonensi|monacensi|petropolitano|hafniensi|oxoniensi|panormitano|neapolitano|"
    r"lugdunensi|vaticano)\b"
)
# Places that are not in reference/places.csv but whose territory is not in
# doubt: (pattern, place key, note).
_TERRITORY_ALIASES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"citta della pieve"), "clusium", "Città della Pieve, in the ager Clusinus."),
    (
        re.compile(r"montepulciano|mons politianus"),
        "clusium",
        "Montepulciano, in the ager Clusinus.",
    ),
    (re.compile(r"chianciano"), "clusium", "Chianciano, in the ager Clusinus."),
    (re.compile(r"\bcasole\b"), "volaterrae", "Casole d'Elsa, in the ager Volaterranus."),
)
_OLIM = re.compile(r"\bolim\b")
_DESCRIPTION = re.compile(
    r"\b(?:ossuari(?:um|i)|operculum|urna|cippus|tegula|olla|patera|litteris|ex lapide|"
    r"ex marmore|fictil|delineat|insculpt|incis|latet|periit|perisse)\b"
)
_UNKNOWN = re.compile(r"\bunknown\b|\bincert|\bignot")
# Editors' sigla that close many CIE custody notes: "GA." (Gamurrini),
# "DA." (Danielsson), "FA." (Fabretti), "(succ.)".
_TRAILING_SIGLA = re.compile(r"(?:\s*(?:\(succ\.\)|[A-Z]{2,3}\.|\(\d{4}\)))+\s*$")


@dataclass(frozen=True)
class FindspotClass:
    role: str
    place_key: str | None
    precision: str | None
    current_location: str | None
    basis: str  # "rule" or "manual"
    note: str = ""


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _first_place(folded: str) -> str | None:
    best: tuple[int, str] | None = None
    for key, rx in _COMPILED:
        m = rx.search(folded)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), key)
    return best[1] if best else None


def classify_findspot(raw: str, places_kind: dict[str, str] | None = None) -> FindspotClass:
    """Classify one findspot string. ``places_kind`` maps place key → kind.

    Precision is ``territory`` when the phrase says so (``in agro``,
    ``Ager …``, ``prope``), otherwise the kind of the place itself
    (``city``, ``site`` or ``region``).
    """
    text = (raw or "").strip()
    if not text:
        return FindspotClass("unknown", None, None, None, "rule")
    folded = _fold(text)
    kinds = places_kind or {}

    # Split off the custody clause. "X, nunc in museo Y" → findspot X, custody Y.
    find_part, custody = folded, None
    m_nunc = _NUNC.search(folded)
    if m_nunc:
        find_part = folded[: m_nunc.start()]
        custody = text[m_nunc.start() :].strip(" ,;.")
    olim = _OLIM.search(find_part)
    if olim:
        former = find_part[olim.end() :]
        find_part = find_part[: olim.start()]
        # "olim Clusii in museo Casuccini": the string names only keepers,
        # not a findspot. A later keeper counts as the current location only
        # where the string says the object is still there ("tum in museo
        # publico Panormitano, ubi … adhuc (1886)"); otherwise none is claimed.
        if custody is None and not find_part.strip(" ,;.(") and _CUSTODY.search(former):
            return FindspotClass(
                "current_location", None, None, _still_kept(text, former, olim.end()), "rule"
            )
    find_part = find_part.strip(" ,;.(")

    custody_only = False
    m_cust = _CUSTODY.search(find_part)
    if m_cust:
        before = find_part[: m_cust.start()].strip(" ,;.(")
        if custody is None:
            custody = text[m_cust.start() :].strip(" ,;.") if before else text.strip(" ,;.")
        if not before:
            custody_only = True
            find_part = ""
        else:
            # "Clusii in museo publico" names the town of the collection, not
            # the findspot. Treat it as custody only unless the phrase also
            # says the object was found there ("in agro", "repert", "effoss").
            if not re.search(r"repert|effoss|invent|rinvenut|trovat|in agro|agro", before):
                custody_only = True
                if m_nunc is None:
                    custody = text.strip(" ,;.")
                find_part = ""
            else:
                find_part = before
    lost = bool(custody and _LOST.search(_fold(custody)))
    if lost:
        # "nunc latet", "nunc videtur perisse", "nunc ubi sit, non comperi":
        # the source says the object is lost, which is no current location.
        custody = None
    if custody:
        custody = _custody_clause(custody)

    if _MUSEUM_CITY.match(folded):
        return FindspotClass("current_location", None, None, text.strip(" ,;."), "rule")
    place = _first_place(find_part) if find_part else None
    alias_note = ""
    if place is None and find_part:
        for rx, key, note in _TERRITORY_ALIASES:
            if rx.search(find_part):
                place, alias_note = key, note
                break
    if place is None:
        if custody_only or custody:
            return FindspotClass("current_location", None, None, custody, "rule")
        if _DESCRIPTION.search(folded):
            return FindspotClass("description", None, None, None, "rule")
        if lost:
            # Only keepers and "nunc ubi sit, non comperi": a custody note.
            return FindspotClass("current_location", None, None, None, "rule")
        return FindspotClass("unknown", None, None, None, "rule")

    kind = kinds.get(place, "city")
    if kind == "region":
        precision = "region"
    elif (
        alias_note
        or _TERRITORY.search(find_part)
        or place == "volsinii_veteres"
        and "orvieto" not in find_part
    ):
        precision = "territory"
    else:
        precision = kind if kind in PRECISIONS else "city"
    role = "findspot_and_current" if custody else "findspot"
    if place == "volsinii_veteres" and "orvieto" not in find_part and not alias_note:
        alias_note = (
            "'Volsinii' read as Etruscan Velzna (Orvieto) at territory precision; "
            "Roman Volsinii is Bolsena."
        )
    note = alias_note or (
        "Unknown findspot within the region." if _UNKNOWN.search(find_part) else ""
    )
    return FindspotClass(role, place, precision, custody, "rule", note)


# "latere" and "desideratur" also describe the object ("in latere sinistro",
# "operculum desideratur"), so they count only in the lost phrase itself.
# "ubi non inveni" and "ubi frustra quaesivi" are the editor reporting the
# object missing from that collection; a bare "non inveni" is not ("nisi
# Faesulis et Volaterris non inveni" is about a letter form).
_LOST = re.compile(
    r"\blatet\b|\bvidetur latere\b|\bperiit\b|\bperi?isse\b|\bubi sit\b|"
    r"\bnon comperi\b|\bnunc desideratur\b|\bdeperdit|\bextet ignoratur\b|"
    r"\bubi (?:\([^)]*\) )?non inveni|\bubi frustra quaesiv"
)
_TUM = re.compile(r"\btum\b")
_UBI_ADHUC = re.compile(r"\bubi\b.*\badhuc\b")


def _still_kept(text: str, former: str, offset: int) -> str | None:
    """The keeper an ``olim …`` string says still has the object, or None.

    ``former`` is the folded text after ``olim``, starting at ``offset`` in
    ``text``. Only ``… ubi … adhuc`` ("where it still is") names a present
    keeper: the clause after ``tum`` ("then"), else the last custody phrase
    before ``ubi``.
    """
    m_ubi = _UBI_ADHUC.search(former)
    if not m_ubi:
        return None
    m_tum = _TUM.search(former, 0, m_ubi.start())
    if m_tum:
        start = m_tum.start()
    else:
        phrases = list(_CUSTODY.finditer(former, 0, m_ubi.start()))
        if not phrases:
            return None
        start = phrases[-1].start()
    folded = _fold(text)
    # Offsets are into the folded text; they line up with ``text`` unless
    # folding changed its length (a ligature), in which case quote the fold.
    src = text if len(folded) == len(text) else folded
    return _custody_clause(src[offset + start :].strip(" ,;."))


def _custody_clause(text: str) -> str:
    """Keep only the clauses of a CIE note that say where the object is kept.

    CIE entries run object description, letter description and custody
    together with semicolons; only the custody clause belongs in
    ``current_location``.
    """
    clauses = [c.strip(" ,;.") for c in text.split(";")]
    keep = [c for c in clauses if _CUSTODY.search(_fold(c)) or _NUNC.search(_fold(c))]
    out = "; ".join(keep) if keep else text.strip(" ,;.")
    return _TRAILING_SIGLA.sub("", out).strip(" ,;.") or out


# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    key: str
    pleiades_id: str
    label_en: str
    label_it: str
    kind: str
    lat: float
    lon: float


def load_places(path: str | Path) -> dict[str, Place]:
    with open(path, encoding="utf-8", newline="") as fh:
        return {
            r["key"]: Place(
                key=r["key"],
                pleiades_id=r["pleiades_id"],
                label_en=r["label_en"],
                label_it=r["label_it"],
                kind=r["kind"],
                lat=float(r["lat"]),
                lon=float(r["lon"]),
            )
            for r in csv.DictReader(fh)
        }


GAZETTEER_FIELDS = (
    "findspot",
    "count",
    "role",
    "place_key",
    "precision",
    "current_location",
    "basis",
    "note",
)


def load_gazetteer(path: str | Path) -> dict[str, FindspotClass]:
    """Load ``reference/findspot_gazetteer.csv`` keyed by the exact string."""
    out: dict[str, FindspotClass] = {}
    p = Path(path)
    if not p.exists():
        return out
    with open(p, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["findspot"]] = FindspotClass(
                role=r["role"],
                place_key=r["place_key"] or None,
                precision=r["precision"] or None,
                current_location=r["current_location"] or None,
                basis=r["basis"] or "rule",
                note=r.get("note") or "",
            )
    return out


@dataclass(frozen=True)
class EtRegion:
    code: str
    label: str
    place_key: str | None
    precision: str | None
    note: str


def load_et_regions(path: str | Path) -> dict[str, EtRegion]:
    with open(path, encoding="utf-8", newline="") as fh:
        return {
            r["code"]: EtRegion(
                code=r["code"],
                label=r["label"],
                place_key=r["place_key"] or None,
                precision=r["precision"] or None,
                note=r.get("note") or "",
            )
            for r in csv.DictReader(fh)
        }
