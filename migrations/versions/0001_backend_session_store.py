"""backend session store: tenants, sessions, turns, audit_events, retrieval_events

Revision ID: 0001
Revises:
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SESSIONSTATE_VALUES = (
    "CREATED",
    "CONNECTING",
    "NOTICE_PENDING",
    "LISTENING",
    "ENDPOINT_PENDING",
    "TRANSCRIBING_FINAL",
    "ROUTING",
    "RETRIEVING",
    "GENERATING",
    "SPEAKING",
    "INTERRUPTED",
    "DEGRADED",
    "CHAT_HANDOFF",
    "HUMAN_HANDOFF",
    "CLOSED",
)


def upgrade() -> None:
    quoted = ", ".join(f"'{value}'" for value in SESSIONSTATE_VALUES)
    op.execute(sa.text(f"CREATE TYPE sessionstate AS ENUM ({quoted})"))

    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings_revision", sa.String(), nullable=True),
    )
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*SESSIONSTATE_VALUES, name="sessionstate", create_type=False),
            nullable=True,
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_tenant_id", "sessions", ["tenant_id"])
    op.create_table(
        "turns",
        sa.Column("turn_id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.session_id"), nullable=False),
        sa.Column("sequence_no", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redacted_text", sa.String(), nullable=True),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("confidence", sa.String(), nullable=True),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_table(
        "retrieval_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("turn_id", sa.String(), sa.ForeignKey("turns.turn_id"), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("index_revision", sa.String(), nullable=True),
        sa.Column("retrieval_mode", sa.String(), nullable=True),
        sa.Column("config_version", sa.String(), nullable=True),
        sa.Column("evidence_status", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("query_sha256", sa.String(), nullable=False),
        sa.Column("query_chars", sa.Integer(), nullable=False),
        sa.Column("applied_filters", sa.JSON(), nullable=True),
        sa.Column("candidates", sa.JSON(), nullable=True),
        sa.Column("selected_source_ids", sa.JSON(), nullable=True),
        sa.Column("cited_source_ids", sa.JSON(), nullable=True),
        sa.Column("conflict_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("excluded_counts", sa.JSON(), nullable=True),
        sa.Column("degraded", sa.JSON(), nullable=True),
        sa.Column("top_score", sa.Float(), nullable=True),
        sa.Column("outdated_matches", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_retrieval_events_turn_id", "retrieval_events", ["turn_id"])
    op.create_index("ix_retrieval_events_tenant_id", "retrieval_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_events_tenant_id", table_name="retrieval_events")
    op.drop_index("ix_retrieval_events_turn_id", table_name="retrieval_events")
    op.drop_table("retrieval_events")
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_turns_session_id", table_name="turns")
    op.drop_table("turns")
    op.drop_index("ix_sessions_tenant_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("tenants")
    op.execute(sa.text("DROP TYPE sessionstate"))
