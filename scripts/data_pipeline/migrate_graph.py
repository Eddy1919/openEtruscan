#!/usr/bin/env python3
"""
Migrate Prosopographical Graph to PostgreSQL.

Parses the OpenEtruscan corpus to build the FamilyGraph, then flattens and 
inserts nodes (entities, clans) and edges (relationships) into PostgreSQL.
"""

import os
import sys
from pathlib import Path

# Ensure src is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openetruscan.corpus import Corpus
from openetruscan.prosopography import FamilyGraph

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL must be set")
        sys.exit(1)

    print("Loading Corpus...")
    corpus = Corpus.load()

    print("Building FamilyGraph from Corpus...")
    graph = FamilyGraph.from_corpus(corpus)

    import psycopg2
    conn = psycopg2.connect(db_url)
    
    with conn.cursor() as cur:
        # Populate Clans
        print(f"Migrating {len(graph.clans())} clans...")
        for clan in graph.clans():
            cur.execute("""
                INSERT INTO clans (id, name) 
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING;
            """, (clan.name, clan.name))
        
        # Populate Persons as Entities
        persons = graph.persons()
        print(f"Migrating {len(persons)} persons...")
        for p in persons:
            inscription_id = p.inscription_ids[0] if p.inscription_ids else None
            cur.execute("""
                INSERT INTO entities (id, name, inscription_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING;
            """, (p.id, p.name_formula.canonical, inscription_id))
            
            # Map BELONGS_TO relationship (Clan)
            if p.gentilicium:
                cur.execute("""
                    INSERT INTO relationships (person_id, clan_id, relationship_type)
                    VALUES (%s, %s, %s);
                """, (p.id, p.gentilicium, "BELONGS_TO"))
                
            # Parse Filiations (Patronymic / Metronymic) and create virtual parent nodes
            for comp in p.name_formula.components:
                if comp.type == "patronymic":
                    father_id = f"father_{p.id}_{comp.base_form}"
                    father_name = f"{comp.base_form} {p.gentilicium}" if p.gentilicium else comp.base_form
                    
                    cur.execute("""
                        INSERT INTO entities (id, name, inscription_id, notes)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """, (father_id, father_name, inscription_id, "Reconstructed_Patronymic"))
                    
                    if p.gentilicium:
                        cur.execute("""
                            INSERT INTO relationships (person_id, clan_id, relationship_type)
                            VALUES (%s, %s, %s);
                        """, (father_id, p.gentilicium, "BELONGS_TO"))
                        
                    cur.execute("""
                        INSERT INTO relationships (person_id, related_person_id, relationship_type)
                        VALUES (%s, %s, %s);
                    """, (p.id, father_id, "CHILD_OF"))
                    
                elif comp.type == "metronymic":
                    mother_id = f"mother_{p.id}_{comp.base_form}"
                    cur.execute("""
                        INSERT INTO entities (id, name, inscription_id, notes)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """, (mother_id, comp.base_form, inscription_id, "Reconstructed_Metronymic"))
                    
                    cur.execute("""
                        INSERT INTO relationships (person_id, related_person_id, relationship_type)
                        VALUES (%s, %s, %s);
                    """, (p.id, mother_id, "CHILD_OF"))
        
    conn.commit()
    conn.close()
    print("Graph Migration Complete!")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    main()
