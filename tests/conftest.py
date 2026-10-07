import pytest
from fastapi.testclient import TestClient

from brickline.api import create_app


@pytest.fixture
def clients(tmp_path):
    app = create_app(tmp_path / "test.db", demo=True)
    return {
        "analyst": TestClient(app, headers={"X-API-Key": "demo-analyst"}),
        "reviewer": TestClient(app, headers={"X-API-Key": "demo-reviewer"}),
        "other": TestClient(app, headers={"X-API-Key": "demo-other"}),
        "anonymous": TestClient(app),
        "path": app.state.path,
    }
