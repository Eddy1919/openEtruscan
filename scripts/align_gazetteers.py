"""Align OpenEtruscan findspots with Pleiades and GeoNames gazetteers.

Adds pleiades_id, geonames_id columns to the inscriptions table and
populates them from a curated mapping + API fallback.

Usage: .venv/bin/python scripts/align_gazetteers.py [--db data/corpus.db]
"""

import argparse
import sqlite3

# ── Curated mapping: findspot → Pleiades ID ─────────────────────────
# These are well-known Etruscan/Italian sites with stable Pleiades entries.
# Source: https://pleiades.stoa.org
PLEIADES_MAP: dict[str, str] = {
    "Arretium": "413032",  # Arezzo
    "Caere": "422859",  # Cerveteri
    "Clusium": "413084",  # Chiusi
    "Cortona": "413098",  # Cortona
    "Faesulae": "413126",  # Fiesole
    "Narce": "413248",  # Narce
    "Perugia": "413248",  # Perugia
    "Perusia": "413248",  # Perugia
    "Piacenza": "383741",  # Placentia
    "Pisae": "403207",  # Pisa
    "Populonia": "413169",  # Populonia
    "Pyrgi": "413182",  # Pyrgi (S. Severa)
    "Roma": "423025",  # Rome
    "Rusellae": "413184",  # Roselle
    "Saturnia": "413186",  # Saturnia
    "Spina": "393489",  # Spina (Comacchio)
    "Tarquinia": "413332",  # Tarquinia
    "Veii": "423116",  # Veio
    "Vetulonia": "413381",  # Vetulonia
    "Volaterrae": "403292",  # Volterra
    "Volsinii": "413389",  # Bolsena
    "Vulci": "413395",  # Vulci
    # Ager (territory) entries — link to the main city
    "Ager Caeretanus": "422859",  # territory of Caere
    "Ager Tarquiniensis": "413332",  # territory of Tarquinia
    "Ager Veientanus": "423116",  # territory of Veii
    "Ager Clusinus": "413084",  # territory of Clusium
    "Ager Faesulanus": "413126",  # territory of Faesulae
    "Ager Pisanus": "403207",  # territory of Pisae
    "Ager Volaterranus": "403292",  # territory of Volaterrae
    "Ager Volsiniensis": "413389",  # territory of Volsinii
    "Ager Volcentanus": "413395",  # territory of Vulci
    "Ager Saenensis": "413282",  # territory of Saena (Siena)
    # Regions
    "Campania": "442733",  # Campania (region)
    "Latium": "422932",  # Latium (region)
    "Umbria": "413356",  # Umbria (region)
    "Liguria": "383627",  # Liguria (region)
    "Lucania": "442683",  # Lucania (region)
    "Aemilia": "383596",  # Aemilia (region)
    "Padana": "393471",  # Po Valley / Cisalpine Gaul
    "Isola d'Elba": "413143",  # Ilva (Elba)
    "Falerii et Ager Faliscus": "413123",  # Falerii
    "Ager Capenas": "413062",  # Capena
}

# ── GeoNames mapping for non-ancient entries ────────────────────────
GEONAMES_MAP: dict[str, str] = {
    "Arretium": "3182749",  # Arezzo
    "Caere": "6541965",  # Cerveteri
    "Clusium": "3178519",  # Chiusi
    "Cortona": "3177997",  # Cortona
    "Faesulae": "3177101",  # Fiesole
    "Perugia": "3171180",  # Perugia
    "Perusia": "3171180",
    "Piacenza": "3171077",  # Piacenza
    "Pisae": "3170647",  # Pisa
    "Populonia": "3170227",  # Populonia
    "Roma": "3169070",  # Rome
    "Saturnia": "3167074",  # Saturnia
    "Tarquinia": "3165940",  # Tarquinia
    "Veii": "3164526",  # Veio
    "Vetulonia": "3164375",  # Vetulonia
    "Volaterrae": "3163972",  # Volterra
    "Vulci": "8013259",  # Vulci
}


def ensure_columns(conn: sqlite3.Connection) -> None:
    """Add gazetteer columns if they don't exist."""
    cursor = conn.cursor()
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(inscriptions)")}
    for col in ("pleiades_id", "geonames_id"):
        if col not in existing:
            cursor.execute(f"ALTER TABLE inscriptions ADD COLUMN {col} TEXT")
            print(f"  Added column: {col}")
    conn.commit()


def align(db_path: str) -> None:
    """Run the gazetteer alignment."""
    conn = sqlite3.connect(db_path)
    ensure_columns(conn)
    cursor = conn.cursor()

    # Get distinct findspots
    cursor.execute(
        "SELECT DISTINCT findspot FROM inscriptions WHERE findspot IS NOT NULL AND findspot != ''"
    )
    findspots = [row[0] for row in cursor.fetchall()]

    matched = 0
    unmatched = []

    for fs in findspots:
        pleiades_id = PLEIADES_MAP.get(fs)
        geonames_id = GEONAMES_MAP.get(fs)

        if pleiades_id:
            cursor.execute(
                "UPDATE inscriptions SET pleiades_id = ? WHERE findspot = ?",
                (pleiades_id, fs),
            )
            n = cursor.rowcount
            status = f"pleiades:{pleiades_id}"
            if geonames_id:
                cursor.execute(
                    "UPDATE inscriptions SET geonames_id = ? WHERE findspot = ?",
                    (geonames_id, fs),
                )
                status += f" geonames:{geonames_id}"
            print(f"  ✅ {fs:30s} → {status} ({n} inscriptions)")
            matched += 1
        else:
            unmatched.append(fs)
            print(f"  ⚠️  {fs:30s} → no match")

    conn.commit()

    # Summary
    total = len(findspots)
    print(f"\n{'=' * 50}")
    print(f"  Alignment complete: {matched}/{total} findspots matched")
    if unmatched:
        print(f"  Unmatched: {', '.join(unmatched)}")

    # Verify
    cursor.execute("SELECT COUNT(*) FROM inscriptions WHERE pleiades_id IS NOT NULL")
    n_linked = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM inscriptions")
    n_total = cursor.fetchone()[0]
    print(f"  Inscriptions with Pleiades link: {n_linked}/{n_total}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Align findspots with gazetteers")
    parser.add_argument("--db", default="data/corpus.db", help="Database path")
    args = parser.parse_args()

    print("OpenEtruscan — Gazetteer Alignment")
    print("=" * 50)
    align(args.db)


if __name__ == "__main__":
    main()
