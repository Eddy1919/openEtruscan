"""
SQLAlchemy 2.0 ORM models for the OpenEtruscan epigraphic corpus.

Defines the relational schema: inscriptions, genetic samples, entities,
clans, and prosopographical relationships.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
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
    provenance_baseline: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
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

    # NLP & Clean Data Columns
    canonical_clean: Mapped[str | None] = mapped_column(Text)
    old_italic_v2: Mapped[str | None] = mapped_column(Text)
    data_quality: Mapped[str | None] = mapped_column(Text)
    translation: Mapped[str | None] = mapped_column(Text)
    canonical_words_only: Mapped[str | None] = mapped_column(Text)
    year_from: Mapped[int | None] = mapped_column(Integer)
    year_to: Mapped[int | None] = mapped_column(Integer)
    intact_token_ratio: Mapped[float | None] = mapped_column(Float)
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
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    provenance_flags: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Epigraphic Provenance
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
    zotero_id: Mapped[str | None] = mapped_column(Text)
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

    The archaeogenetics *runtime* (the ``/genetics/*`` endpoints, the
    ``Corpus.add_genetic_sample`` writer, and the ingest script) was retired
    in the 2.0 surface cleanup. This ORM model is retained deliberately: the
    ``genetic_samples`` table still exists in every migrated database and is
    still read by the deprecation-fenced ``core.spatial``/``core.lineage``
    modules AND by ``core.kinship`` (NOT deprecation-fenced, covered by
    tests/test_kinship.py) — removing spatial/lineage at 2.0 does not make
    this table unused. Deleting this class would make ``alembic revision --autogenerate``
    propose a ``DROP TABLE genetic_samples`` against live databases. Do not
    remove it without an explicit, reviewed migration that drops the table.
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
    biological_sex: Mapped[str | None] = mapped_column(Text)
    c14_date_range: Mapped[str | None] = mapped_column(Text)
    tomb_id: Mapped[str | None] = mapped_column(Text, index=True)
    context_detail: Mapped[str | None] = mapped_column(Text)
    ancestry_components: Mapped[str | None] = mapped_column(Text)
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


class ProposedAnchor(Base):
    """Community-submitted candidate Etruscan↔Latin/Greek gloss equivalence.

    Sits in a moderation queue until an admin marks `status` as
    `approved` (row gets appended to `research/anchors/attested.jsonl`
    via a separate data-refresh pipeline), `rejected`, or `duplicate`.

    See the maintainer-held community-curation design note for the workflow.
    """

    __tablename__ = "proposed_anchors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    etruscan_word: Mapped[str] = mapped_column(Text, nullable=False)
    equivalent: Mapped[str] = mapped_column(Text, nullable=False)
    equivalent_language: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    submitter_email: Mapped[str] = mapped_column(Text, nullable=False)
    submitter_orcid: Mapped[str | None] = mapped_column(Text)
    # Optional corpus ID of the inscription the submitter was reading
    # when they filed the proposal. Threaded in by the frontend's
    # `?from=` search param on /propose/<word>. NOT a FK — see the
    # migration docstring for the loose-coupling rationale.
    source_inscription_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    reviewer: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "equivalent_language IN ('lat', 'grc')",
            name="ck_proposed_anchors_equivalent_language",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'duplicate')",
            name="ck_proposed_anchors_status",
        ),
        # `length()` (not `char_length()`) so the constraint emits on both
        # Postgres and SQLite — the test fallback uses SQLite, which has no
        # `char_length`. For text values both functions are equivalent.
        CheckConstraint(
            "length(evidence_quote) >= 10",
            name="ck_proposed_anchors_evidence_quote_min_length",
        ),
        CheckConstraint(
            "length(source) >= 3",
            name="ck_proposed_anchors_source_min_length",
        ),
        # Empty string would be confusing semantics for "I had no inscription
        # context" — force NULL in that case. Upper bound is a paste-bomb guard.
        CheckConstraint(
            "source_inscription_id IS NULL OR (length(source_inscription_id) BETWEEN 1 AND 64)",
            name="ck_proposed_anchors_source_inscription_id_shape",
        ),
        Index("ix_proposed_anchors_status_created", "status", "created_at"),
        Index("ix_proposed_anchors_etr_word", "etruscan_word"),
    )


# ---------------------------------------------------------------------------
# Edition layer (migration j5f6a7b8c9d0)
# ---------------------------------------------------------------------------

# BIGINT on Postgres; INTEGER on SQLite, where only "INTEGER PRIMARY KEY"
# autoincrements (the test fallback and the local pipeline DB are SQLite).
_BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")


class InscriptionAlias(Base):
    """A standard reference (CIE, ET, TLE, TM, …) that resolves to a record.

    Record IDs never change: the sitemap publishes them. Aliases let a
    scholar reach a record by the reference they cite. One reference may
    resolve to several records (Burman's "Multiple references?" cases, or
    a CIE number shared by the parts of one monument), so ``lookup_key``
    is indexed, not unique. ``basis`` says how the alias was derived:
    ``own_id`` (the record ID is this reference), ``concordance`` (Burman's
    concordance, reached through the record ID) or ``ciep_cie_numbering``
    (a bare CIEP number read as the CIE number; probable, not checked
    record by record). See ``openetruscan.core.concordance``.
    """

    __tablename__ = "inscription_aliases"

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    inscription_id: Mapped[str] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheme: Mapped[str] = mapped_column(Text, nullable=False)
    lookup_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "basis IN ('own_id', 'concordance', 'ciep_cie_numbering', 'manual')",
            name="basis",
        ),
        CheckConstraint(
            "confidence IN ('certain', 'high', 'probable', 'uncertain')",
            name="confidence",
        ),
        Index("uq_inscription_aliases_record_key", "inscription_id", "lookup_key", unique=True),
    )


class InscriptionEdition(Base):
    """Per-record edition metadata that does not belong on ``inscriptions``.

    * ``rix_*`` — the record's ET siglum and the text class it encodes
      (``1`` funerary, ``2`` ownership, …; see ``reference/rix_text_classes.csv``).
      Kept apart from ``classification`` on purpose: the two schemes
      disagree on some texts and the frozen evaluation splits depend on
      ``classification``.
    * ``findspot_*`` — the place the findspot string (or, failing that,
      the ET region code) resolves to, with its precision. The place is an
      attribution, not a find position: the backfill never copies its
      Pleiades point into ``inscriptions.findspot_lat``/``lon``.
    * ``current_location`` — where the object is kept, split out of the
      findspot string. ``findspot_source_text`` keeps the original string
      when the backfill clears a custody-only findspot.
    * ``editor`` / ``autopsy`` — who established the current reading and
      whether they saw the object (NULL = not recorded).
    """

    __tablename__ = "inscription_edition"

    inscription_id: Mapped[str] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    rix_siglum: Mapped[str | None] = mapped_column(Text)
    rix_text_class: Mapped[str | None] = mapped_column(Text, index=True)
    rix_class_basis: Mapped[str | None] = mapped_column(Text)
    findspot_place: Mapped[str | None] = mapped_column(Text)
    findspot_precision: Mapped[str | None] = mapped_column(Text)
    findspot_basis: Mapped[str | None] = mapped_column(Text)
    findspot_source_text: Mapped[str | None] = mapped_column(Text)
    current_location: Mapped[str | None] = mapped_column(Text)
    editor: Mapped[str | None] = mapped_column(Text)
    autopsy: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "findspot_precision IS NULL OR findspot_precision IN "
            "('site', 'city', 'territory', 'region')",
            name="findspot_precision",
        ),
        CheckConstraint(
            "rix_text_class IS NULL OR rix_text_class IN "
            "('0','1','2','3','4','5','6','7','8','9','S','G','N')",
            name="rix_text_class",
        ),
    )


class InscriptionReading(Base):
    """One reading of a text in one edition: the reading history.

    The backfill seeds one row per record from the text we currently show
    (``is_current``), attributed to the edition it came from. Earlier and
    competing readings are added as curators enter them.
    """

    __tablename__ = "inscription_readings"

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    inscription_id: Mapped[str] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reading: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str] = mapped_column(Text, nullable=False)
    editor: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    autopsy: Mapped[bool | None] = mapped_column(Boolean)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InscriptionImage(Base):
    """A photograph, drawing or IIIF resource for a record.

    ``license`` and ``source_citation`` are required: an image without
    known rights is not published.
    """

    __tablename__ = "inscription_images"

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    inscription_id: Mapped[str] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    iiif_manifest: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text, nullable=False)
    rights_holder: Mapped[str | None] = mapped_column(Text)
    source_citation: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('photo', 'drawing', 'squeeze', 'facsimile', 'iiif')", name="kind"
        ),
        CheckConstraint("url IS NOT NULL OR iiif_manifest IS NOT NULL", name="has_target"),
    )


class IndexedDocument(Base):
    """A known inscription the corpus does not hold, indexed by reference.

    Seeded from Burman's concordance rows that match no record; later
    rows can come from REE (Studi Etruschi), ET², or newer CIE fascicles,
    which are under copyright: only the siglum, findspot, date and
    reference are stored, never the text.
    """

    __tablename__ = "indexed_documents"

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    primary_ref: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    refs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trismegistos_id: Mapped[str | None] = mapped_column(Text, index=True)
    rix_siglum: Mapped[str | None] = mapped_column(Text)
    rix_text_class: Mapped[str | None] = mapped_column(Text)
    region_code: Mapped[str | None] = mapped_column(Text, index=True)
    findspot_place: Mapped[str | None] = mapped_column(Text)
    pleiades_id: Mapped[str | None] = mapped_column(Text)
    date_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_row: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LexiconGloss(Base):
    """A proposed meaning for an Etruscan form, with its confidence and source.

    Loaded from ``research/anchors/gold_glosses/gold_glosses.jsonl``.
    ``status`` is that file's adjudication status; nothing below
    ``verified`` should be presented as settled.
    """

    __tablename__ = "lexicon_glosses"

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    form: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    headword: Mapped[str] = mapped_column(Text, nullable=False)
    gloss_en: Mapped[str] = mapped_column(Text, nullable=False)
    latin: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(Text)
    citation_primary: Mapped[str | None] = mapped_column(Text)
    citation_modern: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class NameAttestation(Base):
    """One personal name in one inscription, for the Name Index.

    Built word by word by ``scripts/data_pipeline/build_name_index.py``
    (see ``openetruscan.core.onomastics``): praenomina from
    ``reference/praenomina.csv`` and the family name that follows each one.
    ``lemma`` groups the spellings and case forms of a praenomen (``larθal``
    under ``larθ``); for an abbreviation it is the abbreviation with a dot,
    and for a family name it is the form. ``basis`` and ``confidence`` say
    how the name was read: only ``praenomen_list`` rows are ``high``.
    The site's Name Index reads it through the frontend's own
    ``/api/names/network`` route (openEtruscan-frontend). This API's
    ``/names/network`` endpoint still reads ``relationships``, and
    ``entities`` still feeds the lineage tables.
    """

    __tablename__ = "name_attestations"

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    inscription_id: Mapped[str] = mapped_column(
        ForeignKey("inscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    form: Mapped[str] = mapped_column(Text, nullable=False)
    lemma: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name_type: Mapped[str] = mapped_column(Text, nullable=False)
    gender: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("name_type IN ('praenomen', 'gentilicium')", name="name_type"),
        CheckConstraint("gender IS NULL OR gender IN ('m', 'f')", name="gender"),
        CheckConstraint(
            "basis IN ('praenomen_list', 'praenomen_abbreviation', 'follows_praenomen')",
            name="basis",
        ),
        CheckConstraint("confidence IN ('high', 'probable')", name="confidence"),
        Index("uq_name_attestations_record_position", "inscription_id", "position", unique=True),
    )
