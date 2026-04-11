#!/usr/bin/env python3
"""
Mapbox Fallback Geocoding script.
Finds inscriptions with 'findspot' strings but missing spatial coordinates, 
queries Mapbox Places API, and backfills PostGIS coordinates.
"""
import asyncio
import os
import sys
import httpx
from pathlib import Path
from sqlalchemy import text, select, and_

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from openetruscan.db.session import get_engine
from openetruscan.db.models import Inscription
from dotenv import load_dotenv

load_dotenv()

async def geocode():
    mapbox_token = os.getenv("MAPBOX_SECRET_TOKEN") or os.getenv("MAPBOX_PUBLIC_TOKEN")
    if not mapbox_token:
        print("ERROR: Required MAPBOX_SECRET_TOKEN not found in environment.")
        return
        
    _, SessionLocal = get_engine()
    
    print("🌍 Starting Semantic Geocoding Pipeline via Mapbox API...")
    
    async with SessionLocal() as session:
        stmt = select(Inscription).where(
            and_(
                Inscription.findspot.is_not(None),
                Inscription.findspot != '',
                Inscription.findspot_lat.is_(None)
            )
        )
        result = await session.execute(stmt)
        inscriptions = result.scalars().all()
        
        if not inscriptions:
            print("✅ No inscriptions require text-geocoding.")
            return
            
        print(f"📍 Found {len(inscriptions)} unmapped text locations. Initiating Mapbox resolution...")
        
        updated = 0
        cache = {}
        
        async with httpx.AsyncClient() as client:
            for insc in inscriptions:
                fs = insc.findspot.strip()
                if not fs:
                    continue
                    
                if fs in cache:
                    lon, lat = cache[fs]
                else:
                    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{fs}.json"
                    try:
                        res = await client.get(url, params={"access_token": mapbox_token, "limit": 1})
                        if res.status_code == 200:
                            data = res.json()
                            features = data.get("features", [])
                            if features:
                                lon, lat = features[0]["center"] # Mapbox returns [longitude, latitude]
                                cache[fs] = (lon, lat)
                            else:
                                cache[fs] = (None, None)
                        else:
                            cache[fs] = (None, None)
                    except Exception as e:
                         cache[fs] = (None, None)
                         print(f"API Error on {fs}: {e}")
                    
                    # Prevent rapid rate-limiting blocks
                    await asyncio.sleep(0.1)
                    
                lon, lat = cache[fs]
                if lon is not None and lat is not None:
                    insc.findspot_lon = lon
                    insc.findspot_lat = lat
                    
                    await session.execute(
                        text("""
                            UPDATE inscriptions 
                            SET geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                            WHERE id = :id
                        """),
                        {"lon": lon, "lat": lat, "id": insc.id}
                    )
                    updated += 1
                    print(f"🗺️ Mapped [{insc.id}] '{fs}' -> ({lat}, {lon})")
                else:
                    print(f"❌ Mapbox couldn't resolve: '{fs}'")
                    
        # Write everything into the remote Enterprise PostgreSQL cluster
        await session.commit()
        print(f"\n🎉 Operations successful! Bound {updated} new spatial geometries!")

if __name__ == "__main__":
    asyncio.run(geocode())
