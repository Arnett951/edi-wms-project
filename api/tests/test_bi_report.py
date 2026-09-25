import requests

import main


class FakeResponse:
    def __init__(self, status_code, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self._payload = payload

    def json(self):
        return self._payload


def _configure(monkeypatch, fake_get):
    monkeypatch.setattr(main, "BI_REPORT_BASE_URL", "http://skynet.test:8790")
    monkeypatch.setattr(main, "_bi_report_hits", {})
    monkeypatch.setattr(main.requests, "get", fake_get)


def test_facilities_are_public_and_proxied(unauthenticated_client, monkeypatch):
    facilities = [{"code": "DEMO-EAST", "name": "Demo East Tire Distribution"}]
    _configure(monkeypatch, lambda url, **kw: FakeResponse(200, payload=facilities))

    response = unauthenticated_client.get("/api/public/bi-report/facilities")

    assert response.status_code == 200
    assert response.json() == facilities


def test_pdf_passes_facility_through_and_returns_pdf(unauthenticated_client, monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append((url, kw["params"]))
        return FakeResponse(200, content=b"%PDF-1.4 fake")

    _configure(monkeypatch, fake_get)

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=DEMO-WEST")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert calls == [("http://skynet.test:8790/report.pdf", {"report": "inventory-aging", "facility": "DEMO-WEST"})]


def test_pdf_passes_legacy_source_through(unauthenticated_client, monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(kw["params"])
        return FakeResponse(200, content=b"%PDF-1.4 fake")

    _configure(monkeypatch, fake_get)

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=PERRIS&source=legacy")

    assert response.status_code == 200
    assert "legacy" in response.headers["content-disposition"]
    assert calls == [{"report": "inventory-aging", "facility": "PERRIS", "source": "legacy"}]


def test_pdf_rejects_unknown_source_without_calling_upstream(unauthenticated_client, monkeypatch):
    def fail(url, **kw):
        raise AssertionError("upstream should not be called")

    _configure(monkeypatch, fail)

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=PERRIS&source=Bad Source")

    assert response.status_code == 400


def test_pdf_rejects_malformed_facility_without_calling_upstream(unauthenticated_client, monkeypatch):
    def fail(url, **kw):
        raise AssertionError("upstream should not be called")

    _configure(monkeypatch, fail)

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=x' OR 1=1--")

    assert response.status_code == 400


def test_pdf_is_rate_limited_per_client(unauthenticated_client, monkeypatch):
    _configure(monkeypatch, lambda url, **kw: FakeResponse(200, content=b"%PDF"))

    codes = [
        unauthenticated_client.get("/api/public/bi-report/pdf?facility=DEMO-EAST").status_code
        for _ in range(main.BI_REPORT_RATE_LIMIT + 1)
    ]

    assert codes[:-1] == [200] * main.BI_REPORT_RATE_LIMIT
    assert codes[-1] == 429


def test_offline_upstream_returns_503(unauthenticated_client, monkeypatch):
    def offline(url, **kw):
        raise requests.ConnectionError("no route to host")

    _configure(monkeypatch, offline)

    response = unauthenticated_client.get("/api/public/bi-report/facilities")

    assert response.status_code == 503
    assert "offline" in response.json()["detail"]


def test_unconfigured_service_returns_503(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(main, "BI_REPORT_BASE_URL", None)

    response = unauthenticated_client.get("/api/public/bi-report/facilities")

    assert response.status_code == 503


def test_reports_listing_is_public_and_proxied(unauthenticated_client, monkeypatch):
    reports = [{"id": "location-heatmap", "title": "Location Aging Heatmap", "description": "", "sources": []}]
    _configure(monkeypatch, lambda url, **kw: FakeResponse(200, payload=reports))

    response = unauthenticated_client.get("/api/public/bi-report/reports")

    assert response.status_code == 200
    assert response.json() == reports


def test_pdf_passes_report_id_through(unauthenticated_client, monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(kw["params"])
        return FakeResponse(200, content=b"%PDF-1.4 fake")

    _configure(monkeypatch, fake_get)

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=ATLANTA&report=location-heatmap")

    assert response.status_code == 200
    assert "location-heatmap-ATLANTA" in response.headers["content-disposition"]
    assert calls == [{"report": "location-heatmap", "facility": "ATLANTA"}]


def test_pdf_rejects_path_like_report_without_calling_upstream(unauthenticated_client, monkeypatch):
    def fail(url, **kw):
        raise AssertionError("upstream should not be called")

    _configure(monkeypatch, fail)

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=PERRIS&report=../etc")

    assert response.status_code == 400


def test_pdf_surfaces_upstream_unknown_report(unauthenticated_client, monkeypatch):
    _configure(monkeypatch, lambda url, **kw: FakeResponse(400, payload={"detail": "Unknown report"}))

    response = unauthenticated_client.get("/api/public/bi-report/pdf?facility=PERRIS&report=not-there")

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown report."
