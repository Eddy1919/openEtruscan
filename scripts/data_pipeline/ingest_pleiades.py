import csv
import gzip
import json
import urllib.request
import os

URL = "http://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz"
OUTPUT_FILE = "../../openEtruscan-frontend/public/data/pleiades-network.geojson"

def download_and_process():
    print("Downloading Pleiades data...")
    response = urllib.request.urlopen(URL)
    compressed_file = response.read()
    
    print("Decompressing and parsing...")
    data = gzip.decompress(compressed_file).decode('utf-8').splitlines()
    reader = csv.DictReader(data)
    
    features = []
    
    # Bounding box for Italy/Etruscan expansion sphere
    MIN_LAT, MAX_LAT = 40.0, 45.5
    MIN_LON, MAX_LON = 9.0, 14.5
    
    for row in reader:
        try:
            lat = float(row['reprLat'])
            lon = float(row['reprLong'])
        except (ValueError, TypeError):
            continue
            
        if not (MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON):
            continue
            
        time_periods = row.get('timePeriods', '')
        feature_types = row.get('featureTypes', '').lower()
        
        # Look for Archaic (A), Classical (C), or Hellenistic (H)
        if not any(period in time_periods for period in ['A', 'C', 'H']):
            continue
            
        # Look for settlement-like features
        valid_features = ['settlement', 'fort', 'temple', 'station', 'city', 'town']
        if not any(vf in feature_types for vf in valid_features):
            continue
            
        feature = {
            "type": "Feature",
            "properties": {
                "id": row['id'],
                "title": row['title'],
                "description": row['description'],
                "uri": f"https://pleiades.stoa.org/places/{row['id']}",
                "time_periods": time_periods,
                "feature_types": feature_types
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            }
        }
        features.append(feature)
        
    print(f"Extracted {len(features)} relevant locations.")
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False)
        
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    download_and_process()
