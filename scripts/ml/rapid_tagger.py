"""Rapid-tagging script for manual inscription classification.

Fetches unclassified inscriptions and lets you classify them
with a single keystroke. Creates the gold-standard training set.

Usage: python scripts/rapid_tagger.py [--db data/corpus.db]
"""

import argparse
import sqlite3

CLASSES = {
    "1": "funerary",
    "2": "votive",
    "3": "legal",
    "4": "commercial",
    "5": "boundary",
    "6": "ownership",
    "7": "dedicatory",
    "s": "skip",
    "q": "quit",
}


def main():
    parser = argparse.ArgumentParser(description="Rapid inscription tagger")
    parser.add_argument("--db", default="data/corpus.db", help="Database path")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    # Fetch all unclassified texts
    cursor.execute(
        "SELECT id, canonical, findspot FROM inscriptions "
        "WHERE classification = 'unknown' OR classification IS NULL "
        "ORDER BY id"
    )
    rows = cursor.fetchall()

    total = len(rows)
    labeled = 0
    print(f"Found {total} unclassified inscriptions.\n")

    for i, (id_val, text, findspot) in enumerate(rows, 1):
        if not text or not text.strip():
            continue

        print("-" * 50)
        print(f"[{i}/{total}]  ID: {id_val}")
        print(f"  TEXT:     {text}")
        if findspot:
            print(f"  FINDSPOT: {findspot}")
        print()

        for key, val in CLASSES.items():
            print(f"  [{key}] {val}")

        choice = input("\nSelect class: ").strip().lower()

        if choice == "q":
            break
        if choice == "s":
            continue

        label = CLASSES.get(choice)
        if label and label not in ("skip", "quit"):
            cursor.execute(
                "UPDATE inscriptions SET classification = ? WHERE id = ?",
                (label, id_val),
            )
            conn.commit()
            labeled += 1
            print(f"  ✅ Saved as: {label}\n")
        else:
            print("  ⏭️  Invalid choice, skipping.\n")

    conn.close()
    print(f"\nTagging session ended. Labeled {labeled} inscriptions.")


if __name__ == "__main__":
    main()
