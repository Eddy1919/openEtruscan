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
        "suθi",       # tomb/burial
        "svalce",     # lived (age formula)
        "lupuce",     # died
        "avils",      # years (age formula)
        "ceχa",       # grave/pit
        "zilc",       # magistrate (often on sarcophagi)
        "latn",       # family (family tomb marker)
        "θui",        # here
        "nacna",      # related to death
        "θapna",      # cup/offering vessel (funerary context)
    ],
    "votive": [
        "turce",      # gave/dedicated
        "mulvanice",  # offered (as a gift)
        "alpan",      # gift/offering
        "fleres",     # statue/image (votive statues)
        "mlaχ",       # good/beautiful (votive epithets)
        "aisera",     # divine/of the gods
    ],
    "boundary": [
        "tular",      # boundary (boundary stone)
        "rasna",      # Etruscan (ethnic self-designation)
        "spura",      # city (civic inscriptions)
        "meθlum",     # district/territory
    ],
    "ownership": [
        "mi",         # I (am) — ownership formula
        "mulu",       # dedicated/belonging to
        "minipi",     # possessive marker
    ],
    "legal": [
        "zilχ",       # magistrate/praetor
        "eprθnev",    # title/office
        "purθ",       # office/magistracy
        "marunuχ",    # magistrate title
        "lucair",     # to rule/govern
    ],
    "commercial": [
        "zal",        # two/number (weights, measures)
        "θu",         # one (counting)
        "pruχ",       # pitcher (trade goods)
        "aska",       # leather bag (trade)
    ],
    "dedicatory": [
        "turce",      # gave/dedicated (overlaps votive)
        "tinia",      # Jupiter/Tinia (deity)
        "uni",        # Juno/Uni (deity)
        "menerva",    # Minerva (deity)
        "θesan",      # dawn goddess
        "turan",      # Venus/Turan
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
            "probabilities": {
                k: round(v, 4) for k, v in self.probabilities.items()
            },
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
                "Saving models requires joblib. "
                "Install with: pip install openetruscan[stats]"
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
                "Loading models requires joblib. "
                "Install with: pip install openetruscan[stats]"
            ) from exc
        data = joblib.load(path)
        self._vectorizer = data["vectorizer"]
        self._model = data["model"]
        self._classes = data["classes"]
        self._trained = True
