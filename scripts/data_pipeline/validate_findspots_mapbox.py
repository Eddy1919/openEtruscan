import sqlite3
import json
import urllib.request
import urllib.parse
import urllib.error
import math
from pathlib import Path

def get_mapbox_token():
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("MAPBOX_SECRET_TOKEN="):
                    return line.strip().split("=")[1].strip('"\'')
    except Exception:
        pass
    return None

def haversine(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    R = 6371.0 # Earth radius in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def geocode_mapbox(place_name, token):
    encoded_name = urllib.parse.quote(place_name)
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded_name}.json?access_token={token}&autocomplete=false&limit=1"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            if data['features']:
                # Mapbox returns [lon, lat]
                lon, lat = data['features'][0]['geometry']['coordinates']
                return lat, lon
            return None, None
    except Exception as e:
        print(f"Mapbox API error for '{place_name}': {e}")
        return None, None

def main():
    token = get_mapbox_token()
    if not token:
        print("ERROR: MAPBOX_SECRET_TOKEN not found in .env")
        return

    db_path = Path("data/cie/findspots_geocoding.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Fetch all unique clusters to Geocode
    cur.execute("SELECT DISTINCT cluster_name FROM unique_findspots WHERE cluster_name IS NOT NULL AND status='CLUSTER_GENERATED'")
    clusters = [r[0] for r in cur.fetchall()]
    
    if not clusters:
        print("No pending clusters to validate.")
        return

    print(f"Querying Mapbox for {len(clusters)} distinct standard clusters...")
    
    cluster_cache = {}
    for cl in clusters:
        # Avoid redundant calls
        lat, lon = geocode_mapbox(cl, token)
        cluster_cache[cl] = (lat, lon)
        print(f"Mapbox -> '{cl}': {lat}, {lon}")

    # 2. Update Database row by row
    cur.execute("SELECT id, cluster_name, gemini_lat, gemini_lon FROM unique_findspots WHERE status='CLUSTER_GENERATED'")
    rows = cur.fetchall()

    update_data = []
    
    for row in rows:
        rowid = row[0]
        cluster = row[1]
        g_lat = row[2]
        g_lon = row[3]
        
        m_lat, m_lon = cluster_cache.get(cluster, (None, None))
        
        dist = haversine(g_lat, g_lon, m_lat, m_lon)
        
        status = "MANUAL_REVIEW_NEEDED"
        if m_lat is not None and g_lat is not None:
            if dist <= 15.0:  # Within 15 kilometers = verified
                status = "VERIFIED"
                
        update_data.append((m_lat, m_lon, dist, status, rowid))

    cur.executemany("""
        UPDATE unique_findspots
        SET mapbox_lat=?, mapbox_lon=?, distance_km=?, status=?
        WHERE id=?
    """, update_data)
    
    conn.commit()
    print("Validation and Haversine grading complete!")
    
    # 3. Print Summary
    cur.execute("SELECT status, COUNT(*) FROM unique_findspots GROUP BY status")
    for r in cur.fetchall():
        print(f"Status '{r[0]}': {r[1]} rows")
        
    conn.close()

if __name__ == "__main__":
    main()
