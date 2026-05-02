"""
SQLAlchemy 2.0 ORM models for the OpenEtruscan epigraphic corpus.

Defines the relational schema: inscriptions, genetic samples, entities,
clans, and prosopographical relationships.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """
    Declarative base for all OpenEtruscan SQLAlchemy models.
    Uses SQLAlchemy 2.0 style mapping.
    """

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class DataSource(Base):
    """A bibliographic / dataset source for inscriptions.

    Each row in ``inscriptions`` may point at one DataSource via ``source_id``.
    The DataSource carries the canonical citation, license, and a *provenance
    baseline* (the tier most rows from this source typically fall into).
    See migration ``c3f4d5e6a7b8_data_sources_table`` for the rationale.
    """

    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    url: Mapped[str | None] = mapped_column(Text)
    provenance_baseline: Mapped[str] = mapped_column(
        Text, nullable=False, default="unknown"
    )
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Inscription(Base):
    """
    Represents a single epigraphic record in the corpus.
    Stores raw text, canonicalized phonological text, and spatial metadata.
    """

    __tablename__ = "inscriptions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    phonetic: Mapped[str] = mapped_column(Text, nullable=False)
    old_italic: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    findspot: Mapped[str | None] = mapped_column(Text, default="", index=True)
    findspot_lat: Mapped[float | None] = mapped_column(Float)
    findspot_lon: Mapped[float | None] = mapped_column(Float)
    findspot_uncertainty_m: Mapped[float | None] = mapped_column(Float)
    date_approx: Mapped[int | None] = mapped_column(Integer, index=True)
    date_uncertainty: Mapped[int | None] = mapped_column(Integer)
    medium: Mapped[str | None] = mapped_column(Text, default="")
    object_type: Mapped[str | None] = mapped_column(Text, default="")
    source: Mapped[str | None] = mapped_column(Text, default="")
    bibliography: Mapped[str | None] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(Text, nullable=False, default="etruscan", index=True)
    classification: Mapped[str] = mapped_column(Text, nullable=False, default="unknown", index=True)
    script_system: Mapped[str] = mapped_column(Text, nullable=False, default="old_italic")
    completeness: Mapped[str] = mapped_column(Text, nullable=False, default="complete")
    provenance_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="verified", index=True
    )
    provenance_flags: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # SOTA Epigraphic Provenance
    source_code: Mapped[str] = mapped_column(Text, nullable=False, default="unknown", index=True)
    source_detail: Mapped[str | None] = mapped_column(Text)
    original_script_entry: Mapped[str | None] = mapped_column(Text)

    # Optional FK into data_sources. Nullable for legacy rows that pre-date the
    # data_sources table. The textual `source` column above is kept for
    # backwards compatibility and as a denormalised display string.
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"), index=True
    )

    trismegistos_id: Mapped[str | None] = mapped_column(Text)
    eagle_id: Mapped[str | None] = mapped_column(Text)
    pleiades_id: Mapped[str | None] = mapped_column(Text)
    geonames_id: Mapped[str | None] = mapped_column(Text)
    is_codex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # We omit the raw PostGIS/pgvector and TSVector computed columns from simple modeling
    # to let Alembic handle them cleanly as distinct operations, or manage them manually.

    entities: Mapped[list["Entity"]] = relationship(
        back_populates="inscription", cascade="all, delete-orphan"
    )


class GeneticSample(Base):
    """
    Represents a biological sample from an archaeological context.
    Linked to inscriptions via geographic proximity (PostGIS).
    """

    __tablename__ = "genetic_samples"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    findspot: Mapped[str | None] = mapped_column(Text, default="")
    findspot_lat: Mapped[float | None] = mapped_column(Float)
    findspot_lon: Mapped[float | None] = mapped_column(Float)
    findspot_uncertainty_m: Mapped[float | None] = mapped_column(Float)
    date_approx: Mapped[int | None] = mapped_column(Integer, index=True)
    date_uncertainty: Mapped[int | None] = mapped_column(Integer)
    y_haplogroup: Mapped[str | None] = mapped_column(Text)
    mt_haplogroup: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Clan(Base):
    """
    Represents an Etruscan gentilicial group (gens).
    Used for prosopographical network analysis.
    """

    __tablename__ = "clans"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    relationships: Mapped[list["Relationship"]] = relationship(
        back_populates="clan", cascade="all, delete-orphan"
    )


class Entity(Base):
    """
    Represents a named individual or social actor extracted from an inscription.
    """

    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    inscription_id: Mapped[str | None] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, default="")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    inscription: Mapped[Optional["Inscription"]] = relationship(back_populates="entities")


class Relationship(Base):
    """
    Represents a prosopographical link between two entities or an entity and a clan.
    Models familial ties (clan, puia, sec) and social hierarchies.
    """

    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    related_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    clan_id: Mapped[str | None] = mapped_column(
        ForeignKey("clans.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    person: Mapped[Optional["Entity"]] = relationship(foreign_keys=[person_id])
    related_person: Mapped[Optional["Entity"]] = relationship(foreign_keys=[related_person_id])
    clan: Mapped[Optional["Clan"]] = relationship(back_populates="relationships")

    __table_args__ = (
        CheckConstraint(
            "(related_person_id IS NOT NULL AND clan_id IS NULL) OR "
            "(clan_id IS NOT NULL AND related_person_id IS NULL)",
            name="check_relationship_target",
        ),
    )


class ProvenanceAudit(Base):
    """
    Audit log for curatorial changes to an inscription's provenance status.
    """
    __tablename__ = "provenance_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inscription_id: Mapped[str] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    old_status: Mapped[str] = mapped_column(Text, nullable=False)
    new_status: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    inscription: Mapped[Optional["Inscription"]] = relationship()
