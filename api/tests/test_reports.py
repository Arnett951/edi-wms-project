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


def test_inbound_files_by_customer_returns_list(client, monkeypatch):
    fake_data = [
        {"date": "2026-07-08", "sender": "ACME", "count": 3},
        {"date": "2026-07-08", "sender": "BETA", "count": 1},
        {"date": "2026-07-09", "sender": "ACME", "count": 2},
    ]

    monkeypatch.setattr(main, "rows", lambda sql: fake_data)

    response = client.get("/api/reports/inbound-files-by-customer")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, list)
    assert len(body) == 3
    assert "date" in body[0]
    assert "sender" in body[0]
    assert "count" in body[0]


def test_inbound_files_by_customer_requires_auth(unauthenticated_client):
    response = unauthenticated_client.get(
        "/api/reports/inbound-files-by-customer"
    )
    assert response.status_code == 401


def test_inbound_files_by_customer_queries_edi940_raw(client, monkeypatch):
    captured_sql = []

    def capture_rows(sql):
        captured_sql.append(sql)
        return [{"date": "2026-07-08", "sender": "ACME", "count": 1}]

    monkeypatch.setattr(main, "rows", capture_rows)

    client.get("/api/reports/inbound-files-by-customer")

    assert len(captured_sql) == 1
    assert "EDI940_Raw" in captured_sql[0]
    assert "ISASender" in captured_sql[0]
    assert "LoadDateTime" in captured_sql[0]
