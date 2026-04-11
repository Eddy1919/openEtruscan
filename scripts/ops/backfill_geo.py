#!/usr/bin/env python3
"""
Backfills geographic coordinates for inscriptions referencing Pleiades IDs.
Queries the Pleiades API directly to get longitude and latitude.
Also updates the PostGIS `geom` column using standard spatial functions.
"""
import asyncio
import httpx
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openetruscan.db.session import get_engine
from openetruscan.db.models import Inscription
from sqlalchemy import select, and_

async def backfill_geo():
    print("🌍 Starting Geographical Backfill from Pleiades API...")
    
    _, SessionLocal = get_engine()
    async with SessionLocal() as session:
        # Select inscriptions that have a pleiades ID but lack lat/lon
        stmt = select(Inscription).where(
            and_(
                Inscription.pleiades_id.is_not(None),
                Inscription.findspot_lat.is_(None)
            )
        )
        result = await session.execute(stmt)
        inscriptions = result.scalars().all()
        
        if not inscriptions:
            print("✅ All inscriptions with Pleiades IDs already have geographic data mapped!")
            return
            
        print(f"📍 Found {len(inscriptions)} inscriptions needing geographic backfill.")
        
        updated_count = 0
        async with httpx.AsyncClient() as client:
            for insc in inscriptions:
                # pleiades_id is usually a numeric string e.g. "413009"
                pid = str(insc.pleiades_id).split("/")[-1].strip()
                url = f"https://pleiades.stoa.org/places/{pid}/json"
                try:
                    res = await client.get(url, timeout=10.0)
                    if res.status_code == 200:
                        data = res.json()
                        repr_point = data.get("reprPoint")
                        if repr_point and len(repr_point) == 2:
                            lon, lat = repr_point
                            
                            # Update SQLAlchemy Model
                            insc.findspot_lon = lon
                            insc.findspot_lat = lat
                            
                            # Execute raw SQL to sync geometry
                            await session.execute(
                                text("""
                                    UPDATE inscriptions 
                                    SET geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                                    WHERE id = :id
                                """),
                                {"lon": lon, "lat": lat, "id": insc.id}
                            )
                            
                            updated_count += 1
                            print(f"[SUCCESS] {insc.id} -> mapped to Pleiades {pid} ({lat}, {lon})")
                        else:
                            print(f"[WARN] {insc.id} -> Pleiades {pid} has no representative point.")
                    elif res.status_code == 404:
                         print(f"[WARN] {insc.id} -> Pleiades {pid} not found (404).")
                    else:
                        print(f"[ERROR] {insc.id} -> API returned {res.status_code}")
                except Exception as e:
                    print(f"[ERROR] Failed to fetch {pid} for {insc.id}: {e}")
                
                # Throttle slightly to respect Pleiades server limits
                await asyncio.sleep(0.2)
                
        # Commit the transaction block containing all the models and manual geometry updates
        await session.commit()
        print(f"\n🎉 Successfully backfilled {updated_count} records with geo-coordinates! Your map visuals will now populate.")

if __name__ == "__main__":
    asyncio.run(backfill_geo())
