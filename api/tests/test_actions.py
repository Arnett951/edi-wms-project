import main


def test_trigger_edi_rejects_missing_key(client):
    response = client.post("/api/actions/trigger-edi")

    assert response.status_code == 401


def test_trigger_edi_rejects_wrong_key(client):
    response = client.post("/api/actions/trigger-edi", headers={"x-api-key": "wrong"})

    assert response.status_code == 401


def test_trigger_edi_fails_closed_when_key_not_configured(client, monkeypatch):
    monkeypatch.setattr(main, "API_KEY", None)

    response = client.post("/api/actions/trigger-edi", headers={"x-api-key": "anything"})

    assert response.status_code == 500


def test_trigger_edi_success(client, auth_headers, monkeypatch):
    monkeypatch.setenv("LOGIC_APP_TRIGGER_URL", "https://example.com/trigger")

    class FakeResponse:
        ok = True
        status_code = 200
        text = "accepted"

    monkeypatch.setattr(main.requests, "post", lambda url, json: FakeResponse())

    response = client.post("/api/actions/trigger-edi", headers=auth_headers)
    body = response.json()

    assert body["success"] is True
    assert body["status_code"] == 200


def test_trigger_edi_reports_missing_logic_app_url(client, auth_headers, monkeypatch):
    monkeypatch.delenv("LOGIC_APP_TRIGGER_URL", raising=False)

    response = client.post("/api/actions/trigger-edi", headers=auth_headers)
    body = response.json()

    assert body["success"] is False
    assert "LOGIC_APP_TRIGGER_URL" in body["error"]


def test_simulate_pickup_requires_api_key(client):
    response = client.post("/api/wms/simulate-pickup")

    assert response.status_code == 401


def test_simulate_pickup_updates_ready_orders(client, auth_headers, monkeypatch):
    class FakeCursor:
        rowcount = 4

        def execute(self, sql):
            self.sql = sql

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

    response = client.post("/api/wms/simulate-pickup", headers=auth_headers)
    body = response.json()

    assert body["success"] is True
    assert body["pickedUp"] == 4


def test_run_adf_pipeline_returns_error_payload_on_failure(client, monkeypatch):
    def failing_credential():
        raise RuntimeError("no azure credentials available")

    monkeypatch.setattr(main, "DefaultAzureCredential", failing_credential)

    response = client.post("/api/adf/run")
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is False
    assert "no azure credentials available" in body["error"]


def test_run_adf_pipeline_success(client, monkeypatch):
    monkeypatch.setattr(main, "DefaultAzureCredential", lambda: object())
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "sub-1")
    monkeypatch.setenv("ADF_RESOURCE_GROUP", "rg-1")
    monkeypatch.setenv("ADF_FACTORY_NAME", "factory-1")
    monkeypatch.setenv("ADF_PIPELINE_NAME", "pipeline-1")

    class FakeRun:
        run_id = "run-123"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.pipelines = self

        def create_run(self, **kwargs):
            return FakeRun()

    monkeypatch.setattr(main, "DataFactoryManagementClient", FakeClient)

    response = client.post("/api/adf/run")
    body = response.json()

    assert body["success"] is True
    assert body["runId"] == "run-123"
