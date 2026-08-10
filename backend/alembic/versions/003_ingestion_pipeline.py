"""Alembic migration — ingestion pipeline tables and column extensions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "003_ingestion_pipeline"
down_revision: Union[str, None] = "002_link_profiles_to_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ingestion_run_status = postgresql.ENUM(
    "running", "completed", "failed", "partial", name="ingestionrunstatus", create_type=False
)
rejected_stage = postgresql.ENUM(
    "discover", "prefilter", "extract", "dedupe", name="rejectedstage", create_type=False
)
source_type = postgresql.ENUM("rss", "html", "json", name="sourcetype", create_type=False)
opportunity_type = postgresql.ENUM(
    "scholarship",
    "fellowship",
    "internship",
    "graduate_program",
    "phd",
    "grant",
    "conference",
    "workshop",
    "competition",
    "other",
    name="opportunitytype",
    create_type=False,
)


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _column_names(inspector, table: str) -> set[str]:
    if not _has_table(inspector, table):
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column, inspector) -> None:
    if column.name not in _column_names(inspector, table):
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    ingestion_run_status.create(bind, checkfirst=True)
    rejected_stage.create(bind, checkfirst=True)
    source_type.create(bind, checkfirst=True)
    opportunity_type.create(bind, checkfirst=True)

    if not _has_table(inspector, "opportunity_sources"):
        op.create_table(
            "opportunity_sources",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("source_type", source_type, nullable=False),
            sa.Column("fetch_interval_minutes", sa.Integer(), server_default="360"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("parser_config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("registry_id", sa.String(length=64), nullable=True),
            sa.Column("adapter_id", sa.String(length=128), nullable=True),
            sa.Column("fetch_mode", sa.String(length=32), server_default="http"),
            sa.Column("summary_completeness", sa.String(length=32), server_default="snippet_only"),
            sa.Column("authority", sa.Float(), server_default="0.5"),
            sa.Column("politeness_delay_ms", sa.Integer(), server_default="2500"),
            sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("etag", sa.String(length=255), nullable=True),
            sa.Column("last_modified", sa.String(length=255), nullable=True),
            sa.Column("consecutive_failures", sa.Integer(), server_default="0"),
            sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_opportunity_sources_registry_id", "opportunity_sources", ["registry_id"])

    else:
        cols = [
            sa.Column("registry_id", sa.String(length=64), nullable=True),
            sa.Column("adapter_id", sa.String(length=128), nullable=True),
            sa.Column("fetch_mode", sa.String(length=32), server_default="http"),
            sa.Column("summary_completeness", sa.String(length=32), server_default="snippet_only"),
            sa.Column("authority", sa.Float(), server_default="0.5"),
            sa.Column("politeness_delay_ms", sa.Integer(), server_default="2500"),
            sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("etag", sa.String(length=255), nullable=True),
            sa.Column("last_modified", sa.String(length=255), nullable=True),
            sa.Column("consecutive_failures", sa.Integer(), server_default="0"),
        ]
        for col in cols:
            _add_column_if_missing("opportunity_sources", col, inspector)

    inspector = sa.inspect(bind)

    if not _has_table(inspector, "raw_documents"):
        op.create_table(
            "raw_documents",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("source_id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("url_hash", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("fetch_kind", sa.String(length=16), server_default="index"),
            sa.Column("parent_id", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("content_type", sa.String(length=128), nullable=True),
            sa.Column("raw_content", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("processed", sa.Boolean(), server_default=sa.text("false")),
            sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"]),
            sa.ForeignKeyConstraint(["parent_id"], ["raw_documents.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_raw_documents_url_hash", "raw_documents", ["url_hash"])
        op.create_index("ix_raw_documents_content_hash", "raw_documents", ["content_hash"])
    else:
        for col in [
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("fetch_kind", sa.String(length=16), server_default="index"),
            sa.Column("parent_id", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("content_type", sa.String(length=128), nullable=True),
        ]:
            _add_column_if_missing("raw_documents", col, inspector)

    inspector = sa.inspect(bind)

    if not _has_table(inspector, "opportunities"):
        op.create_table(
            "opportunities",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("institution", sa.String(length=255), nullable=True),
            sa.Column("program", sa.String(length=255), nullable=True),
            sa.Column("opportunity_type", opportunity_type, server_default="other"),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("canonical_url", sa.Text(), nullable=True),
            sa.Column("url_hash", sa.String(length=64), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("funding_type", sa.String(length=64), nullable=True),
            sa.Column("degree_levels", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("countries", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("extraction_confidence", sa.String(length=16), nullable=True),
            sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("field_changes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("duplicate_of", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("embedding", Vector(1536), nullable=True),
            sa.Column("source_id", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("raw_document_id", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("search_vector", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"]),
            sa.ForeignKeyConstraint(["raw_document_id"], ["raw_documents.id"]),
            sa.ForeignKeyConstraint(["duplicate_of"], ["opportunities.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("url_hash"),
        )
    else:
        for col in [
            sa.Column("canonical_url", sa.Text(), nullable=True),
            sa.Column("content_hash", sa.String(length=64), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("funding_type", sa.String(length=64), nullable=True),
            sa.Column("degree_levels", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("countries", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("extraction_confidence", sa.String(length=16), nullable=True),
            sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("field_changes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("duplicate_of", sa.UUID(as_uuid=False), nullable=True),
        ]:
            _add_column_if_missing("opportunities", col, inspector)

    if not _has_table(inspector, "ingestion_runs"):
        op.create_table(
            "ingestion_runs",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("source_id", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("status", ingestion_run_status, nullable=False, server_default="running"),
            sa.Column("discovered", sa.Integer(), server_default="0"),
            sa.Column("prefilter_drop", sa.Integer(), server_default="0"),
            sa.Column("fetched", sa.Integer(), server_default="0"),
            sa.Column("created", sa.Integer(), server_default="0"),
            sa.Column("updated", sa.Integer(), server_default="0"),
            sa.Column("rejected", sa.Integer(), server_default="0"),
            sa.Column("errors", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ingestion_runs_source_id", "ingestion_runs", ["source_id"])

    if not _has_table(inspector, "rejected_items"):
        op.create_table(
            "rejected_items",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("run_id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("source_id", sa.UUID(as_uuid=False), nullable=True),
            sa.Column("stage", rejected_stage, nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=False),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("snippet", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"]),
            sa.ForeignKeyConstraint(["source_id"], ["opportunity_sources.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_rejected_items_run_id", "rejected_items", ["run_id"])
        op.create_index("ix_rejected_items_source_id", "rejected_items", ["source_id"])

    if not _has_table(inspector, "platform_settings"):
        op.create_table(
            "platform_settings",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("rejected_items", "ingestion_runs", "platform_settings"):
        if _has_table(inspector, table):
            op.drop_table(table)
