import sqlite3
import os
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

# Setup paths
repo_root = Path(__file__).resolve().parent.parent.parent
db_path = repo_root / 'data' / 'cie' / 'databases' / 'cie_rescued.db'

# API Key
env_path = repo_root / ".env"
api_key = os.getenv("GEMINI_API_KEY")
if not api_key and env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.strip().split('=', 1)[1].strip().strip('"').strip("'")
                break

if not api_key:
    print("Error: GEMINI_API_KEY not found.")
    exit(1)

gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

gemini_schema = {
    "type": "OBJECT",
    "properties": {
        "modern_location": {
            "type": "STRING",
            "description": "Modern name of the findspot."
        },
        "lat": {
            "type": "NUMBER",
            "description": "Latitude of the findspot."
        },
        "lon": {
            "type": "NUMBER",
            "description": "Longitude of the findspot."
        },
        "uncertainty_m": {
            "type": "NUMBER",
            "description": "Uncertainty in meters (e.g. 5000 for city, 500 for specific site)."
        },
        "salvaged_transliteration": {
            "type": "STRING",
            "description": "The salvaged Etruscan inscription text, if found in commentary. Else null."
        },
        "reasoning": {
            "type": "STRING",
            "description": "Brief explanation of the location extraction."
        }
    },
    "required": ["modern_location", "lat", "lon"]
}

def call_gemini(prompt, retries=3):
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": gemini_schema,
            "temperature": 0.1
        }
    }
    
    for attempt in range(retries):
        req = urllib.request.Request(gemini_url, json.dumps(data).encode('utf-8'), {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                text_resp = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                
                if text_resp.startswith("```json"):
                    text_resp = text_resp.replace("```json", "", 1).replace("```", "", 1).strip()
                elif text_resp.startswith("```"):
                     text_resp = text_resp.replace("```", "", 2).strip()
                     
                return json.loads(text_resp)
        except Exception as e:
            wait_time = (attempt + 1) * 5
            print(f"\nAPI Attempt {attempt+1} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    return None

def geocode_batch():
    if not db_path.exists():
        print(f"File not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Select confirmed Etruscan records that need geocoding or salvage
    cur.execute("""
        SELECT cie_id, transliterated, latin_findspot, latin_commentary 
        FROM cie_review 
        WHERE classification = 'Etruscan' 
        AND (findspot_lat IS NULL OR transliterated = 'N/A' OR transliterated IS NULL)
    """)
    rows = cur.fetchall()
    
    print(f"Hardening {len(rows)} verified Etruscan records...")
    
    processed_count = 0
    for row in rows:
        cie_id, transliterated, findspot, commentary = row
        try:
            print(f"[{processed_count + 1}/{len(rows)}] Hardening CIE {cie_id}...", end='', flush=True)
            
            prompt = (
                f"You are an expert in Etruscan archaeology and geography.\n"
                f"Extract the modern location and precise coordinates for this CIE inscription site.\n\n"
                f"CIE ID: {cie_id}\n"
                f"Findspot (Latin): {findspot}\n"
                f"Commentary: {str(commentary)[:1000]}\n"
                f"Current Transliteration: {transliterated}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Identify the modern city (e.g. Chiusi, Perugia, Arezzo) and specific site.\n"
                f"2. Provide decimal coordinates (Lat, Lon).\n"
                f"3. If 'Current Transliteration' is 'N/A', look closely at the Commentary. Often the text is cited there (e.g. 'larθia...'). Extract it into salvaged_transliteration."
            )
            
            result = call_gemini(prompt)
            if result:
                # Update DB
                update_fields = []
                params = []
                
                if result.get('lat'):
                    update_fields.append("findspot_lat = ?")
                    params.append(result.get('lat'))
                if result.get('lon'):
                    update_fields.append("findspot_lon = ?")
                    params.append(result.get('lon'))
                if result.get('modern_location'):
                    update_fields.append("findspot_modern = ?")
                    params.append(result.get('modern_location'))
                if result.get('uncertainty_m'):
                    update_fields.append("uncertainty_m = ?")
                    params.append(result.get('uncertainty_m'))
                
                # Salvage transliteration if missing
                if (transliterated == 'N/A' or not transliterated) and result.get('salvaged_transliteration'):
                    update_fields.append("transliterated = ?")
                    params.append(result.get('salvaged_transliteration'))
                
                if update_fields:
                    query = f"UPDATE cie_review SET {', '.join(update_fields)} WHERE cie_id = ?"
                    params.append(cie_id)
                    cur.execute(query, params)
                    conn.commit()
                    processed_count += 1
                    print(" OK.", flush=True)
                else:
                    print(" SKIPPED (No data found).", flush=True)
            else:
                print(" FAILED (API Error).", flush=True)
                
            time.sleep(1.2) # Rate limit safety
        except Exception as e:
            print(f"\nError on {cie_id}: {e}", flush=True)
            continue
            
    conn.close()
    print(f"\nHardening complete. Processed {processed_count} records.")

if __name__ == "__main__":
    geocode_batch()
