import csv
import sys

def main():
    csv_file = "openetruscan_clean.csv"

    # Emit ALTER TABLE statements
    print("BEGIN;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS canonical_clean TEXT;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS old_italic_v2 TEXT;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS data_quality TEXT;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS translation TEXT;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS canonical_words_only TEXT;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS year_from INTEGER;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS year_to INTEGER;")
    print("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS intact_token_ratio REAL;")

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record_id = row["id"].replace("'", "''")
            
            # Helper to safely quote strings or emit NULL
            def q(val):
                if not val.strip():
                    return "NULL"
                return "'" + val.replace("'", "''") + "'"

            # Helper for numbers
            def q_num(val):
                if not val.strip():
                    return "NULL"
                return val.strip()

            translation = q(row["translation"])
            year_from = q_num(row["year_from"])
            year_to = q_num(row["year_to"])
            canonical_words_only = q(row["canonical_words_only"])
            intact_token_ratio = q_num(row["intact_token_ratio"])
            
            sql = f"""UPDATE inscriptions SET
                translation = {translation},
                year_from = {year_from},
                year_to = {year_to},
                canonical_words_only = {canonical_words_only},
                intact_token_ratio = {intact_token_ratio}
                WHERE id = '{record_id}';"""
            
            print(sql)

    print("COMMIT;")

if __name__ == "__main__":
    main()
