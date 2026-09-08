from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, SQLModel, create_engine


class CodebookRecord(SQLModel, table=True):
    __tablename__ = "codebooks"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    yaml_raw: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentRecord(SQLModel, table=True):
    __tablename__ = "documents"

    id: int | None = Field(default=None, primary_key=True)
    corpus_id: str
    text: str
    metadata_json: str = "{}"
    # The source's own native document id (e.g. QualiLab's "doc-1"), so a
    # later export can map an extraction back to the right document in a
    # re-uploaded source file. None for CSV/XLSX/paste-imported documents,
    # which have no such stable id to preserve. See
    # docs/superpowers/specs/2026-09-02-qualilab-interop-design.md finding #1.
    external_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HumanLabelRecord(SQLModel, table=True):
    """A human-coded gold label for one document, under one codebook.

    Deliberately allows multiple rows per (document_id, codebook_id): a
    QualiLab double-blind project produces one label per coder per
    document, and collapsing that to a single "ground truth" at import
    time would throw away real inter-rater information. The tradeoff this
    creates -- validation.py's agreement_report() assumes exactly one gold
    row per document -- is handled at the import boundary instead: the
    default, recommended import path (QualiLab's "final" / team-
    consolidated layer) is validated to contain at most one row per
    document before being written here, so the common case stays safe by
    construction. See the design spec's "Gold-standard reduction to one
    row per document" section for the full reasoning."""

    __tablename__ = "human_labels"

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id")
    codebook_id: int = Field(foreign_key="codebooks.id")
    category: str
    coder: str  # QualiLab author_name/set_by, or "manual" for hand-entered labels
    source: str = "manual"  # "qualilab_import" | "manual"
    # QualiLab's own "final" (team-consolidated) vs "individual" (one row
    # per rater) layer, preserved rather than dropped at import -- without
    # it there's no way to later distinguish a multi-coder gold set from a
    # single consolidated one once both are sitting in the same table.
    layer: str = "final"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    codebook_id: int = Field(foreign_key="codebooks.id")
    corpus_id: str
    model: str
    status: str = "pending"
    # What actually produced this run's extractions, persisted at creation
    # time rather than left implicit in CreateRunRequest (which is not
    # itself stored) -- disclosure.py needs to report this honestly after
    # the fact, and "trust today's app.py code path" is not a substitute
    # for a run recording its own provenance.
    provider_mode: str = "api_key"  # "api_key" | "cli"
    provider_detail: str = ""  # the model id (api_key mode) or CLI command (cli mode)
    # sha256 of the CodebookRecord.yaml_raw actually used by this run,
    # filled in by run_extraction once it loads the codebook. Caching in
    # extraction.py matches on this, not on codebook_id alone -- codebooks
    # are edited in place (PUT /codebooks/{id} keeps the same id), and
    # without a content hash a run against an edited codebook would
    # silently reuse cached extractions produced under the codebook's
    # *previous* definition instead of re-querying the LLM.
    codebook_yaml_hash: str = ""
    # When true, run_extraction never serves a cached extraction for this
    # run, even if one exists for the same (document, codebook_hash,
    # model) -- persisted here (not just a request-time parameter) because
    # run_extraction runs as a background task, decoupled from the
    # original HTTP request, and reads everything it needs off the
    # RunRecord itself. Exists for reproducibility verification: comparing
    # a run against a same-config repeat is meaningless if the "repeat"
    # just replays the first run's cached answers instead of asking the
    # LLM again.
    bypass_cache: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractionRecord(SQLModel, table=True):
    __tablename__ = "extractions"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id")
    document_id: int = Field(foreign_key="documents.id")
    categoria: str
    justificativa: str
    trecho_evidencia: str
    # Whether trecho_evidencia was found verbatim (or near-verbatim, modulo
    # quote/dash/whitespace normalization) in the source document -- see
    # extraction.py's verify_evidence_span(). Ported from QualiHolo (issue
    # #2): until this existed, a hallucinated or paraphrased quote passed
    # through unnoticed. Flagged for the researcher to see, not used to
    # invalidate categoria -- this repo's stance is that automated software
    # surfaces the signal, the researcher's judgment decides what to do
    # with it (see AGENTS.md's Product Vision).
    evidence_verified: bool = False
    # "exact" | "normalized" | "empty" | "too_short" | "not_found" | "" for
    # a pre-existing row migrated before this column existed.
    evidence_match_tier: str = ""
    tokens_used: int | None = None
    original_result_json: str = ""
    # Audit trail: the exact prompt sent and the raw (pre-parsing) response
    # received, so any result can be verified later without having to trust
    # a reconstruction from current source -- see ProviderResult in
    # providers.py. Empty string, not None, when a build_messages failure
    # happened before any prompt could be built.
    prompt_sent: str = ""
    raw_response: str = ""


# SQLModel/SQLAlchemy field type -> SQLite column type, for the additive
# migration below. Only a hint, not a constraint: SQLite has dynamic type
# affinity, so a column declared TEXT still stores an int fine and vice
# versa -- correctness doesn't depend on guessing right here. Anything not
# in this dict, or any SQLAlchemy type whose `.python_type` isn't
# implemented (raises NotImplementedError -- true for a few concrete types,
# not just a hypothetical), falls back to TEXT rather than failing the
# whole migration over a cosmetic type-affinity choice.
_SQLITE_TYPE_BY_PYTHON_TYPE = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
}


def _sqlite_column_type(column) -> str:
    try:
        return _SQLITE_TYPE_BY_PYTHON_TYPE.get(column.type.python_type, "TEXT")
    except NotImplementedError:
        return "TEXT"


def _ensure_columns(dbapi_connection) -> None:
    """Additively migrate a pre-existing SQLite file to match the current
    model definitions: for every SQLModel table, ADD COLUMN any field the
    model declares that the on-disk table doesn't have yet.

    `SQLModel.metadata.create_all()` only creates whole tables that don't
    exist -- it never alters an existing table's columns. Twice now
    (prompt_sent/raw_response on ExtractionRecord, provider_mode/
    provider_detail on RunRecord above) a field added to a model has left
    a live shared `decifra.sqlite` on disk with the old, narrower shape,
    and every query touching that table 500s until someone runs an
    `ALTER TABLE` by hand. This closes that gap generally instead of
    perpetuating it one manual fix at a time: new tables still come from
    `create_all` below, but any column drift on an existing table is
    reconciled automatically, every time the engine is built. Additive
    only (never drops or renames a column), so no data is at risk -- a
    stale extra column left over from an old model shape is simply
    ignored, not removed.
    """
    for table in SQLModel.metadata.tables.values():
        existing = {
            row[1]  # PRAGMA table_info(...) row shape: (cid, name, type, notnull, dflt_value, pk)
            for row in dbapi_connection.execute(f'PRAGMA table_info("{table.name}")').fetchall()
        }
        if not existing:
            continue  # table doesn't exist yet -- create_all() below handles it, nothing to migrate
        for column in table.columns:
            if column.name in existing:
                continue
            sqlite_type = _sqlite_column_type(column)
            default_sql = ""
            if column.default is not None and column.default.is_scalar:
                default_sql = f" DEFAULT {column.default.arg!r}" if isinstance(column.default.arg, str) else f" DEFAULT {column.default.arg}"
            dbapi_connection.execute(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {sqlite_type}{default_sql}')


def get_engine(db_url: str = "sqlite:///decifra.sqlite"):
    is_in_memory = db_url == "sqlite://" or ":memory:" in db_url
    kwargs = {"poolclass": StaticPool} if is_in_memory else {}
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        **kwargs,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        if not is_in_memory:
            # WAL lets readers and a writer proceed concurrently instead of
            # the default rollback-journal mode's whole-file lock -- with
            # multiple processes (this project's own dev sessions today)
            # sharing one decifra.sqlite, that default mode means a
            # background run_extraction write can make an unrelated read
            # fail with "database is locked". WAL needs a real file, so
            # this is skipped for in-memory test databases.
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

    SQLModel.metadata.create_all(engine)
    with engine.connect() as connection:
        _ensure_columns(connection.connection)
        connection.connection.commit()
    return engine
