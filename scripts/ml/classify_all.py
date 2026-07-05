"""Classify all unclassified inscriptions in the corpus using the trained CNN."""

import sqlite3

from openetruscan.neural import NeuralClassifier


def main():
    # Load model — arch is set via __init__, load() takes only path
    classifier = NeuralClassifier(arch="cnn")
    classifier.load("data/models")

    conn = sqlite3.connect("data/corpus.db")

    # Get all missing classifications
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, canonical FROM inscriptions"
        " WHERE classification IS NULL"
        " OR classification = ''"
        " OR classification = 'unknown'"
    )
    rows = cursor.fetchall()

    print(f"Assigning classifications to {len(rows)} inscriptions...")
    updates = []
    for id_val, text in rows:
        if not text or not text.strip():
            continue
        # predict() returns ClassificationResult — extract .label for SQLite
        result = classifier.predict(text)
        updates.append((result.label, id_val))

    print(f"Generated {len(updates)} predictions. Updating database.")
    cursor.executemany("UPDATE inscriptions SET classification = ? WHERE id = ?", updates)
    conn.commit()
    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
