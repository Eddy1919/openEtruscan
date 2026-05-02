"""Regression snapshot testing for classifier."""

from openetruscan.ml.classifier import InscriptionClassifier

# Held-out set of inputs mapped to their expected classification labels.
# If these start failing, it indicates a regression in classification accuracy.
SNAPSHOT_SET = {
    "suθi larθal lecnes": "funerary",
    "turce alpan fleres": "votive",
    "tular rasna spura": "boundary",
    "mi mulu larisce": "ownership",
    "flerχva neθunsl": "votive",
    "suθi larthi": "funerary",
    "spura tular": "boundary",
}

def test_classifier_snapshot():
    """Ensure classification results do not regress on a held-out snapshot set."""
    clf = InscriptionClassifier()
    for text, expected_label in SNAPSHOT_SET.items():
        result = clf.predict(text)
        assert result.label == expected_label, f"Regression on '{text}': expected {expected_label}, got {result.label}"
