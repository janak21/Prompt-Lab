"""CLI uses the real database and engine with a network-free FakeLLM."""

import json

import pytest

from backend.app import cli, models
from backend.app.llm import FakeLLM


def setup():
    prompt = models.create_prompt("Support")
    version = models.create_prompt_version(prompt["id"], "Old: {{x}}")
    models.create_prompt_version(prompt["id"], "New: {{x}}")
    dataset = models.create_dataset("Tickets")
    models.create_test_case(dataset["id"], {"x": "ticket"}, category="standard")
    models.create_grader(prompt["id"], "string_match", "quality", {"must_contain": ["hello"]}, gating=True)
    return prompt, version, dataset


def test_cli_summary_latest_version_report_and_threshold_boundary(tmp_db, tmp_path, capsys):
    setup()
    fake = FakeLLM(default_response="hello")
    path = tmp_path / "report.json"
    result = cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", "--fail-under", "10", "--require-pass-rate", "1", "--json", str(path)], llm=fake)
    assert result == 0
    assert fake.calls[0].messages[0]["content"] == "New: ticket"
    report = json.loads(path.read_text())
    assert report["run"]["version_no"] == 2
    assert report["stats"]["pass_rate"] == 1
    assert "standard: 10.00" in capsys.readouterr().out


def test_cli_ids_and_pinned_version(tmp_db):
    prompt, version, dataset = setup()
    fake = FakeLLM(default_response="hello")
    assert cli.main(["run", "--prompt", str(prompt["id"]), "--version", "1", "--dataset", str(dataset["id"])], llm=fake) == 0
    assert fake.calls[0].messages[0]["content"] == "Old: ticket"


@pytest.mark.parametrize("flag,value", [("--fail-under", "8"), ("--require-pass-rate", "1")])
def test_threshold_failure_writes_report(tmp_db, tmp_path, flag, value):
    setup()
    path = tmp_path / "failed.json"
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", flag, value, "--json", str(path)], llm=FakeLLM(default_response="bad")) == 1
    assert json.loads(path.read_text())["cases"][0]["passed"] is False


def test_llm_failure_exits_nonzero_and_writes_report(tmp_db, tmp_path):
    setup()
    fake = FakeLLM()
    fake.queue_failure(RuntimeError("upstream failed"))
    path = tmp_path / "failed.json"
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", "--json", str(path)], llm=fake) == 1
    assert json.loads(path.read_text())["cases"][0]["error"] == "upstream failed"


def test_resolution_errors_do_not_call_llm(tmp_db):
    setup()
    models.create_prompt("Support")
    fake = FakeLLM()
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets"], llm=fake) == 2
    assert cli.main(["run", "--prompt", "missing", "--dataset", "Tickets"], llm=fake) == 2
    assert cli.main(["run", "--prompt", "1", "--version", "99", "--dataset", "Tickets"], llm=fake) == 2
    assert not fake.calls


def test_empty_dataset_rejected(tmp_db):
    setup()
    models.create_dataset("Empty")
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Empty"], llm=FakeLLM()) == 2


def test_explicit_pass_rate_can_allow_gate_failures(tmp_db):
    setup()
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", "--require-pass-rate", "0"], llm=FakeLLM(default_response="bad")) == 0


def test_unscored_run_cannot_meet_score_threshold(tmp_db):
    prompt, _, _ = setup()
    models.delete_grader(models.list_graders(prompt["id"])[0]["id"])
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", "--fail-under", "0"], llm=FakeLLM()) == 1


def test_global_failure_writes_report(tmp_db, tmp_path, monkeypatch):
    setup()

    async def fail(run_id, llm):
        models.update_run(run_id, status="failed", error="Setup failed")

    monkeypatch.setattr(cli.runner, "run_evaluation", fail)
    path = tmp_path / "failed.json"
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", "--json", str(path)], llm=FakeLLM()) == 1
    assert json.loads(path.read_text())["run"]["status"] == "failed"


@pytest.mark.parametrize("flag,value", [("--fail-under", "nan"), ("--fail-under", "11"), ("--require-pass-rate", "1.1"), ("--require-pass-rate", "-1")])
def test_invalid_thresholds(flag, value):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--prompt", "P", "--dataset", "D", flag, value], llm=FakeLLM())
    assert exc.value.code == 2
