import json
import sqlite3
import subprocess
import sys

import pytest

from arf.models import ARFError, Charter, TaskSpec, parse_json
from arf.store import Store
from conftest import ROOT, spec


def cli(*arguments, ok=True):
    result = subprocess.run(
        [sys.executable, "-m", "arf", *map(str, arguments)],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    if ok:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        return json.loads(result.stdout)
    assert result.returncode != 0 and result.stderr
    assert result.stdout == "" and "Traceback" not in result.stderr
    return result


def test_a2_full_cli_restart_and_durable_observations(tmp_path):
    db = tmp_path / "nested" / "arf.db"
    assert cli("init", "--db", db, "--charter", ROOT / "examples/demo-charter.yaml")["status"] == "imported"
    cli("task", "add", "--db", db, "--spec", ROOT / "examples/demo-task.json")
    assert cli("task", "list", "--db", db)[0]["status"] == "pending"
    assert cli("run-next", "--db", db)["status"] == "succeeded"
    task = cli("task", "show", "--db", db, "--id", "demo-mean")
    evidence = cli("evidence", "list", "--db", db)
    with Store(db) as store:
        study = store.study()
    assert cli("recover", "--db", db)["interrupted"] == []
    assert cli("run-next", "--db", db) == {"status": "no_ready_task"}
    assert cli("task", "show", "--db", db, "--id", "demo-mean") == task
    assert cli("evidence", "list", "--db", db) == evidence
    assert cli("init", "--db", db, "--charter", ROOT / "examples/demo-charter.yaml")["status"] == "already_exists"
    with Store(db) as store:
        assert store.study() == study
        assert task["runs"] == store.task("demo-mean")["runs"]
    cli("task", "add", "--db", db, "--spec", ROOT / "examples/demo-task.json", ok=False)
    cli("task", "retry", "--db", db, "--id", "demo-mean", ok=False)


def test_cli_explicit_recovery_and_retry(ready):
    ready.claim_next()  # Simulate a crash immediately after the durable claim.
    db = ready.path
    assert len(cli("recover", "--db", db)["interrupted"]) == 1
    assert cli("recover", "--db", db)["interrupted"] == []
    assert cli("run-next", "--db", db)["status"] == "no_ready_task"
    assert cli("task", "retry", "--db", db, "--id", "demo-mean")["status"] == "pending"
    assert cli("run-next", "--db", db)["status"] == "succeeded"
    task = cli("task", "show", "--db", db, "--id", "demo-mean")
    assert [run["status"] for run in task["runs"]] == ["interrupted", "succeeded"]


@pytest.mark.parametrize("values", [[], [True], [False], [None], ["2"], [float("nan")],
                                        [float("inf")], [-float("inf")], [10**400], {}, None])
def test_a5_malformed_input_rejected(values):
    with pytest.raises(ARFError):
        TaskSpec.parse(spec(input={"values": values}))


@pytest.mark.parametrize("data", [
    spec(kind="shell"), spec(kind="python"), spec(kind="https://example.com"),
    spec(command="touch SHOULD_NOT_EXIST"), spec(code="print(1)"),
    spec(module="os"), spec(url="https://example.com"),
    spec(input={"values": [2], "command": "anything"}),
    spec(input={"values": ["https://example.com"]}),
    spec(input={"values": ["__import__('os').system('id')"]}),
])
def test_a9_rejected_specs_never_reach_executor(ready, tmp_path, data):
    path = tmp_path / "unsupported.json"
    path.write_text(json.dumps(data))
    before = ready.tasks()
    cli("task", "add", "--db", ready.path, "--spec", path, ok=False)
    assert ready.tasks() == before
    assert ready.task("demo-mean")["runs"] == []


@pytest.mark.parametrize("source", [
    b"", b"[]", b"study_id: x\nquestion: null\nsuccess_criteria: []",
    b"study_id: x\nquestion: Q\nsuccess_criteria: []",
    b"study_id: x\nquestion: Q\nsuccess_criteria: [null]",
    b"study_id: x\nquestion: Q\nsuccess_criteria: [ok]\nconstraints: null",
    b"study_id: x\nstudy_id: y\nquestion: Q\nsuccess_criteria: [ok]",
    b"!!python/object/apply:os.system [id]", b"study_id: [", b"\xff",
])
def test_invalid_charter(source):
    with pytest.raises(ARFError):
        Charter.parse(source)


def test_template_invalid_and_failed_init_creates_no_database(tmp_path):
    db = tmp_path / "invalid.db"
    cli("init", "--db", db, "--charter", ROOT / "charter.template.yaml", ok=False)
    assert not db.exists()


def test_charter_optional_constraints():
    assert Charter.parse(b"study_id: x\nquestion: Q\nsuccess_criteria: [ok]").constraints == []


def test_duplicate_json_fields_and_missing_db(tmp_path):
    with pytest.raises(ARFError, match="duplicate"):
        parse_json('{"kind":"shell", "kind":"demo_mean"}')
    cli("task", "list", "--db", tmp_path / "missing.db", ok=False)
    assert not (tmp_path / "missing.db").exists()


def test_unknown_schema_and_unrelated_database_are_not_modified(tmp_path):
    db = tmp_path / "other.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE existing(value TEXT)")
        connection.execute("INSERT INTO existing VALUES ('preserve me')")
    with pytest.raises(ARFError, match="nonempty unversioned"):
        Store(db, create=True)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT * FROM existing").fetchall() == [("preserve me",)]
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(ARFError, match="version: 999"):
        Store(db)
