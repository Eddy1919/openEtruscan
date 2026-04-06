import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from openetruscan.db.models import Base, Entity, Relationship, Clan
from openetruscan.db.repository import InscriptionRepository, InscriptionData

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)

@pytest.fixture(scope="module", autouse=True)
async def setup_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session():
    async with async_session() as session:
        yield session

@pytest.mark.asyncio
async def test_get_concordance_network(db_session: AsyncSession):
    repo = InscriptionRepository(db_session)
    
    # 1. Create linked inscriptions
    ins1 = InscriptionData(id="INS_1", trismegistos_id="TM_1", raw_text="...", canonical="...", findspot="...", medium="stone", object_type="stele", language="etruscan", classification="funerary")
    ins2 = InscriptionData(id="INS_2", trismegistos_id="TM_1", raw_text="...", canonical="...", findspot="...", medium="stone", object_type="stele", language="etruscan", classification="funerary")
    ins3 = InscriptionData(id="INS_3", eagle_id="E_1", raw_text="...", canonical="...", findspot="...", medium="stone", object_type="stele", language="etruscan", classification="funerary")
    ins4 = InscriptionData(id="INS_4", raw_text="...", canonical="...", findspot="...", medium="stone", object_type="stele", language="etruscan", classification="funerary") # Unrelated
    
    await repo.add(ins1)
    await repo.add(ins2)
    await repo.add(ins3)
    await repo.add(ins4)
    await db_session.commit()
    
    # 2. Test concordance
    network = await repo.get_concordance_network("INS_1")
    ids = [i.id for i in network]
    assert "INS_1" in ids
    assert "INS_2" in ids
    assert "INS_4" not in ids

@pytest.mark.asyncio
async def test_get_names_network(db_session: AsyncSession):
    repo = InscriptionRepository(db_session)
    
    # 1. Add inscription
    await repo.add(InscriptionData(id="INS_5", raw_text="...", canonical="...", findspot="...", medium="stone", object_type="stele", language="etruscan", classification="funerary"))
    
    # 2. Add Entities
    e1 = Entity(id="P1", name="Larth", inscription_id="INS_5")
    e2 = Entity(id="P2", name="Arnth", inscription_id="INS_5")
    db_session.add_all([e1, e2])
    await db_session.flush()
    
    # 3. Add Clan
    clan = Clan(id="C1", name="Tite")
    db_session.add(clan)
    await db_session.flush()
    
    # 4. Add Relationship
    rel = Relationship(
        person_id="P1",
        related_person_id="P2",
        relationship_type="brother"
    )
    rel2 = Relationship(
        person_id="P1",
        clan_id="C1",
        relationship_type="member_of"
    )
    db_session.add_all([rel, rel2])
    await db_session.commit()
    
    # 5. Test network
    graph = await repo.get_names_network("INS_5")
    
    node_ids = [n["id"] for n in graph["nodes"]]
    assert "ins:INS_5" in node_ids
    assert "P1" in node_ids
    assert "P2" in node_ids
    assert "C1" in node_ids
    
    edges = graph["edges"]
    assert any(e["from"] == "P1" and e["to"] == "P2" and e["label"] == "brother" for e in edges)
    assert any(e["from"] == "P1" and e["to"] == "C1" and e["label"] == "member_of" for e in edges)
