import sys
from pathlib import Path
import importlib.util
import pytest

LEGACY_ROOT = Path(__file__).resolve().parent.parent
if str(LEGACY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEGACY_ROOT))

spec = importlib.util.spec_from_file_location("seed_database", str(LEGACY_ROOT / "scripts" / "seed_database.py"))
if spec and spec.loader:
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seed_database = mod.seed_database
else:
    def seed_database():
        pass


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database():
    seed_database()


