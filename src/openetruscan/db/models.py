from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Inscription(Base):
    __tablename__ = "inscriptions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    phonetic: Mapped[str] = mapped_column(Text, nullable=False)
    old_italic: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    findspot: Mapped[Optional[str]] = mapped_column(Text, default="", index=True)
    findspot_lat: Mapped[Optional[float]] = mapped_column(Float)
    findspot_lon: Mapped[Optional[float]] = mapped_column(Float)
    findspot_uncertainty_m: Mapped[Optional[float]] = mapped_column(Float)
    date_approx: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    date_uncertainty: Mapped[Optional[int]] = mapped_column(Integer)
    medium: Mapped[Optional[str]] = mapped_column(Text, default="")
    object_type: Mapped[Optional[str]] = mapped_column(Text, default="")
    source: Mapped[Optional[str]] = mapped_column(Text, default="")
    bibliography: Mapped[Optional[str]] = mapped_column(Text, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(Text, nullable=False, default="etruscan", index=True)
    classification: Mapped[str] = mapped_column(Text, nullable=False, default="unknown", index=True)
    script_system: Mapped[str] = mapped_column(Text, nullable=False, default="old_italic")
    completeness: Mapped[str] = mapped_column(Text, nullable=False, default="complete")
    provenance_status: Mapped[str] = mapped_column(Text, nullable=False, default="verified", index=True)
    provenance_flags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trismegistos_id: Mapped[Optional[str]] = mapped_column(Text)
    eagle_id: Mapped[Optional[str]] = mapped_column(Text)
    pleiades_id: Mapped[Optional[str]] = mapped_column(Text)
    geonames_id: Mapped[Optional[str]] = mapped_column(Text)
    is_codex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # We omit the raw PostGIS/pgvector and TSVector computed columns from simple modeling
    # to let Alembic handle them cleanly as distinct operations, or manage them manually.
    
    entities: Mapped[list["Entity"]] = relationship(back_populates="inscription", cascade="all, delete-orphan")


class GeneticSample(Base):
    __tablename__ = "genetic_samples"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    findspot: Mapped[Optional[str]] = mapped_column(Text, default="")
    findspot_lat: Mapped[Optional[float]] = mapped_column(Float)
    findspot_lon: Mapped[Optional[float]] = mapped_column(Float)
    findspot_uncertainty_m: Mapped[Optional[float]] = mapped_column(Float)
    date_approx: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    date_uncertainty: Mapped[Optional[int]] = mapped_column(Integer)
    y_haplogroup: Mapped[Optional[str]] = mapped_column(Text)
    mt_haplogroup: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(Text, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Clan(Base):
    __tablename__ = "clans"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    relationships: Mapped[list["Relationship"]] = relationship(back_populates="clan", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    inscription_id: Mapped[Optional[str]] = mapped_column(ForeignKey("inscriptions.id", ondelete="CASCADE"), index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inscription: Mapped[Optional["Inscription"]] = relationship(back_populates="entities")


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[str]] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    related_person_id: Mapped[Optional[str]] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    clan_id: Mapped[Optional[str]] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    person: Mapped[Optional["Entity"]] = relationship(foreign_keys=[person_id])
    related_person: Mapped[Optional["Entity"]] = relationship(foreign_keys=[related_person_id])
    clan: Mapped[Optional["Clan"]] = relationship(back_populates="relationships")

    __table_args__ = (
        CheckConstraint(
            "(related_person_id IS NOT NULL AND clan_id IS NULL) OR "
            "(clan_id IS NOT NULL AND related_person_id IS NULL)",
            name="check_relationship_target"
        ),
    )
