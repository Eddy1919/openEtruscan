#!/usr/bin/env python3
"""
Pleiades alignment audit script.
Enforces geographic standards by matching findspots and Pleiades IDs.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openetruscan.db.session import async_session
from openetruscan.db.repository import InscriptionRepository

async def audit_pleiades():
    print("🔍 Auditing 11,000+ findings for Pleiades alignment...")
    
    async with async_session() as session:
        repo = InscriptionRepository(session)
        result = await repo.validate_pleiades_ids()
        
        total = result["total_checked"]
        invalid = result["invalid_ids"]
        
        print(f"✅ Total inscriptions checked: {total}")
        
        if invalid:
            print(f"❌ Found {len(invalid)} invalid Pleiades ID formats:")
            for item in invalid[:10]:
                print(f"   - {item['id']}: {item['pleiades_id']} ({item['reason']})")
            if len(invalid) > 10:
                print(f"   ... and {len(invalid) - 10} more.")
        else:
            print("✨ All existing Pleiades IDs follow standard numeric format.")

        # Check for missing coordinates where Pleiades ID exists
        # (This is a simplified check, a real one would call Pleiades API)
        print("\n📍 Checking coordinate coverage...")
        repo_session = repo.session
        from sqlalchemy import select, and_
        from openetruscan.db.models import Inscription
        
        stmt = select(Inscription.id).where(
            and_(
                Inscription.pleiades_id.is_not(None),
                Inscription.findspot_lat.is_(None)
            )
        )
        missing_count = len((await repo_session.execute(stmt)).fetchall())
        print(f"📊 Inscriptions with Pleiades ID but missing coordinates: {missing_count}")

if __name__ == "__main__":
    asyncio.run(audit_pleiades())
