import main


def test_trigger_edi_success(client, monkeypatch):
    monkeypatch.setenv("LOGIC_APP_TRIGGER_URL", "https://example.com/trigger")

    class FakeResponse:
        ok = True
        status_code = 200
        text = "accepted"

    monkeypatch.setattr(main.requests, "post", lambda url, json: FakeResponse())

    response = client.post("/api/actions/trigger-edi")
    body = response.json()

    assert body["success"] is True
    assert body["status_code"] == 200


def test_trigger_edi_reports_missing_logic_app_url(client, monkeypatch):
    monkeypatch.delenv("LOGIC_APP_TRIGGER_URL", raising=False)

    response = client.post("/api/actions/trigger-edi")
    body = response.json()

    assert body["success"] is False
    assert "LOGIC_APP_TRIGGER_URL" in body["error"]


def test_simulate_pickup_updates_ready_orders(client, monkeypatch):
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

    response = client.post("/api/wms/simulate-pickup")
    body = response.json()

    assert body["success"] is True
    assert body["pickedUp"] == 4


def test_run_adf_pipeline_returns_generic_error_on_failure(client, monkeypatch):
    def failing_credential():
        raise RuntimeError("no azure credentials available")

    monkeypatch.setattr(main, "DefaultAzureCredential", failing_credential)

    response = client.post("/api/adf/run")

    # The failure detail (e.g. an internal exception message) is logged
    # server-side, not returned to the caller - see main.run_adf_pipeline.
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to start the ADF pipeline."


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
