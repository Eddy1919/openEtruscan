import sqlite3
import re
import json

def get_geom_str(lon, lat):
    if lon is not None and lat is not None:
        return f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"
    return "NULL"

def escape_sql(s):
    if s is None:
        return "NULL"
    if isinstance(s, (int, float)):
        return str(s)
    if isinstance(s, bool):
        return "true" if s else "false"
    # replace single quotes with two single quotes
    safe = str(s).replace("'", "''")
    return f"'{safe}'"

def export_sql():
    conn = sqlite3.connect('data/cie/databases/cie_etruscan.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM cie_review")
    rows = cur.fetchall()
    
    # Get column names
    col_names = [description[0] for description in cur.description]
    
    with open('data/cie/working/pg_ingest.sql', 'w', encoding='utf-8') as f:
        f.write("BEGIN;\n")
        f.write("SET statement_timeout = 50000;\n")
        count = 0
        for row in rows:
            rd = dict(zip(col_names, row))
            id_val = f"CIE {rd['cie_id']}" if 'CIE' not in rd['cie_id'] else rd['cie_id']
            
            canonical = rd.get('canonical') or ''
            phonetic = rd.get('phonetic') or ''
            old_italic = rd.get('old_italic') or ''
            raw_text = rd.get('transliterated') or ''
            findspot = rd.get('findspot_modern') or rd.get('latin_findspot') or ''
            lat = rd.get('findspot_lat')
            lon = rd.get('findspot_lon')
            unc_m = rd.get('uncertainty_m')
            
            # Map provenance flags
            flags = []
            if rd.get('language_hint'): flags.append(rd['language_hint'])
            prov_status = 'verified'
            
            geom = get_geom_str(lon, lat)
            
            source_code = rd.get('source_code', 'CIE')
            source_detail = rd.get('pdf_source') or rd.get('source_detail', '')
            original_script = rd.get('original_script_entry') or rd.get('original_script', '')
            notes = rd.get('latin_commentary', '')
            bibliography = rd.get('bibliography', '')
            
            f.write(f"""
INSERT INTO inscriptions (
    id, canonical, phonetic, old_italic, raw_text, findspot, findspot_lat, findspot_lon, findspot_uncertainty_m,
    notes, bibliography, language, classification, script_system, completeness, provenance_status, provenance_flags, 
    geom, source_code, source_detail, original_script_entry
) VALUES (
    {escape_sql(id_val)},
    {escape_sql(canonical)},
    {escape_sql(phonetic)},
    {escape_sql(old_italic)},
    {escape_sql(raw_text)},
    {escape_sql(findspot)},
    {escape_sql(lat)},
    {escape_sql(lon)},
    {escape_sql(unc_m)},
    {escape_sql(notes)},
    {escape_sql(bibliography)},
    'etruscan',
    'unknown',
    'old_italic',
    'complete',
    {escape_sql(prov_status)},
    {escape_sql(",".join(flags))},
    {geom},
    {escape_sql(source_code)},
    {escape_sql(source_detail)},
    {escape_sql(original_script)}
) ON CONFLICT (id) DO NOTHING;
""")
            count += 1
            
        f.write("COMMIT;\n")
    print(f"Exported {count} records to data/cie/working/pg_ingest.sql")

if __name__ == "__main__":
    export_sql()
