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
    def fake_rows_params(sql, params):
        if "dbo.ErrorKnowledgeBase" in sql:
            return []
        return [
            {
                "rawId": 42,
                "fileName": "sample.edi",
                "processStatus": "PARSE_FAILED",
                "loadDateTime": "2026-01-01 12:00:00",
                "errorMessage": "No ST*940 transaction sets were parsed from this file.",
                "rawContent": ISA_SEGMENT,
            }
        ]

    monkeypatch.setattr(main, "rows_params", fake_rows_params)

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


def test_resolve_customer_alias_maps_known_alias(monkeypatch):
    captured = {}

    def fake_rows_params(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"CustomerCode": "LOW"}]

    monkeypatch.setattr(main, "rows_params", fake_rows_params)

    assert main.resolve_customer_alias("Lowes") == "LOW"
    assert captured["params"] == ("Lowes",)
    assert "dbo.CustomerAliases" in captured["sql"]


def test_resolve_customer_alias_falls_back_to_input_when_unknown(monkeypatch):
    monkeypatch.setattr(main, "rows_params", lambda sql, params: [])

    assert main.resolve_customer_alias("SOMECODE") == "SOMECODE"


def test_handle_failed_orders_resolves_alias_before_filtering(monkeypatch):
    captured = {}

    def fake_rows_params(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    def fake_resolve(term):
        assert term == "Lowes"
        return "LOW"

    monkeypatch.setattr(main, "rows_params", fake_rows_params)
    monkeypatch.setattr(main, "resolve_customer_alias", fake_resolve)

    result = main.handle_failed_orders(customer="Lowes")

    assert captured["params"] == ("LOW",)
    assert "for customer LOW" in result["reply"]


def test_explain_error_returns_none_for_empty_message():
    assert main.explain_error(None) is None
    assert main.explain_error("") is None


def test_explain_error_returns_none_when_no_match(monkeypatch):
    monkeypatch.setattr(main, "rows_params", lambda sql, params: [])

    assert main.explain_error("some unrecognized SQL error") is None


def test_explain_error_combines_explanation_and_remediation(monkeypatch):
    captured = {}

    def fake_rows_params(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{
            "Explanation": "A W01 line is missing a valid quantity.",
            "RemediationStep": "Ask the sender to resend with a corrected quantity.",
        }]

    monkeypatch.setattr(main, "rows_params", fake_rows_params)

    result = main.explain_error("EDI 940 validation failed: W01 quantity is missing, invalid, or zero.")

    assert result == (
        "A W01 line is missing a valid quantity. "
        "Ask the sender to resend with a corrected quantity."
    )
    assert captured["params"] == ("EDI 940 validation failed: W01 quantity is missing, invalid, or zero.",)
    assert "dbo.ErrorKnowledgeBase" in captured["sql"]


def test_explain_error_omits_remediation_when_absent(monkeypatch):
    monkeypatch.setattr(
        main,
        "rows_params",
        lambda sql, params: [{"Explanation": "Just an explanation.", "RemediationStep": None}],
    )

    assert main.explain_error("whatever") == "Just an explanation."


class _FakeLocalModelResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content, "tool_calls": None}}]}


def test_local_model_fallback_falls_back_to_claude_on_leaked_tool_call(monkeypatch):
    monkeypatch.setattr(main, "LOCAL_MODEL_BASE_URL", "http://fake-local-model")
    monkeypatch.setattr(
        main,
        "_local_model_request",
        lambda messages, tools, max_tokens: _FakeLocalModelResponse(
            '<tool_call>\n{"name": "list_failed_orders", "arguments": {"customer": "TGT"}}\n</tool_call>'
            "assistantHere are the links..."
        ),
    )

    result = main.handle_local_model_fallback("give me links to those files", main.AI_TOOLS, main.AI_TOOL_DISPATCH)

    assert result is None


def test_local_model_fallback_returns_plain_text_reply(monkeypatch):
    monkeypatch.setattr(main, "LOCAL_MODEL_BASE_URL", "http://fake-local-model")
    monkeypatch.setattr(
        main,
        "_local_model_request",
        lambda messages, tools, max_tokens: _FakeLocalModelResponse("I can only help with PO/ISA status."),
    )

    result = main.handle_local_model_fallback("what's the weather", main.AI_TOOLS, main.AI_TOOL_DISPATCH)

    assert result["reply"] == "I can only help with PO/ISA status."
    assert result["source"] == "local_ai"


def test_dispatch_file_download_prefers_file_name(monkeypatch):
    monkeypatch.setattr(main, "handle_file_download_by_filename", lambda name: {"called_with": name})
    monkeypatch.setattr(main, "handle_file_download_by_isa", lambda isa: {"called_with": isa})

    result = main.dispatch_file_download({"file_name": "sample.edi", "isa_number": "000012345"})

    assert result == {"called_with": "sample.edi"}


def test_dispatch_file_download_falls_back_to_isa_number(monkeypatch):
    monkeypatch.setattr(main, "handle_file_download_by_isa", lambda isa: {"called_with": isa})

    result = main.dispatch_file_download({"isa_number": "000012345"})

    assert result == {"called_with": "000012345"}


def test_dispatch_file_download_requires_some_input():
    result = main.dispatch_file_download({})

    assert result["downloads"] == []
    assert "file name or the ISA control number" in result["reply"]


def test_handle_failed_orders_appends_explanation_when_available(monkeypatch):
    failed_row = {
        "fileName": "bad.edi",
        "sender": "LOW",
        "processStatus": "PARSE_FAILED",
        "errorMessage": "some parse error",
        "loadDateTime": "2026-01-01 12:00:00",
    }

    def fake_rows_params(sql, params):
        assert "dbo.ErrorKnowledgeBase" in sql
        return [{"Explanation": "Known issue.", "RemediationStep": None}]

    monkeypatch.setattr(main, "rows_params", fake_rows_params)
    monkeypatch.setattr(main, "rows", lambda sql: [failed_row])

    result = main.handle_failed_orders()

    assert "some parse error (Known issue.)" in result["reply"]
