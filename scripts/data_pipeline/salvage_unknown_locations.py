import sqlite3
import os
import time
from pathlib import Path
import json
import urllib.request
import urllib.error

# Setup paths
repo_root = Path(__file__).resolve().parent.parent.parent
db_dir = repo_root / 'data' / 'cie' / 'databases'
unknown_db = db_dir / 'cie_etruscan_unknown.db'
report_path = repo_root / 'data' / 'cie' / 'salvaged_locations_report.md'

# Load API Key manually if dotenv is not available
env_path = repo_root / ".env"
api_key = os.getenv("GEMINI_API_KEY")
if not api_key and env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.strip().split('=', 1)[1].strip().strip('"').strip("'")
                break

if not api_key:
    print("Error: GEMINI_API_KEY not found in env or .env file.")
    exit(1)

gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

gemini_schema = {
    "type": "OBJECT",
    "properties": {
        "found_location": {
            "type": "BOOLEAN",
            "description": "True if a location can be extracted from the commentary."
        },
        "extracted_toponym": {
            "type": "STRING",
            "description": "The exact Latin or Italian location phrase from the text (e.g. 'Clusii'). Null if none."
        },
        "modern_guess": {
            "type": "STRING",
            "description": "Your best guess mapping the Latin toponym to a modern Italian place (e.g. 'Chiusi'). Null if none."
        },
        "reasoning": {
            "type": "STRING",
            "description": "Brief explanation."
        }
    },
    "required": ["found_location"]
}

def call_gemini(prompt):
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": gemini_schema,
            "temperature": 0.1
        }
    }
    
    req = urllib.request.Request(gemini_url, json.dumps(data).encode('utf-8'), {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            # Extracted text is deeply nested in Gemini payload
            text_resp = res_json['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def salvage_locations():
    if not unknown_db.exists():
        print(f"File not found: {unknown_db}")
        return

    conn = sqlite3.connect(unknown_db)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT cie_id, transliterated, latin_commentary 
        FROM cie_review 
        WHERE (latin_findspot IS NULL OR latin_findspot LIKE '%N/A%' OR latin_findspot == '')
        AND LENGTH(latin_commentary) > 20
    """)
    rows = cur.fetchall()
    
    results = []
    print(f"Found {len(rows)} candidates for location salvage.")
    
    for row in rows:
        cie_id, transliterated, commentary = row
        prompt = (
            f"You are an expert epigrapher. I have an Etruscan inscription without a recorded findspot. "
            f"Please read the following Latin commentary from the Corpus Inscriptionum Etruscarum (CIE) "
            f"and extract any mention of the place where it was found (ex sepulcro, agro, near a city, etc).\n\n"
            f"CIE ID: {cie_id}\n"
            f"Text: {transliterated}\n"
            f"Commentary: {commentary}"
        )
        
        data = call_gemini(prompt)
        if data and data.get("found_location"):
            results.append({
                "cie_id": cie_id,
                "text": transliterated,
                "commentary_snippet": commentary[:150] + "...",
                "extracted": data.get("extracted_toponym"),
                "modern": data.get("modern_guess"),
                "reasoning": data.get("reasoning")
            })
        print('.', end='', flush=True)
        time.sleep(0.5)
            
    print(f"\nSalvaged {len(results)} locations.")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# [GATE 1] Location Salvage Review Report\n\n")
        f.write("The Gemini LLM has analyzed the `latin_commentary` of records missing a findspot. Please review the extracted locations below.\n\n")
        
        f.write("| CIE ID | Extracted Toponym | Modern Guess | Reasoning | Text |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for res in results:
            text_snip = str(res['text']).replace('\n', ' ')[:30] + "..." if res['text'] else ""
            f.write(f"| {res['cie_id']} | **{res['extracted']}** | {res['modern']} | {res['reasoning']} | {text_snip} |\n")
            
    print(f"Report written to {report_path}")
    conn.close()

if __name__ == "__main__":
    salvage_locations()
