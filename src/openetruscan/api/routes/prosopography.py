"""Names networks, clans, and the family-graph exports."""

import asyncio
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import MAX_GENS_LEN, limiter
from openetruscan.api.schemas import SearchResponse, _build_model
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

router = APIRouter()


@router.get("/inscription/{inscription_id}/names-network", tags=["Prosopography"])
@limiter.limit("60/minute")
async def get_inscription_names_network(
    request: Request, inscription_id: str, session: AsyncSession = Depends(get_session)
):
    """
    Fetch a graph representation (nodes/edges) of entities and relationships
    associated with this inscription.
    """
    repo = InscriptionRepository(session)
    graph = await repo.get_names_network(inscription_id)
    if not graph or not graph.get("nodes"):
        # We still return the empty graph structure if no entities are found,
        # but 404 if the inscription itself is missing would be handled by common logic.
        return {"nodes": [], "edges": []}

    return graph


@router.get("/names/network", tags=["Prosopography"])
@limiter.limit("150/minute")
async def names_network(
    request: Request,
    min_count: Annotated[
        int,
        Query(ge=1, le=100, description="Minimum attestations to include"),
    ] = 5,
    session: AsyncSession = Depends(get_session),
):
    """
    Prosopographic co-occurrence network endpoint.
    Fetches frequent name relationships from the database and returns a node/edge graph.
    """
    # Initialize repository with session
    repo = InscriptionRepository(session)
    # Fetch data from repository
    return await repo.get_full_names_network(min_count=min_count)


@router.get("/clan/{gens}", response_model=SearchResponse, tags=["Prosopography"])
@limiter.limit("30/minute")
async def search_by_clan(
    request: Request,
    gens: Annotated[
        str,
        Path(description="Gentilicium (clan name) to search for"),
    ],
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Prosopographical network search by clan/gens."""

    # Validate gens - allow letters, spaces, and hyphens
    if not re.match(r"^[\w\s\-]+$", gens, re.UNICODE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gens contains invalid characters",
        )

    if len(gens) > MAX_GENS_LEN:
        return {"total": 0, "count": 0, "results": []}

    repo = InscriptionRepository(session)
    results = await repo.search_clan_members(gens)

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


_FAMILY_GRAPH_CACHE = None
_FAMILY_GRAPH_LOCK = None


async def _get_family_graph(repo: InscriptionRepository, language: str = "etruscan") -> Any:
    """Returns a cached FamilyGraph, building it once upon first request."""
    global _FAMILY_GRAPH_CACHE, _FAMILY_GRAPH_LOCK

    if _FAMILY_GRAPH_CACHE is not None:
        return _FAMILY_GRAPH_CACHE

    if _FAMILY_GRAPH_LOCK is None:
        _FAMILY_GRAPH_LOCK = asyncio.Lock()

    async with _FAMILY_GRAPH_LOCK:
        if _FAMILY_GRAPH_CACHE is None:
            _FAMILY_GRAPH_CACHE = await _build_family_graph(repo, language)
        return _FAMILY_GRAPH_CACHE


async def _build_family_graph(repo: InscriptionRepository, language: str = "etruscan") -> Any:
    """Async wrapper to build the FamilyGraph from the Async InscriptionRepository."""
    from openetruscan.core.adapter import load_adapter
    from openetruscan.core.prosopography import FamilyGraph, Person, parse_name

    graph = FamilyGraph()
    person_id = 0
    batch_size = 500
    offset = 0
    adapter = load_adapter(language)

    while True:
        results = await repo.search(limit=batch_size, offset=offset)
        if not results.inscriptions:
            break

        for inscription in results.inscriptions:
            if not inscription.canonical.strip():
                continue

            formula = parse_name(inscription.canonical, language=language, adapter=adapter)
            person = Person(
                id=f"P{person_id:05d}",
                name_formula=formula,
                inscription_ids=[inscription.id],
                findspots=[inscription.findspot] if inscription.findspot else [],
            )
            graph.add_person(person)
            person_id += 1

        offset += batch_size

    return graph


@router.get("/prosopography/export", tags=["Prosopography"])
@limiter.limit("5/minute")
async def export_prosopography(
    request: Request,
    fmt: Annotated[
        str,
        Query(description="Export format: json, graphml, csv, neo4j"),
    ] = "json",
    session: AsyncSession = Depends(get_session),
):
    """Export the entire prosopographical FamilyGraph."""
    from fastapi.responses import Response

    repo = InscriptionRepository(session)
    graph = await _get_family_graph(repo)

    try:
        content = graph.export(fmt=fmt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    media_types = {
        "json": "application/json",
        "csv": "text/csv",
        "graphml": "application/xml",
        "neo4j": "text/plain",
    }

    return Response(content=content, media_type=media_types.get(fmt, "text/plain"))


@router.get("/prosopography/persons/search", tags=["Prosopography"])
@limiter.limit("30/minute")
async def search_prosopography_persons(
    request: Request,
    gens: str | None = None,
    praenomen: str | None = None,
    gender: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Search for specific named persons in the prosopographical network."""
    repo = InscriptionRepository(session)
    graph = await _get_family_graph(repo)

    persons = graph.search_persons(gens=gens, praenomen=praenomen, gender=gender)

    # Manually serialize persons since the method returns Person objects directly
    return [
        {
            "id": p.id,
            "name": p.name_formula.canonical,
            "gender": p.gender,
            "praenomen": p.praenomen,
            "gentilicium": p.gentilicium,
            "patronymic": p.name_formula.patronymic(),
            "findspots": p.findspots,
            "inscription_ids": p.inscription_ids,
        }
        for p in persons
    ]


@router.get("/prosopography/clans/{gens}/related", tags=["Prosopography"])
@limiter.limit("30/minute")
async def related_clans(request: Request, gens: str, session: AsyncSession = Depends(get_session)):
    """Find clans strictly related to the target clan via co-occurrence."""
    repo = InscriptionRepository(session)
    graph = await _get_family_graph(repo)

    related = graph.related_clans(gens)
    return {"clan": gens, "related_clans": related}
