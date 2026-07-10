from datetime import datetime, timedelta, timezone

import main


def test_dashboard_summary_combines_raw_wms_and_blob_metrics(client, monkeypatch):
    call_log = []

    def fake_rows(sql):
        call_log.append(sql)
        if "COUNT(*)" in sql:
            return [{"filesReceived": 10, "filesParsed": 8, "filesFailed": 2}]
        return [{"wmsReady": 1, "wmsSent": 1, "wmsSuccess": 3, "wmsFailed": 1, "wmsPickedUp": 5}]

    monkeypatch.setattr(main, "rows", fake_rows)
    monkeypatch.setattr(
        main, "get_blob_queue_metrics", lambda: {"filesWaiting": 2, "oldestFileAgeSeconds": 45}
    )

    response = client.get("/api/dashboard/summary")
    body = response.json()

    assert response.status_code == 200
    assert body["filesReceived"] == 10
    assert body["wmsPickedUp"] == 5
    assert body["filesWaiting"] == 2
    assert len(call_log) == 2


def test_dashboard_summary_survives_blob_metrics_failure(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "rows",
        lambda sql: [{"filesReceived": 1}] if "COUNT" in sql else [{"wmsPickedUp": 0}],
    )

    def raise_error():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(main, "get_blob_queue_metrics", raise_error)

    response = client.get("/api/dashboard/summary")
    body = response.json()

    assert response.status_code == 200
    assert body["filesWaiting"] == 0
    assert "storage unavailable" in body["blobStatusError"]


def test_recent_files_returns_rows_from_db(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "rows",
        lambda sql: [
            {
                "rawId": 1,
                "isaControlNumber": "000012345",
                "isaSender": "ACME",
                "fileName": "a.edi",
                "processStatus": "PARSED",
                "loadDateTime": "2026-01-01 00:00:00",
                "errorMessage": None,
            }
        ],
    )

    response = client.get("/api/dashboard/recent-files")
    body = response.json()

    assert response.status_code == 200
    assert body[0]["fileName"] == "a.edi"
    assert body[0]["isaControlNumber"] == "000012345"


def test_wms_orders_returns_rows_from_db(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "rows",
        lambda sql: [
            {
                "wmsOrderHeaderStagingId": 1,
                "warehouseOrderNumber": "ORDER1",
                "integrationStatus": "READY",
                "attemptCount": 0,
                "errorMessage": None,
            }
        ],
    )

    response = client.get("/api/dashboard/wms-orders")
    body = response.json()

    assert response.status_code == 200
    assert body[0]["warehouseOrderNumber"] == "ORDER1"


def test_blob_status_endpoint_reports_metrics(client, monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-conn-str")

    class FakeBlob:
        def __init__(self, age_seconds):
            self.creation_time = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
            self.last_modified = self.creation_time

    class FakeContainer:
        def list_blobs(self):
            return [FakeBlob(120), FakeBlob(30)]

    class FakeBlobService:
        def get_container_client(self, name):
            return FakeContainer()

    monkeypatch.setattr(
        main.BlobServiceClient, "from_connection_string", lambda conn_str: FakeBlobService()
    )

    response = client.get("/api/dashboard/blob-status")
    body = response.json()

    assert response.status_code == 200
    assert body["filesWaiting"] == 2
    assert body["oldestAgeSeconds"] >= 120


def test_blob_status_endpoint_requires_connection_string(client, monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

    response = client.get("/api/dashboard/blob-status")

    assert response.status_code == 500
