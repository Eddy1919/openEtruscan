import sqlite3

conn_et = sqlite3.connect("data/cie/cie_etruscan.db")
conn_lat = sqlite3.connect("data/cie/cie_latin.db")
cur_et = conn_et.cursor()
cur_lat = conn_lat.cursor()

# Famous Etruscan u-stems with genitive -s ending that got caught in the crossfire
safe_words = ['velus', 'venelus', 'pumpus', 'fusumus', 'secus', 'cecus', 'cicus', 'farus', 'haltus', 'chius', 'plaus', 'krutpuus', 'anxvilus', 'seius']

cur_lat.execute("SELECT rowid, * FROM cie_review WHERE language_hint='likely_latin_morphology'")
rows = cur_lat.fetchall()

to_rescue = []
to_delete_rowids = []

for row in rows:
    text = str(row[2]).lower()
    
    # If the text has hardcore Latin markers like 'natus', 'f.', 'vixit', keep it in Latin.
    if any(x in text for x in ['natus', 'nata', '. f', '* f', 'vixit', 'annos', 'mens', 'filius']):
        continue
        
    # If the text ONLY has our safe Etruscan genitives, let's rescue it.
    if any(w in text for w in safe_words):
        to_rescue.append(row[1:]) # Skip rowid
        to_delete_rowids.append(row[0])

print(f"Rescuing {len(to_rescue)} authentic Etruscan genitives...")

if to_rescue:
    # Update back to candidate
    updated = [tuple([list(r)[0], list(r)[1], list(r)[2], list(r)[3], list(r)[4], list(r)[5], list(r)[6], "etruscan_candidate"]) for r in to_rescue]
    cur_et.executemany("INSERT INTO cie_review VALUES (?, ?, ?, ?, ?, ?, ?, ?)", updated)
    conn_et.commit()
    
    cur_lat.execute(f"DELETE FROM cie_review WHERE rowid IN ({','.join('?'*len(to_delete_rowids))})", to_delete_rowids)
    conn_lat.commit()

conn_et.close()
conn_lat.close()
