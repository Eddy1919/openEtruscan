"""
Inscription classifier — ML-powered text classification for epigraphic corpora.

Two modes:
  1. **ML mode**: Multinomial Naive Bayes + TF-IDF trained on labeled inscriptions.
  2. **Keyword fallback**: Enhanced vocabulary scoring when < 500 labeled samples.

Usage:
    from openetruscan.classifier import InscriptionClassifier

    clf = InscriptionClassifier()
    result = clf.predict("suθi larθal lecnes")
    print(result.label, result.probabilities)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openetruscan.normalizer import normalize

# ---------------------------------------------------------------------------
# Keyword vocabulary (expanded scholarly patterns per class)
# ---------------------------------------------------------------------------

_KEYWORD_VOCAB: dict[str, list[str]] = {
    "funerary": [
        # --- Tomb / burial markers ---
        "suθi",  # tomb/burial
        "suθina",  # funerary offering
        "suθiθ",  # of the tomb (genitive)
        "σuθi",  # variant spelling of suθi
        "σuθiθ",  # variant genitive
        # --- Death and life formulae ---
        "lupu",  # died
        "lupuce",  # died (perfective)
        "svalce",  # lived (age formula)
        "svalθas",  # lived (variant)
        "avils",  # years (age formula)
        "avil",  # year
        "murce",  # was (in death/life formulae)
        # --- Kinship (typical on sarcophagi/urns) ---
        "clan",  # son
        "sec",  # daughter
        "puia",  # wife
        "ati",  # mother
        "latn",  # family/gens
        "lautni",  # family member/freedman
        "nefts",  # grandson/nephew
        "papacs",  # grandfather
        "clenaraśi",  # of the sons
        # --- Funerary structures/contexts ---
        "ceχa",  # grave/pit
        "nacna",  # related to death
        "θapna",  # cup/offering vessel (funerary)
        "hinthial",  # shade/ghost/soul
        "tamera",  # funerary chamber
        "σuθic",  # of the tomb
        "zivas",  # the living / lived
        "ceriχunce",  # built/made (for the tomb)
        "lavtni",  # family (on sarcophagi)
        "huσur",  # youth (age marker)
    ],
    "votive": [
        # --- Dedication verbs ---
        "turce",  # gave/dedicated
        "mulvanice",  # offered (as a gift)
        "muluvanice",  # offered (variant)
        "mulu",  # dedicated/offered
        # --- Gift/offering terms ---
        "alpan",  # gift/offering
        "fleres",  # statue/image (votive)
        "flerχva",  # votive offering/ritual
        "cver",  # gift/offering
        # --- Divine epithets ---
        "mlaχ",  # good/beautiful (votive)
        "aisera",  # divine/of the gods
        "ais",  # god
        "eiser",  # divine (adj./deity)
        "aisna",  # divine
        # --- Sanctuary terms ---
        "tuθina",  # sanctuary/temple
        "tmia",  # temple
    ],
    "boundary": [
        # --- Boundary terminology ---
        "tular",  # boundary/boundary stone
        "tularias",  # of the boundary
        # --- Civic/territorial ---
        "rasna",  # Etruscan (self-designation)
        "raśnas",  # of the Etruscans (genitive)
        "raśneś",  # of the Etruscan (adj.)
        "spura",  # city/civic
        "spural",  # of the city
        "spurana",  # civic (adj.)
        "meθlum",  # district/territory
        "meθlumθ",  # of the district
        "methlumθ",  # variant
        # --- Land terms ---
        "vaχr",  # land/estate
    ],
    "ownership": [
        # --- Ownership formulae ---
        "mi",  # I (am) — ownership formula
        "mini",  # me / mine
        "minipi",  # possessive marker
        "zinace",  # made (I made = craftsman mark)
        "zinaku",  # maker (variant)
        "ziχuχe",  # wrote/engraved
        # --- Vessel/object markers ---
        "eca",  # this (demonstrative, on objects)
        "mine",  # gift/possession
        "apirθe",  # related to objects
    ],
    "legal": [
        # --- Magistrate titles ---
        "zilχ",  # magistrate/praetor
        "zilχnu",  # magistrate (variant)
        "zilc",  # magistrate (variant)
        "zilaθ",  # magistrate/praetor
        "zilaχnθas",  # magistrate office
        "zilacal",  # of the magistrate
        "zilci",  # magistracy
        "eprθnev",  # title/office
        "purθ",  # office/magistracy
        "marunuχ",  # magistrate title
        "lucair",  # to rule/govern
        "cepen",  # title (priestly/official)
        "tenu",  # to hold/administer
        "camθi",  # title/honor
        # --- Legal actions ---
        "amce",  # was/held (office)
        "eslz",  # honoring (office)
        "parχis",  # holding office
        # --- Administrative terms ---
        "tenθas",  # of the office
        "naper",  # measure/norm
        "spureśtreści",  # civic office (Liber Linteus)
    ],
    "commercial": [
        # --- Numerals (weights/measures) ---
        "zal",  # two
        "ci",  # three
        "θu",  # one
        "maχ",  # five
        "huθ",  # four/six
        "semφ",  # seven
        "cezp",  # eight
        "nurφ",  # nine
        "śar",  # ten
        # --- Trade goods/vessels ---
        "pruχ",  # pitcher
        "aska",  # leather bag/flask
        "culiχna",  # vessel/cup (kylix)
        "θafna",  # bowl/vessel
        "qutum",  # vessel (pitcher)
        "presnts",  # something weighed
    ],
    "dedicatory": [
        # --- Deity names (major Etruscan pantheon) ---
        "tinia",  # Jupiter/Tinia
        "tinśi",  # of Tinia (genitive)
        "uni",  # Juno/Uni
        "unial",  # of Uni
        "menerva",  # Minerva
        "menrvas",  # of Minerva (gen.)
        "θesan",  # dawn goddess Thesan
        "θeśan",  # variant spelling
        "turan",  # Venus/Turan
        "fuflunś",  # Fufluns/Dionysus
        "hercle",  # Hercules
        "selva",  # Silvanus
        "caθa",  # sun deity
        "leθn",  # deity of death
        "vetsl",  # deity
        "śuri",  # Suri (underworld deity)
        "śuris",  # of Suri (gen.)
        "saucne",  # deity/ritual term
        "aritimi",  # Artemis
        "aplu",  # Apollo
        "sethlans",  # Sethlans/Hephaestus
        "turms",  # Hermes/Turms
        # --- Temple dedication terms ---
        "heramaśva",  # for the temple/sacred context
        "θemiasa",  # sacred area
        "śacni",  # sacred/sanctuary
        "śacnicla",  # sacred rite
    ],
}


# Minimum labeled samples before switching from keyword to ML
_ML_THRESHOLD = 500


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    """Result of inscription classification."""

    label: str
    probabilities: dict[str, float] = field(default_factory=dict)
    method: str = "keyword_fallback"  # "ml" or "keyword_fallback"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "method": self.method,
        }


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class InscriptionClassifier:
    """
    Text classifier for Etruscan inscriptions.

    Uses scikit-learn Naive Bayes when sufficient labeled data exists,
    otherwise falls back to enhanced keyword scoring.
    """

    def __init__(self) -> None:
        self._vectorizer = None
        self._model = None
        self._classes: list[str] = []
        self._trained = False

    def train(self, texts: list[str], labels: list[str]) -> None:
        """
        Train the ML classifier on labeled inscription texts.

        Args:
            texts: Canonical inscription texts.
            labels: Classification labels (funerary, votive, etc.).
        """
        if len(texts) < _ML_THRESHOLD:
            return  # Stay in keyword fallback mode

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.naive_bayes import MultinomialNB
        except ImportError as exc:
            raise ImportError(
                "ML classification requires scikit-learn. "
                "Install with: pip install openetruscan[stats]"
            ) from exc

        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=3000,
            min_df=2,
        )
        x_train = self._vectorizer.fit_transform(texts)

        self._model = MultinomialNB(alpha=0.1)
        self._model.fit(x_train, labels)
        self._classes = list(self._model.classes_)
        self._trained = True

    def predict(
        self,
        text: str,
        language: str = "etruscan",
    ) -> ClassificationResult:
        """
        Classify an inscription text.

        Uses ML if trained, otherwise keyword fallback.
        """
        result = normalize(text, language=language)
        canonical = result.canonical
        tokens = result.tokens

        if self._trained and self._model is not None and self._vectorizer is not None:
            return self._predict_ml(canonical)
        return self._predict_keywords(canonical, tokens)

    def _predict_ml(self, canonical: str) -> ClassificationResult:
        """Classify using the trained ML model."""
        x_vec = self._vectorizer.transform([canonical])
        proba = self._model.predict_proba(x_vec)[0]
        probabilities = dict(zip(self._classes, proba, strict=True))

        label = max(probabilities, key=probabilities.get)  # type: ignore[arg-type]
        return ClassificationResult(
            label=label,
            probabilities=probabilities,
            method="ml",
        )

    def _predict_keywords(
        self,
        canonical: str,
        tokens: list[str],
    ) -> ClassificationResult:
        """Classify using enhanced keyword vocabulary scoring."""
        scores: dict[str, float] = {}

        for category, keywords in _KEYWORD_VOCAB.items():
            score = 0.0
            for keyword in keywords:
                # Check token-level match
                if keyword in tokens:
                    score += 1.0
                # Check substring match (for compound forms)
                elif keyword in canonical:
                    score += 0.5
            # Normalise by vocabulary size to avoid bias toward larger lists
            scores[category] = score / len(keywords) if keywords else 0.0

        if not scores or max(scores.values()) == 0.0:
            return ClassificationResult(
                label="unknown",
                probabilities=scores,
                method="keyword_fallback",
            )

        # Softmax-like normalisation for probability-like output
        total = sum(scores.values())
        probabilities = {k: v / total for k, v in scores.items()} if total > 0 else scores

        label = max(scores, key=scores.get)  # type: ignore[arg-type]
        return ClassificationResult(
            label=label,
            probabilities=probabilities,
            method="keyword_fallback",
        )

    def save_model(self, path: str) -> None:
        """Save the trained model to disk."""
        if not self._trained:
            raise RuntimeError("No trained model to save. Call train() first.")
        try:
            import joblib
        except ImportError as exc:
            raise ImportError(
                "Saving models requires joblib. Install with: pip install openetruscan[stats]"
            ) from exc
        joblib.dump(
            {
                "vectorizer": self._vectorizer,
                "model": self._model,
                "classes": self._classes,
            },
            path,
        )

    def load_model(self, path: str) -> None:
        """Load a trained model from disk."""
        try:
            import joblib
        except ImportError as exc:
            raise ImportError(
                "Loading models requires joblib. Install with: pip install openetruscan[stats]"
            ) from exc
        data = joblib.load(path)
        self._vectorizer = data["vectorizer"]
        self._model = data["model"]
        self._classes = data["classes"]
        self._trained = True
