"""
Embedding-based MLP Classifier using Gemini vectors.

Trains an sklearn MLP using pre-computed `emb_combined` pgvector embeddings
from the PostGIS database. Drastically faster and more semantically aware
than the legacy CharCNN.

Usage:
    from openetruscan.ml.embedding_classifier import EmbeddingMLPClassifier
    clf = EmbeddingMLPClassifier()
    clf.train_from_db(os.environ["DATABASE_URL"])
"""

import time
from typing import Any

from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import numpy as np
import psycopg2


class EmbeddingMLPClassifier:
    """Predict inscription classification using Gemini vector embeddings."""

    def __init__(self, hidden_layer_sizes: tuple = (128, 64), random_state: int = 42) -> None:
        self.hidden_layer_sizes = hidden_layer_sizes
        self.random_state = random_state
        self.model = MLPClassifier(
            hidden_layer_sizes=self.hidden_layer_sizes,
            activation="relu",
            solver="adam",
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.1,
            random_state=self.random_state,
        )
        self.label_encoder = LabelEncoder()
        self._trained = False

    def train_from_db(
        self, db_url: str, val_split: float = 0.2, verbose: bool = True
    ) -> dict[str, Any]:
        """Fetch vectorized data and train the MLP."""
        conn = psycopg2.connect(db_url)

        # We only want verified labels, not 'unknown'
        sql = """
            SELECT canonical, classification, emb_combined 
            FROM inscriptions 
            WHERE emb_combined IS NOT NULL 
              AND canonical != ''
        """

        start_time = time.time()

        vectors = []
        labels = []

        from openetruscan.ml.neural import _weak_label, normalize

        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                canonical = row[0]
                lbl = row[1]

                # Weak labeling if unknown
                if not lbl or lbl == "unknown":
                    result = normalize(canonical, language="etruscan")
                    lbl = _weak_label(result.canonical, result.tokens)
                    if not lbl or lbl == "unknown":
                        continue

                vec_str = row[2]
                if isinstance(vec_str, str):
                    vec = [float(v) for v in vec_str.strip("[]").split(",")]
                else:
                    vec = vec_str  # If the DB adapter auto-converts to list
                vectors.append(vec)
                labels.append(row[1])

        conn.close()

        if len(vectors) < 20:
            raise ValueError(
                f"Only {len(vectors)} labeled embedded samples found. Need at least 20."
            )

        X = np.array(vectors)
        y = self.label_encoder.fit_transform(labels)

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=val_split, stratify=y, random_state=self.random_state
        )

        if verbose:
            print(f"  Training vectors: {len(X_train)}")
            print(f"  Validation vectors: {len(X_val)}")

        self.model.fit(X_train, y_train)

        # Evaluate
        val_preds = self.model.predict(X_val)
        val_f1 = f1_score(y_val, val_preds, average="macro", zero_division=0)

        classification_report(
            y_val,
            val_preds,
            target_names=self.label_encoder.classes_,
            output_dict=True,
            zero_division=0,
        )

        self._trained = True

        metrics = {
            "arch": "mlp_embeddings",
            "train_time_s": round(time.time() - start_time, 2),
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "val_f1_macro": round(val_f1, 4),
            "classes": self.label_encoder.classes_.tolist(),
        }

        if verbose:
            print(f"  ✅ Embedding MLP trained in {metrics['train_time_s']}s")
            print(f"     Best val F1 (macro): {val_f1:.4f}")

        return metrics

    def predict(self, embedding: list[float]) -> dict[str, Any]:
        """Predict the classification based on an input vector."""
        if not self._trained:
            raise RuntimeError("Model must be trained before predicting.")

        X = np.array([embedding])
        probs = self.model.predict_proba(X)[0]

        probabilities = {
            str(cls): round(float(p), 4)
            for cls, p in zip(self.label_encoder.classes_, probs, strict=False)
        }
        best_label = max(probabilities, key=probabilities.get)

        return {
            "label": best_label,
            "method": "neural_mlp_embeddings",
            "probabilities": probabilities,
        }
