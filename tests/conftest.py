from pathlib import Path

import pytest

from arf.models import Charter, TaskSpec
from arf.store import Store


ROOT = Path(__file__).resolve().parents[1]


def spec(task_id="demo-mean", dependencies=None, **overrides):
    data = {
        "task_id": task_id,
        "study_id": "demo-mean-study",
        "title": "Calculate example mean",
        "description": "Fixed integration fixture",
        "kind": "demo_mean",
        "input": {"values": [2, 4, 6, 8]},
        "dependencies": dependencies or [],
    }
    data.update(overrides)
    return data


def pytest_generate_tests(metafunc):
    # Reuse every original Store-based acceptance case on both schema versions.
    if metafunc.module.__name__ in ("test_lifecycle", "test_validation_cli") and "store" in metafunc.fixturenames:
        metafunc.parametrize("store", [1, 2], indirect=True, ids=["v1", "v2"])


@pytest.fixture
def store(tmp_path, request):
    with Store(tmp_path / "arf.db", create=True) as database:
        database.import_charter(Charter.parse((ROOT / "examples/demo-charter.yaml").read_bytes()))
        if getattr(request, "param", 1) == 2:
            from arf.plan_store import migrate
            migrate(database)
        yield database


@pytest.fixture
def ready(store):
    store.add_task(TaskSpec.parse(spec()))
    return store
