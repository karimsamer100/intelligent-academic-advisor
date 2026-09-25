from __future__ import annotations

import pytest

import app.db.session as db_session


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


def test_session_scope_commits_and_closes(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: lambda: session)

    with db_session.session_scope() as yielded:
        assert yielded is session

    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.closes == 1


def test_session_scope_rolls_back_closes_and_reraises(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: lambda: session)

    with pytest.raises(RuntimeError, match="boom"):
        with db_session.session_scope():
            raise RuntimeError("boom")

    assert session.commits == 0
    assert session.rollbacks == 1
    assert session.closes == 1
