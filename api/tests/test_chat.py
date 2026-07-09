import main


def test_po_lookup_found(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "rows_params",
        lambda sql, params: [
            {
                "wmsOrderHeaderStagingId": 1,
                "warehouseOrderNumber": "ORDER1001",
                "integrationStatus": "READY",
                "attemptCount": 0,
                "errorMessage": None,
            }
        ],
    )

    response = client.post("/api/chat", json={"question": "Where is PO ORDER1001?"})
    body = response.json()

    assert response.status_code == 200
    assert body["intent"] == "po_lookup"
    assert "ORDER1001" in body["reply"]
    assert "waiting to be sent to WMS" in body["reply"]


def test_po_lookup_reports_failure_reason(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "rows_params",
        lambda sql, params: [
            {
                "wmsOrderHeaderStagingId": 3,
                "warehouseOrderNumber": "ORDER1003",
                "integrationStatus": "FAILED",
                "attemptCount": 2,
                "errorMessage": "Mock WMS rejected order: invalid SKU.",
            }
        ],
    )

    response = client.post("/api/chat", json={"question": "Where is PO ORDER1003?"})
    body = response.json()

    assert "invalid SKU" in body["reply"]


def test_po_lookup_not_found(client, monkeypatch):
    monkeypatch.setattr(main, "rows_params", lambda sql, params: [])

    response = client.post("/api/chat", json={"question": "Where is PO UNKNOWN?"})
    body = response.json()

    assert body["intent"] == "po_lookup"
    assert body["matches"] == []
    assert "couldn't find PO/order UNKNOWN" in body["reply"]


ISA_SEGMENT = (
    "ISA*00*          *00*          *ZZ*SENDER*ZZ*RECEIVER*250101*1200*U*00401"
    "*000012345*0*P*>~"
)


def test_isa_lookup_found(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "rows_params",
        lambda sql, params: [
            {
                "rawId": 42,
                "fileName": "sample.edi",
                "processStatus": "PARSE_FAILED",
                "loadDateTime": "2026-01-01 12:00:00",
                "errorMessage": "No ST*940 transaction sets were parsed from this file.",
                "rawContent": ISA_SEGMENT,
            }
        ],
    )

    response = client.post("/api/chat", json={"question": "What happened with ISA 000012345?"})
    body = response.json()

    assert body["intent"] == "isa_lookup"
    assert "sample.edi" in body["reply"]
    assert "failed to parse" in body["reply"]
    assert body["matches"][0]["isaControlNumber"] == "000012345"


def test_isa_lookup_not_found(client, monkeypatch):
    monkeypatch.setattr(main, "rows_params", lambda sql, params: [])

    response = client.post("/api/chat", json={"question": "What happened with ISA 999999999?"})
    body = response.json()

    assert body["intent"] == "isa_lookup"
    assert "couldn't find any file" in body["reply"]


def test_unknown_intent_suggests_latest_failed_isa(client, monkeypatch):
    monkeypatch.setattr(main, "get_latest_failed_isa", lambda: "000098765")

    response = client.post("/api/chat", json={"question": "hello there"})
    body = response.json()

    assert body["intent"] == "unknown"
    assert "000098765" in body["reply"]
    assert body["matches"] == []


def test_unknown_intent_falls_back_to_placeholder_isa(client, monkeypatch):
    monkeypatch.setattr(main, "get_latest_failed_isa", lambda: None)

    response = client.post("/api/chat", json={"question": "hello there"})
    body = response.json()

    assert "000012345" in body["reply"]


def test_sample_isa_endpoint_returns_latest_failure(client, monkeypatch):
    monkeypatch.setattr(main, "get_latest_failed_isa", lambda: "000054321")

    response = client.get("/api/chat/sample-isa")

    assert response.status_code == 200
    assert response.json() == {"isaControlNumber": "000054321"}


def test_sample_isa_endpoint_returns_null_when_no_failures(client, monkeypatch):
    monkeypatch.setattr(main, "get_latest_failed_isa", lambda: None)

    response = client.get("/api/chat/sample-isa")

    assert response.json() == {"isaControlNumber": None}


def test_get_latest_failed_isa_queries_expected_sql(monkeypatch):
    captured_sql = {}

    def fake_rows(sql):
        captured_sql["sql"] = sql
        return [{"isaControlNumber": "000011111"}]

    monkeypatch.setattr(main, "rows", fake_rows)

    assert main.get_latest_failed_isa() == "000011111"
    assert "ISA_ControlNumber" in captured_sql["sql"]
    assert "ProcessStatus LIKE '%FAIL%'" in captured_sql["sql"]
    assert "ORDER BY RawId DESC" in captured_sql["sql"]


def test_get_latest_failed_isa_returns_none_when_no_rows(monkeypatch):
    monkeypatch.setattr(main, "rows", lambda sql: [])

    assert main.get_latest_failed_isa() is None
