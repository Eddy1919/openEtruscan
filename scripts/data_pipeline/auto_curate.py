#!/usr/bin/env python3
import json
from pathlib import Path

# Semantic overrides mapping Latin locatives to coordinates
LLM_GEO_MAPPING = {
    'Clusii in agro': (43.0174, 11.9492),
    'Clusii': (43.0174, 11.9492),
    'Perusiae': (43.1107, 12.3908),
    'Volaterris': (43.4015, 10.8619),
    'Arretii': (43.4613, 11.8802),
    'Faesulis': (43.8059, 11.2944),
    'Cortonae': (43.2754, 11.9858),
    'Vulcis': (42.4212, 11.6323),
    'Caere': (42.0009, 12.1067),
    'Tarquiniis': (42.2488, 11.7553),
    'Volsiniis': (42.7182, 11.875)
}

def auto_curate():
    base_dir = Path(__file__).resolve().parent.parent.parent / "data/cie"
    raw_file = base_dir / "full_extraction.json"
    out_file = base_dir / "curated_pending.json"
    
    if not raw_file.exists():
        print(f"File {raw_file} not found. Run extraction pipeline first.")
        raw_file.parent.mkdir(parents=True, exist_ok=True)
        raw_file.write_text("[]")
    
    raw_data = json.loads(raw_file.read_text() or "[]")
    curated = []
    
    print("🤖 Starting Auto-Curation pass...")
    
    for item in raw_data:
        cie_id = item.get("cie_id", "")
        text_t = item.get("etruscan_text_transliterated", "")
        
        # Coherency Rule: Must have an ID and valid text length
        if not cie_id or not text_t or len(text_t) < 2:
            print(f"   🗑️  Discarded incoherent: {cie_id} | {text_t}")
            continue
            
        # Geographic Semantic Alignment
        fs = item.get("latin_findspot", "")
        for target, coords in LLM_GEO_MAPPING.items():
            if target.lower() in fs.lower():
                item["auto_lat"] = coords[0]
                item["auto_lon"] = coords[1]
                break
                
        curated.append(item)
        
    out_file.write_text(json.dumps(curated, indent=2))
    print(f"✅ Auto-curation complete. {len(curated)} items are structurally sound and awaiting human review.")

if __name__ == "__main__":
    auto_curate()
