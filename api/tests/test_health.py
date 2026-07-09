def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "EDI WMS API running"}


def test_debug_logic_url_reports_when_set(client, monkeypatch):
    monkeypatch.setenv("LOGIC_APP_TRIGGER_URL", "https://example.com/trigger")

    response = client.get("/api/debug/logic-url")

    assert response.json() == {"url_set": True}


def test_debug_logic_url_reports_when_unset(client, monkeypatch):
    monkeypatch.delenv("LOGIC_APP_TRIGGER_URL", raising=False)

    response = client.get("/api/debug/logic-url")

    assert response.json() == {"url_set": False}
