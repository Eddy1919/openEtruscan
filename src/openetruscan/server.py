"""
FastAPI REST wrapper for the OpenEtruscan corpus.

Provides full-text and native PostGIS spatial search capabilities via HTTP.
Run locally:
    uvicorn openetruscan.server:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openetruscan.corpus import Corpus

# Global corpus and graph instances (loaded on startup)
corpus = None
family_graph = None
insc_to_gens = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global corpus, family_graph, insc_to_gens
    # If DATABASE_URL is set, Corpus.load() connects to PostgreSQL automatically.
    # Otherwise, it falls back to the local SQLite offline copy.
    corpus = Corpus.load()

    # Initialize the Prosopographical Network Engine
    from openetruscan.prosopography import FamilyGraph
    family_graph = FamilyGraph.from_corpus(corpus)

    # Build reverse lookup for instant UI badge population
    insc_to_gens = {
        idx: p.gentilicium
        for p in family_graph.persons()
        for idx in p.inscription_ids
        if p.gentilicium
    }

    yield
    if corpus:
        corpus.close()


app = FastAPI(
    title="OpenEtruscan Corpus API",
    description="REST API for querying the OpenEtruscan dataset.",
    version="0.3",
    lifespan=lifespan,
)

# Allow CORS for static GitHub Pages frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InscriptionModel(BaseModel):
    id: str
    canonical: str
    phonetic: str
    old_italic: str
    raw_text: str
    findspot: str
    findspot_lat: float | None
    findspot_lon: float | None
    date_display: str
    medium: str
    object_type: str
    language: str
    classification: str
    gens: str | None = None


class SearchResponse(BaseModel):
    total: int
    count: int
    results: list[InscriptionModel]


def _build_model(i) -> InscriptionModel:
    return InscriptionModel(
        id=i.id,
        canonical=i.canonical,
        phonetic=i.phonetic,
        old_italic=i.old_italic,
        raw_text=i.raw_text,
        findspot=i.findspot,
        findspot_lat=i.findspot_lat,
        findspot_lon=i.findspot_lon,
        date_display=i.date_display(),
        medium=i.medium,
        object_type=i.object_type,
        language=i.language,
        classification=i.classification,
        gens=insc_to_gens.get(i.id),
    )


@app.get("/search", response_model=SearchResponse)
def search_corpus(
    text: str | None = Query(None, description="Wildcard text search (e.g. *larth*)"),
    findspot: str | None = Query(None, description="Findspot name"),
    language: str | None = Query(None, description="Language filter"),
    classification: str | None = Query(None, description="Classification filter"),
    limit: int = 100,
):
    """Search by text, location, or metadata."""
    results = corpus.search(
        text=text,
        findspot=findspot,
        language=language,
        classification=classification,
        limit=limit,
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/radius", response_model=SearchResponse)
def search_by_radius(
    lat: float = Query(..., description="Latitude of center point"),
    lon: float = Query(..., description="Longitude of center point"),
    radius_km: float = Query(50.0, description="Radius in kilometers"),
    limit: int = 100,
):
    """Search by spatial radius."""
    results = corpus.search_radius(lat=lat, lon=lon, radius_km=radius_km, limit=limit)
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/clan/{gens}", response_model=SearchResponse)
def search_by_clan(gens: str):
    """Prosopographical network search."""
    clan_info = family_graph.clan(gens)
    if not clan_info:
        return {"total": 0, "count": 0, "results": []}

    member_insc_ids = []
    for member in clan_info.members:
        member_insc_ids.extend(member.inscription_ids)

    results = corpus.search(limit=99999)
    id_set = set(member_insc_ids)
    matching = [i for i in results.inscriptions if i.id in id_set]

    data = [_build_model(i) for i in matching]
    return {"total": len(data), "count": len(data), "results": data}


@app.get("/stats")
def corpus_stats():
    """Get corpus counts."""
    return {"total_inscriptions": corpus.count()}
