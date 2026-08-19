import main


def test_sanitize_chat_history_caps_to_last_five_and_drops_invalid_entries():
    history = [
        main.ChatMessage(role="user", content=f"msg {i}") for i in range(7)
    ] + [
        main.ChatMessage(role="system", content="should be dropped"),
        main.ChatMessage(role="user", content="   "),
    ]

    result = main.sanitize_chat_history(history)

    assert len(result) == 5
    assert result[0] == {"role": "user", "content": "msg 2"}
    assert result[-1] == {"role": "user", "content": "msg 6"}


def test_sanitize_chat_history_handles_none_and_empty():
    assert main.sanitize_chat_history(None) == []
    assert main.sanitize_chat_history([]) == []


def test_chat_passes_history_through_to_ai_fallback(client, monkeypatch):
    monkeypatch.setattr(main, "ISA_PATTERN", main.re.compile(r"$^"))
    monkeypatch.setattr(main, "PO_PATTERN", main.re.compile(r"$^"))
    monkeypatch.setattr(main, "get_user_permissions", lambda _oid: [])
    monkeypatch.setattr(main, "handle_local_model_fallback", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_feedback_context", lambda: "")
    monkeypatch.setattr(main, "_anthropic_client", object())

    captured = {}

    def fake_ai_fallback(question, tools, dispatch, feedback_context="", history=None):
        captured["history"] = history
        return {"intent": "ai_unhandled", "reply": "ok", "matches": [], "source": "ai"}

    monkeypatch.setattr(main, "handle_ai_fallback", fake_ai_fallback)

    response = client.post(
        "/api/chat",
        json={
            "question": "yes",
            "history": [
                {"role": "assistant", "content": "Want a download link for that file?"},
            ],
        },
    )

    assert response.status_code == 200
    assert captured["history"] == [{"role": "assistant", "content": "Want a download link for that file?"}]
