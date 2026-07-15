import main


def test_daily_volume_returns_30_days(client, monkeypatch):
    fake_data = [
        {"date": f"2026-06-{d:02d}", "count": d % 5}
        for d in range(15, 45)
    ][:30]

    monkeypatch.setattr(main, "rows", lambda sql: fake_data)

    response = client.get("/api/reports/daily-volume")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 30
    assert "date" in body[0]
    assert "count" in body[0]


def test_daily_volume_includes_zero_count_days(client, monkeypatch):
    fake_data = [
        {"date": "2026-06-01", "count": 0},
        {"date": "2026-06-02", "count": 3},
    ]

    monkeypatch.setattr(main, "rows", lambda sql: fake_data)

    response = client.get("/api/reports/daily-volume")
    body = response.json()

    assert response.status_code == 200
    zero_days = [row for row in body if row["count"] == 0]
    assert len(zero_days) == 1
    assert zero_days[0]["date"] == "2026-06-01"


def test_daily_volume_requires_auth(unauthenticated_client):
    response = unauthenticated_client.get("/api/reports/daily-volume")
    assert response.status_code == 401


def test_daily_volume_queries_edi940_raw(client, monkeypatch):
    captured_sql = []

    def capture_rows(sql):
        captured_sql.append(sql)
        return [{"date": "2026-07-01", "count": 1}]

    monkeypatch.setattr(main, "rows", capture_rows)

    client.get("/api/reports/daily-volume")

    assert len(captured_sql) == 1
    assert "EDI940_Raw" in captured_sql[0]
    assert "LoadDateTime" in captured_sql[0]


def test_file_status_summary_returns_per_sender_counts(client, monkeypatch):
    fake_data = [
        {"sender": "ACME", "received": 5, "errored": 2},
        {"sender": "GLOBEX", "received": 3, "errored": 0},
    ]

    monkeypatch.setattr(main, "rows", lambda sql: fake_data)

    response = client.get("/api/reports/file-status-summary")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 2
    assert body[0]["sender"] == "ACME"
    assert body[0]["received"] == 5
    assert body[0]["errored"] == 2


def test_file_status_summary_requires_auth(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(main, "AZURE_AD_TENANT_ID", "tenant-1")
    monkeypatch.setattr(main, "AZURE_AD_CLIENT_ID", "client-1")

    response = unauthenticated_client.get("/api/reports/file-status-summary")
    assert response.status_code == 401


def test_file_status_summary_query_scopes_last_48_hours_by_sender(client, monkeypatch):
    captured_sql = []

    def capture_rows(sql):
        captured_sql.append(sql)
        return []

    monkeypatch.setattr(main, "rows", capture_rows)

    response = client.get("/api/reports/file-status-summary")

    assert response.status_code == 200
    assert response.json() == []  # empty/no-data state is handled gracefully
    assert len(captured_sql) == 1
    sql = captured_sql[0]
    assert "EDI940_Raw" in sql
    assert "ISASender" in sql
    assert "GROUP BY ISASender" in sql
    assert "DATEADD(hour, -48, GETUTCDATE())" in sql
    assert "'%fail%'" in sql.lower()
