import sqlite3

conn_et = sqlite3.connect("data/cie/cie_etruscan.db")
conn_lat = sqlite3.connect("data/cie/cie_latin.db")
cur_et = conn_et.cursor()
cur_lat = conn_lat.cursor()

safe_words = ['velus', 'venelus', 'pumpus', 'fusumus', 'secus', 'cecus', 'cicus', 'farus', 'haltus', 'chius', 'plaus', 'krutpuus', 'seius', 'anxvilus', 'uelus']

cur_lat.execute("SELECT rowid, * FROM cie_review WHERE language_hint='likely_latin_morphology'")
rows = cur_lat.fetchall()

to_rescue = []
to_delete_rowids = []

for row in rows:
    text = str(row[3]).lower()  # index 3 is transliterated in the returned tuple! Because schema is:
    # 0 rowid, 1 cie_id, 2 language_hint, 3 transliterated, 4 latin_findspot, 5 latin_commentary, 6 bibliography, 7 pdf_source, 8 original_script
    
    # Strictly latin markers
    if any(x in text for x in ['natus', 'nata', '. f', '* f', 'vixit']):
        continue
        
    if any(w in text for w in safe_words):
        to_rescue.append(row[1:])
        to_delete_rowids.append(row[0])

print(f"Rescuing {len(to_rescue)} authentic Etruscan genitives...")

if to_rescue:
    # Set language_hint back to candidate
    updated = []
    for r in to_rescue:
        r_list = list(r)
        r_list[1] = "etruscan_candidate"
        updated.append(tuple(r_list))
        
    cur_et.executemany("INSERT INTO cie_review VALUES (?, ?, ?, ?, ?, ?, ?, ?)", updated)
    conn_et.commit()
    
    cur_lat.execute(f"DELETE FROM cie_review WHERE rowid IN ({','.join('?'*len(to_delete_rowids))})", to_delete_rowids)
    conn_lat.commit()

conn_et.close()
conn_lat.close()
