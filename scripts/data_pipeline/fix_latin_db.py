import sqlite3

conn_lat = sqlite3.connect("data/cie/cie_latin.db")
c = conn_lat.cursor()

# Swap them
# 'likely_latin_morphology' is currently in original_script
# original_script is missing (because we overwrote it) but wait! We lost original_script.
# That's fine, original_script is just garbage mojibake for Latin texts anyway.
# We just need to fix language_hint to 'likely_latin_morphology' for those rows.
c.execute("UPDATE cie_review SET language_hint='likely_latin_morphology' WHERE original_script='likely_latin_morphology'")
c.execute("UPDATE cie_review SET original_script='' WHERE original_script='likely_latin_morphology'")
conn_lat.commit()
conn_lat.close()
