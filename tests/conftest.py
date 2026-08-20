import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from wealth_pilot.memory.store import MemoryStore


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(root=tmp_path / "memory")
