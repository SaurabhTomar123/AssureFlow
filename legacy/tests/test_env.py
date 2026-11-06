import pytest
from sqlalchemy import text
from src.config import settings
from src.db.session import engine


def test_settings_load():
    assert settings.DATABASE_URL is not None
    assert settings.ENVIRONMENT == "development"


def test_core_dependencies_importable():
    import fastapi
    import pydantic
    import sqlalchemy
    import fitz
    import reportlab
    import PIL
    import yaml

    assert fastapi.__name__ == "fastapi"
    assert pydantic.__name__ == "pydantic"
    assert sqlalchemy.__name__ == "sqlalchemy"
    assert fitz.__name__ == "fitz"
    assert reportlab.__name__ == "reportlab"
    assert PIL.__name__ == "PIL"
    assert yaml.__name__ == "yaml"


def test_database_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar() == 1

