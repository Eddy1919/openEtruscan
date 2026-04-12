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
report_path = repo_root / 'data' / 'cie' / 'rescued_grading_report.md'

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
        "classification": {
            "type": "STRING",
            "enum": ["Etruscan", "Latin", "Ambiguous", "Noise"],
            "description": "The philological classification of the inscription."
        },
        "confidence": {
            "type": "NUMBER",
            "description": "Confidence score from 0.0 to 1.0."
        },
        "reasoning": {
            "type": "STRING",
            "description": "Brief explanation of the classification."
        }
    },
    "required": ["classification", "confidence"]
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
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            text_resp = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # Remove markdown JSON blocks if present
            if text_resp.startswith("```json"):
                text_resp = text_resp.replace("```json", "", 1).replace("```", "", 1).strip()
            elif text_resp.startswith("```"):
                 text_resp = text_resp.replace("```", "", 2).strip()
                 
            return json.loads(text_resp)
    except Exception as e:
        print(f"\nAPI Error: {e}")
        return None

def grade_inscriptions():
    if not db_path.exists():
        print(f"File not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # We only grade items that haven't been graded yet
    cur.execute("SELECT cie_id, transliterated, latin_commentary FROM cie_review WHERE confidence IS NULL OR confidence = ''")
    rows = cur.fetchall()
    
    total_remaining = len(rows)
    print(f"Starting grading of {total_remaining} remaining inscriptions (Conservative Mode)...")
    
    graded_this_run = 0
    for row in rows:
        cie_id, transliterated, commentary = row
        try:
            print(f"[{graded_this_run + 1}/{total_remaining}] Grading CIE {cie_id}...", end='', flush=True)
            prompt = (
                f"You are a specialist in Etruscan and Latin epigraphy. Grade the following inscription found in the CIE archives.\n\n"
                f"CRITICAL INSTRUCTION: BE CONSERVATIVE. "
                f"If the text is very short (e.g. one name), fragmentary, or uses characters common to both languages without diagnostic phonemes (θ,ś,χ), mark as 'Ambiguous'. "
                f"Only mark as 'Etruscan' if there is clear linguistic evidence (syntax, specific phonemes, or explicit mention of Etruscan origin in the commentary).\n\n"
                f"CIE ID: {cie_id}\n"
                f"Transcription: {transliterated}\n"
                f"Commentary: {str(commentary)[:800] if commentary else ''}"
            )
            
            grading = call_gemini(prompt)
            if grading:
                cur.execute("""
                    UPDATE cie_review 
                    SET confidence = ?, classification = ?, notes = COALESCE(notes, '') || ?
                    WHERE cie_id = ?
                """, (
                    str(grading.get('confidence')), 
                    grading.get('classification'), 
                    f" [Grading: {grading.get('reasoning')}]",
                    cie_id
                ))
                conn.commit()
                graded_this_run += 1
                print(" OK.", flush=True)
            else:
                print(" FAILED (API Error).", flush=True)
                    
            time.sleep(1.2) # Conservative rate limit
        except Exception as e:
            print(f"\nCRITICAL ERROR on {cie_id}: {e}", flush=True)
            continue
            
    print(f"\nGrading batch complete. Graded {graded_this_run} items.")
    
    # Generate Summary Report
    cur.execute("SELECT classification, COUNT(*) FROM cie_review GROUP BY classification")
    stats = cur.fetchall()
    
    with open(report_path, "w") as f:
        f.write("# [GATE 4] Rescued Dataset Grading Audit\n\n")
        f.write("Gemini has performed a conservative philological assessment of the 1,280 rescued records.\n\n")
        f.write("## Distribution Summary\n")
        f.write("| Category | Count | Action |\n")
        f.write("| :--- | :--- | :--- |\n")
        for s in stats:
            action = "PROCEED TO INGESTION" if s[0] == "Etruscan" else "REMAIN IN QUARANTINE"
            f.write(f"| **{s[0]}** | {s[1]} | {action} |\n")
            
    print(f"Report generated: {report_path}")
    conn.close()

if __name__ == "__main__":
    grade_inscriptions()
