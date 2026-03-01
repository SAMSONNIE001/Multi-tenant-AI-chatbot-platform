from types import SimpleNamespace

from app.auth.models import User
from app.chat.router import ask
from app.chat.schemas import AskRequest
from app.governance.policy_engine import PolicyResult


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarRows(self._rows)


class _FakeDB:
    def __init__(self, document_rows):
        self.document_rows = document_rows
        self.last_stmt = None

    def execute(self, stmt):
        self.last_stmt = stmt
        return _ExecResult(self.document_rows)


def test_ask_refuses_on_document_lookup_mismatch_and_filters_by_tenant(monkeypatch):
    chunks = [
        SimpleNamespace(id="c1", document_id="d1", chunk_index=0, text="one"),
        SimpleNamespace(id="c2", document_id="d2", chunk_index=1, text="two"),
    ]
    current_user = User(
        id="u1",
        tenant_id="t1",
        email="admin@acme.com",
        password_hash="x",
        role="admin",
    )
    current_user.tenant_name = "Acme"
    db = _FakeDB(
        # Deliberately return fewer docs than doc_ids to trigger mismatch guard.
        [SimpleNamespace(id="d1", tenant_id="t1", visibility="public", tags=[])]
    )
    audit_calls = []

    monkeypatch.setattr("app.chat.router.search_chunks", lambda **_: chunks)
    # Isolate this unit test from DB-backed conversation/quota machinery.
    monkeypatch.setattr(
        "app.chat.router.get_or_create_conversation",
        lambda *_args, **_kwargs: SimpleNamespace(id="conv_test"),
    )
    monkeypatch.setattr("app.chat.router.fetch_recent_messages", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.chat.router.append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.chat.router.touch_conversation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.chat.router.check_rate_limit", lambda **_: (True, None))
    monkeypatch.setattr("app.chat.router.check_tenant_quota", lambda **_: (True, None, {}))
    monkeypatch.setattr("app.chat.router.write_usage_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.chat.router.evaluate_question_policy",
        lambda *_args, **_kwargs: PolicyResult(action="allow"),
    )
    monkeypatch.setattr(
        "app.chat.router.write_chat_audit_log",
        lambda *args, **kwargs: audit_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "app.chat.router.generate_answer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )

    response = ask(
        AskRequest(question="what is policy", top_k=5),
        db=db,
        current_user=current_user,
    )

    assert response.answer == "Request refused due to document access inconsistency."
    assert response.coverage.doc_count == 2
    assert response.coverage.chunk_count == 2
    assert response.citations == []
    assert len(audit_calls) == 1
    assert audit_calls[0][1]["refused"] is True

    # Ensure tenant constraint is present in the query (defense-in-depth).
    assert "documents.tenant_id" in str(db.last_stmt)
