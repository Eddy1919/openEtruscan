#!/usr/bin/env python3
import json
import sys
import subprocess
import tempfile
from pathlib import Path

# Add src to the sys path so we can invoke the core codebase
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from openetruscan.core.corpus import Corpus, Inscription

def human_review():
    base_dir = Path(__file__).resolve().parent.parent.parent / "data/cie"
    pending_file = base_dir / "curated_pending.json"
    
    if not pending_file.exists():
        print("No pending review items found.")
        return
        
    data = json.loads(pending_file.read_text())
    if not data:
        print("Queue is empty. Everything reviewed!")
        return

    # Connect to PostgreSQL via the internal Corpus API wrapper
    print("🔌 Connecting to PostgreSQL Engine...")
    corpus = Corpus.load()
    
    print("\n" + "="*50)
    print(f" HUMAN-IN-THE-LOOP (HITL) REVIEW QUEUE ")
    print(f" Items pending structural approval: {len(data)}")
    print(" KEYBINDINGS: [y] Accept, [n] Reject, [e] Edit, [q] Quit CLI")
    print("="*50 + "\n")
    
    remaining = []
    
    for idx, item in enumerate(data):
        cie_id = item.get("cie_id", "Unknown")
        fs = item.get("latin_findspot", "")
        text_t = item.get("etruscan_text_transliterated", "")
        notes = item.get("latin_commentary", "")
        lat = item.get("auto_lat")
        lon = item.get("auto_lon")
        
        print("\n" + "-" * 60)
        print(f"📄 RECORD {idx+1}/{len(data)} | ID: \033[96m{cie_id}\033[0m")
        print(f"📜 TEXT:      \033[93m{text_t}\033[0m")
        print(f"📍 FINDSPOT:  {fs} (Autopath: {lat}, {lon})")
        print(f"📝 NOTES:     {notes[:150]}...")
        
        while True:
            choice = input(f"👉 Accept? [y/n/e/q]: ").strip().lower()
            if choice in ['y', 'n', 'e', 'q']:
                break
                
        if choice == 'q':
            # Halt session and persist exact queue state
            remaining.extend(data[idx:])
            break
        elif choice == 'n':
            print("   🚫 Rejected entry.")
            continue
        elif choice == 'e':
            # Hook the system editor (defaulting to nano for fastest access)
            print("   Opening item in Nano editor. Save standardly to propagate modifications.")
            with tempfile.NamedTemporaryFile(suffix=".json", mode="w+") as tf:
                json.dump(item, tf, indent=2)
                tf.flush()
                subprocess.call(['nano', tf.name])
                tf.seek(0)
                try:
                    item = json.load(tf)
                except Exception as e:
                    print(f"   ⚠️ Invalid JSON structure returned from system editor! Item bypassed to prevent data poison. {e}")
                    remaining.append(item)
                    continue
            choice = 'y'

        if choice == 'y':
            canonical_id = item.get("cie_id", "").replace("CIE ", "").replace("CIE", "").strip()
            formatted_id = f"CIE {canonical_id}"
            
            insc = Inscription(
                id=formatted_id,
                canonical=item.get("etruscan_text_transliterated", ""),
                raw_text=item.get("etruscan_text_original") or item.get("etruscan_text_transliterated", ""),
                findspot=item.get("latin_findspot", ""),
                findspot_lat=item.get("auto_lat"),
                findspot_lon=item.get("auto_lon"),
                notes=item.get("latin_commentary", ""),
                bibliography=item.get("bibliography") or "",
                source="CIE Volume I (HITL Approved)",
                provenance_status="verified"
            )
            try:
                corpus.add(insc)
                print(f"   ✅ Merged \033[92m{formatted_id}\033[0m firmly into PostgreSQL layer.")
            except Exception as e:
                print(f"   ❌ DB Synchronization Failure for {formatted_id}: {e}")
                remaining.append(item)

    # Persist un-reviewed queue blocks
    pending_file.write_text(json.dumps(remaining, indent=2))
    corpus.close()
    print("\n🏁 Session finalized. TUI Closed.")

if __name__ == "__main__":
    human_review()
