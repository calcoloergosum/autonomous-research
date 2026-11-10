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


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "arf.db", create=True) as database:
        database.import_charter(Charter.parse((ROOT / "examples/demo-charter.yaml").read_bytes()))
        yield database


@pytest.fixture
def ready(store):
    store.add_task(TaskSpec.parse(spec()))
    return store
