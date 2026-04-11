import sqlite3
import json
import urllib.request
import urllib.error
import time
from pathlib import Path

def get_gemini_api_key():
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    return line.strip().split("=")[1].strip('"\'')
    except Exception:
        pass
    return None

def call_gemini(api_key, system_prompt, chunks):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": system_prompt},
                {"text": "Here are the strings to cluster:\n" + "\n".join([f"ID {c[0]}: {c[1]}" for c in chunks])}
            ]
        }],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read()
            res_json = json.loads(res_body)
            raw_text = res_json['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw_text)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        print(e.read().decode())
        return None
    except Exception as e:
        print(f"API Error: {e}")
        return None

def main():
    api_key = get_gemini_api_key()
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        return

    db_path = Path("data/cie/findspots_geocoding.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, original_string FROM unique_findspots WHERE cluster_name IS NULL OR status='PENDING'")
    rows = cur.fetchall()

    if not rows:
        print("All findspots have already been clustered.")
        return

    print(f"Found {len(rows)} findspots to cluster.")

    SYSTEM_PROMPT = """
You are a Geographic AI specializing in Etruscan archaeology and Italian topography. 
You will receive a list of 19th-century academic site descriptions (mostly in Latin or Italian). 
Your task is to cluster these descriptions to identify the singular, canonical modern "Place Name" (Municipality, Province, or famous Archaeological Site) in Italy that represents the findspot.

Return ONLY a strict JSON Array of objects matching this exact schema:
[
  {
    "id": <the exactly provided ID integer>,
    "cluster_name": "Modern Canonical Place Name, Province, Italy",
    "approx_lat": <float estimated latitude>,
    "approx_lon": <float estimated longitude>
  }
]
Do not return anything else. Output pure JSON. Make sure you return an object for EVERY single ID provided.
"""

    BATCH_SIZE = 40
    
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        print(f"Processing batch {i} to {i+len(batch)} / {len(rows)}...")
        
        result = call_gemini(api_key, SYSTEM_PROMPT, batch)
        if result:
            update_data = []
            for item in result:
                try:
                    obj_id = int(item.get("id"))
                    cluster = str(item.get("cluster_name", ""))
                    lat = item.get("approx_lat")
                    lon = item.get("approx_lon")
                    update_data.append((cluster, lat, lon, "CLUSTER_GENERATED", obj_id))
                except Exception as e:
                    print(f"Skipping malformed json object: {item}")
                    
            if update_data:
                cur.executemany("""
                    UPDATE unique_findspots 
                    SET cluster_name=?, gemini_lat=?, gemini_lon=?, status=?
                    WHERE id=?
                """, update_data)
                conn.commit()
                print(f"Successfully committed batch {i}.")
        else:
            print("Failed to process chunk. Halting to prevent infinite loop.")
            break
            
        time.sleep(3)

    conn.close()

if __name__ == "__main__":
    main()
