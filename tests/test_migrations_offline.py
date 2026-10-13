from alembic import command
from alembic.config import Config


def test_offline_sql_has_session_tables_not_knowledge(monkeypatch, capsys):
    monkeypatch.setenv("SYNC_DATABASE_URL", "postgresql://user:pass@localhost/voice_agent")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head", sql=True)
    sql = capsys.readouterr().out.lower()
    for table in ("tenants", "sessions", "turns", "audit_events", "retrieval_events"):
        assert f"create table {table}" in sql or f'create table "{table}"' in sql
    assert "sessionstate" in sql
    assert "knowledge_" not in sql
