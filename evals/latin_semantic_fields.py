"""Latin reference vocabularies grouped by semantic field.

Used to compute ``precision_at_k_semantic_field`` — a softer metric than
strict-lexical precision. The strict version asks "is the EXACT Latin
equivalent in top-k?". The semantic-field version asks "is *any* Latin
word in the same semantic field as the expected target in top-k?".

For ``papa→avus`` (grandfather), strict-lexical fails because the system
returns ``[papa, daddy, pater]`` — none equal ``avus``. But ``pater`` IS
a kinship term. Semantic-field gives partial credit for "the encoder
correctly identified the semantic neighbourhood, even if it picked the
wrong specific lemma".

This metric is appropriate for the use cases the system can actually
support (semantic-field exploration, hypothesis generation), as opposed
to the strict-lexical metric which measures something the system was
never going to do well at without parallel-data supervision.

Vocabulary sources:
  * Each entry's expected Latin lemma from rosetta_eval_pairs (the
    minimum members of each field).
  * Standard Latin synonyms / morphologically-related forms (e.g.
    filius/filia/filiola/filiolus all kinship; iuppiter/iouis/iouem
    all the same theonym in different cases).

Kept conservative: only words an undergrad classics student would
unambiguously place in the field. We are NOT trying to be exhaustive —
we are trying to give partial credit when the encoder gets the field
right.
"""

from __future__ import annotations

# All forms are lowercase, NFC-normalised — same as how the embedder
# stores them in language_word_embeddings.
LATIN_SEMANTIC_FIELDS: dict[str, set[str]] = {
    "kinship": {
        # parents / grandparents
        "pater", "patris", "patrem", "patre",
        "mater", "matris", "matrem", "matre",
        "avus", "auus", "aui", "auia", "avia",
        # children
        "filius", "filii", "filium", "filio", "filia", "filiae",
        "filiola", "filiolus", "natus", "nata", "puer", "puella",
        # siblings
        "frater", "fratris", "fratrem", "fratres", "soror", "sororis",
        # marriage
        "uxor", "uxoris", "uxorem", "coniunx", "coniugis",
        "maritus", "marita", "sponsus", "sponsa",
        # extended
        "nepos", "nepotis", "nepotes", "neptis",
        "familia", "familiae", "gens", "gentis", "domus", "stirps",
    },
    "civic": {
        # magistracies
        "praetor", "praetoris", "consul", "consulis",
        "dictator", "censor", "tribunus", "magister", "magistratus",
        "aedilis", "quaestor",
        # state / community
        "ciuitas", "civitas", "ciuitatis", "civitatis",
        "respublica", "populus", "populi", "imperium", "imperii",
        "fines", "finis", "finibus", "limes", "regio",
        "urbs", "urbis", "oppidum", "uicus", "vicus",
        # ethnonyms
        "etruscus", "etrusca", "etrusci", "tuscus", "tusci", "tusca",
        # religious-civic role
        "sacerdos", "sacerdotis", "haruspex", "augur", "pontifex",
    },
    "religious": {
        # gods / divinity
        "deus", "dei", "deum", "deo", "diuus", "divus", "numen", "numinis",
        # tomb / burial
        "sepulcrum", "sepulcri", "tumulus", "tumuli", "monumentum",
        "monumenti", "bustum", "rogus",
        # sacred / offering
        "sacer", "sacra", "sacrum", "sacri", "sacrae",
        "fanum", "fani", "templum", "templi", "ara", "arae",
        "uotum", "votum", "uoti", "voti",
        "oblatio", "donum", "dona", "munus", "muneris",
        # ritual specialists (some overlap with civic)
        "sacerdos", "sacerdotis", "flamen", "uirgo", "virgo",
    },
    "time": {
        "annus", "anni", "annum", "anno", "annorum", "annis",
        "mensis", "mense", "menses", "mensium",
        "dies", "diei", "die", "tempus", "temporis",
        "sol", "solis", "luna", "lunae",
        "uesper", "vesper", "aurora",
        "aetas", "aeui", "aevi",
    },
    "numeral": {
        "unus", "una", "unum",
        "duo", "duae", "duorum", "duobus",
        "tres", "tria", "trium", "tribus",
        "quattuor", "quatuor",
        "quinque", "sex", "septem", "octo", "nouem", "novem", "decem",
        "primus", "prima", "primum",
        "secundus", "tertius", "quartus", "quintus",
        "centum", "mille",
    },
    "verb": {
        # giving / dedicating
        "do", "dare", "dedi", "dedit", "dederunt", "datum",
        "dono", "donare", "donaui", "donavi", "donatum",
        "dedico", "dedicare", "dedicaui", "dedicavi", "dedicauit", "dedicavit",
        # making / building
        "facio", "facere", "feci", "fecit", "fecerunt", "factum",
        "construo", "construere", "constructum",
        # being / living / dying
        "sum", "esse", "est", "sunt", "fuit", "erat",
        "uiuo", "vivo", "uiuere", "vivere", "uixit", "vixit",
        "morior", "mori", "mortuus", "mortua", "obiit", "decessit",
        "obeo", "obire", "obit",
        # writing / inscribing
        "scribo", "scribere", "scripsit", "scriptum",
        "scriptura", "scriptor", "litera", "littera",
        "inscribo", "inscribere", "inscriptum",
    },
    "theonym": {
        # major Olympians as adopted by Romans
        "iuppiter", "iouis", "ioui", "iouem", "ioue",
        "iuno", "iunonis", "iunoni", "iunonem",
        "minerua", "minerva", "mineruae", "minervae",
        "venus", "veneris", "ueneris", "veneri",
        "mercurius", "mercurii", "mercurio",
        "neptunus", "neptuni",
        "apollo", "apollinis", "diana", "dianae",
        "mars", "martis", "vulcanus", "uulcanus",
        "ceres", "cereris", "vesta", "uesta",
        "bacchus", "bacchi", "liber", "liberi",
        "hercules", "herculis", "herculi", "herculem",
        "saturnus", "saturni",
        # Underworld
        "dis", "ditis", "pluto", "plutonis",
        "proserpina", "proserpinae",
    },
    "onomastic": {
        # Roman praenomina commonly attested in Etruscan-Latin equation
        "aulus", "auli", "lars", "lartis",
        "uelius", "velius", "uelii", "velii",
        "marcus", "marci", "marco",
        "lucius", "lucii", "lucio",
        "gaius", "caius", "gaii",
        "publius", "publii", "tiberius", "tiberii",
        "sextus", "sexti", "spurius",
        "tarquinius", "tarquinii",
    },
}


def get_field_vocabulary(category: str) -> set[str]:
    """Return the Latin vocabulary set for a given Etruscan eval category.
    Empty set for unknown categories."""
    return LATIN_SEMANTIC_FIELDS.get(category, set())


def field_member_count(category: str, candidates: list[str]) -> int:
    """How many of ``candidates`` are members of the field for ``category``."""
    vocab = get_field_vocabulary(category)
    if not vocab:
        return 0
    return sum(1 for c in candidates if c.lower() in vocab)
