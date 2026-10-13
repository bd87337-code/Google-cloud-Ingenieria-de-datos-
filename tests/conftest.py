import pytest

from macro_tracker.db.connection import connect
from macro_tracker.db.repository import Repository


@pytest.fixture
def repo():
    conn = connect(":memory:")
    yield Repository(conn)
    conn.close()


@pytest.fixture
def sample_profile():
    """Perfil sintético (no son datos reales de nadie)."""
    return dict(
        sex="M", birth_date="1996-05-20", height_cm=180, activity_level="moderate",
        goal="lose", rate_kg_week=0.5,
    )
