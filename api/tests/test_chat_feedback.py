import main


def test_submit_feedback_inserts_row(client, monkeypatch):
    captured = {}

    class FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            captured["committed"] = True

    monkeypatch.setattr(main, "get_conn", lambda: FakeConn())

    response = client.post(
        "/api/chat/feedback",
        json={
            "question": "Where is PO ORDER1001?",
            "reply": "PO ORDER1001 is ready.",
            "source": "regex",
            "channel": "support",
            "rating": -1,
            "comment": "Wrong order number in the reply.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert captured["committed"] is True
    assert "INSERT INTO dbo.ChatFeedback" in captured["sql"]
    user_oid, message_hash, channel, source, question, reply, rating, comment = captured["params"]
    assert user_oid == "test-user"
    assert len(message_hash) == 64
    assert channel == "support"
    assert source == "regex"
    assert question == "Where is PO ORDER1001?"
    assert reply == "PO ORDER1001 is ready."
    assert rating == -1
    assert comment == "Wrong order number in the reply."


def test_submit_feedback_defaults_unknown_channel_to_support(client, monkeypatch):
    captured = {}

    class FakeCursor:
        def execute(self, sql, params):
            captured["params"] = params

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    monkeypatch.setattr(main, "get_conn", lambda: FakeConn())

    response = client.post(
        "/api/chat/feedback",
        json={
            "question": "q",
            "reply": "r",
            "channel": "not-a-real-channel",
            "rating": 1,
        },
    )

    assert response.status_code == 200
    assert captured["params"][2] == "support"


def test_submit_feedback_rejects_invalid_rating(client):
    response = client.post(
        "/api/chat/feedback",
        json={"question": "q", "reply": "r", "rating": 0},
    )

    assert response.status_code == 400


def test_submit_feedback_rejects_comment_over_max_length(client):
    response = client.post(
        "/api/chat/feedback",
        json={"question": "q", "reply": "r", "rating": 1, "comment": "x" * 1001},
    )

    assert response.status_code == 400


def test_submit_feedback_rejects_missing_question_or_reply(client):
    response = client.post(
        "/api/chat/feedback",
        json={"question": "  ", "reply": "r", "rating": 1},
    )

    assert response.status_code == 400


def test_chat_uses_recent_negative_feedback_as_ai_context(client, monkeypatch):
    monkeypatch.setattr(main, "ISA_PATTERN", main.re.compile(r"$^"))
    monkeypatch.setattr(main, "PO_PATTERN", main.re.compile(r"$^"))
    monkeypatch.setattr(main, "get_user_permissions", lambda _oid: [])
    monkeypatch.setattr(main, "handle_local_model_fallback", lambda *a, **k: None)
    monkeypatch.setattr(
        main,
        "get_recent_negative_feedback",
        lambda limit=main.CHAT_FEEDBACK_CONTEXT_LIMIT: [
            {"QuestionText": "old q", "ResponseText": "old r", "Comment": "too vague"}
        ],
    )

    captured_system = {}

    def fake_ai_fallback(question, tools, dispatch, feedback_context=""):
        captured_system["context"] = feedback_context
        return {"intent": "ai_unhandled", "reply": "ok", "matches": [], "source": "ai"}

    monkeypatch.setattr(main, "handle_ai_fallback", fake_ai_fallback)
    monkeypatch.setattr(main, "_anthropic_client", object())

    response = client.post("/api/chat", json={"question": "something unrelated"})

    assert response.status_code == 200
    assert "too vague" in captured_system["context"]
