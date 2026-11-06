import pytest
from scripts.seed_database import seed_database


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database():
    seed_database()

