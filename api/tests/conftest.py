import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    # Bypass real Azure AD JWT validation in tests - business-logic tests
    # shouldn't need a live token or network access to Azure's JWKS endpoint.
    # Auth itself is covered separately in tests/test_auth.py.
    main.app.dependency_overrides[main.require_auth] = lambda: {"sub": "test-user"}
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client():
    # No dependency override - exercises the real require_auth path, for
    # tests that specifically check auth is enforced.
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
