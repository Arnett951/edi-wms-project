import change_request_lib as cr_lib
import main


class FakeCursor:
    """Records the SQL/params it was asked to execute and returns canned rows."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        return self

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self.cursor_obj


def _row(cr_number, status):
    # Build a row matching CR_COLUMNS order; only CRNumber and Status matter here.
    values = {"CRNumber": cr_number, "Status": status}
    return tuple(values.get(col) for col in cr_lib.CR_COLUMNS)


def test_list_crs_active_filters_out_closed_and_merged():
    conn = FakeConn([_row(1, "Pending Gate 1 review")])
    cr_lib.list_crs(conn, "active")
    sql, params = conn.cursor_obj.executed[0]
    assert "Status NOT LIKE ?" in sql
    assert list(params) == ["Merged%", "Closed%", "Auto-denied%", "Rolled back%"]


def test_list_crs_closed_filters_to_closed_and_merged():
    conn = FakeConn([_row(2, "Merged (Gate 2) by X on Y")])
    cr_lib.list_crs(conn, "closed")
    sql, params = conn.cursor_obj.executed[0]
    assert "Status LIKE ?" in sql
    assert "NOT LIKE" not in sql
    assert list(params) == ["Merged%", "Closed%", "Auto-denied%", "Rolled back%"]


def test_list_crs_closed_includes_auto_denied_and_rolled_back():
    # CR-015: Auto-denied and Rolled back CRs are grouped under the Closed tab.
    conn = FakeConn([])
    cr_lib.list_crs(conn, "closed")
    sql, params = conn.cursor_obj.executed[0]
    assert "Auto-denied%" in params
    assert "Rolled back%" in params
    # Four prefixes -> four OR'd LIKE clauses.
    assert sql.count("Status LIKE ?") == 4


def test_list_crs_no_group_returns_all_without_where():
    conn = FakeConn([])
    cr_lib.list_crs(conn)
    sql, params = conn.cursor_obj.executed[0]
    assert "WHERE" not in sql
    assert params == ()


def test_list_change_requests_endpoint_passes_status_group(client, monkeypatch):
    captured = {}

    def fake_list_crs(conn, status_group=None):
        captured["status_group"] = status_group
        return []

    monkeypatch.setattr(main, "get_user_permissions", lambda oid: ["cr.admin"])
    monkeypatch.setattr(cr_lib, "get_conn", lambda: FakeConn([]))
    monkeypatch.setattr(cr_lib, "list_crs", fake_list_crs)

    response = client.get("/api/change-requests?status_group=closed")

    assert response.status_code == 200
    assert captured["status_group"] == "closed"
