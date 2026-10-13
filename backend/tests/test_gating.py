"""Gates preserve scores while enforcing hard constraints, using FakeLLM only."""

import httpx
import pytest

from backend.app import db, models
from backend.app.eval.runner import EVENT_BUS, run_evaluation
from backend.app.eval.scoring import build_run_stats, compute_final_score, compute_passed
from backend.app.llm import FakeLLM
from backend.app.main import app
from backend.app.routers.runs import compare_runs, get_run_detail, prepare_run
from backend.app.schemas import RunCreate


def setup_run(*, gating=True, config=None):
    prompt = models.create_prompt("P")
    version = models.create_prompt_version(prompt["id"], "{{x}}")
    dataset = models.create_dataset("D")
    models.create_test_case(dataset["id"], {"x": "hello"}, category="standard")
    grader = models.create_grader(prompt["id"], "string_match", "safety", config or {"must_not_contain": ["refund"]}, weight=0, gating=gating)
    models.create_grader(prompt["id"], "string_match", "quality", {"must_contain": ["hello"]})
    return prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"])), grader


async def test_hard_failure_cannot_be_outweighed_snapshot_and_compare(tmp_db):
    run, grader = setup_run()
    models.update_grader(grader["id"], gating=False, config={"must_contain": ["hello"]})
    await run_evaluation(run["id"], FakeLLM(default_response="hello refund"))
    report = get_run_detail(run["id"])
    assert report.cases[0].status == "failed"
    assert report.cases[0].passed is False
    assert report.stats.avg_score == 10
    assert report.stats.pass_rate == 0
    assert report.run.pass_rate == 0
    assert report.stats.by_category["standard"].avg_score == 10
    assert report.stats.distribution[9] == 1
    assert models.get_run(run["id"])["grader_snapshot"][0]["gating"] is True
    assert EVENT_BUS.last_event(run["id"])[1]["pass_rate"] == 0
    next_run = prepare_run(RunCreate(prompt_version_id=run["prompt_version_id"], dataset_id=run["dataset_id"]))
    await run_evaluation(next_run["id"], FakeLLM(default_response="hello refund"))
    comparison = compare_runs(next_run["id"], run["id"])
    assert comparison.deltas.avg_score == 0
    assert comparison.deltas.pass_rate == 1


@pytest.mark.parametrize("kind,score,threshold,passed", [
    ("string_match", 5, 0, False),
    ("code_syntax", 0, 0, False),
    ("json_schema", 0, 0, False),
    ("budget", 0, 0, False),
    ("string_match", 10, 0, True),
    ("llm_judge", 7.9, 8, False),
    ("llm_judge", 8, 8, True),
])
def test_gate_semantics(kind, score, threshold, passed):
    grades = [{"grader_type": kind, "score": score, "weight": 0, "details": {"_gating": True, "_pass_threshold": threshold}}]
    assert compute_passed(grades) is passed


@pytest.mark.parametrize("status", ["skipped", "failed"])
def test_unscored_gate_is_inconclusive(status):
    grades = [{"grader_type": "code_syntax", "score": 0, "details": {"_gating": True, "_status": status}}]
    assert compute_passed(grades) is None
    assert build_run_stats([{"status": "completed", "passed": None, "grades": grades}])["pass_rate"] == 0


def test_worked_example_without_gates():
    grades = [{"score": 8, "weight": 1}, {"score": 6, "weight": 2}, {"score": 0, "weight": 1, "details": {"_status": "skipped"}}]
    assert compute_final_score(grades) == pytest.approx(20 / 3)
    assert compute_passed(grades) is True
    assert build_run_stats([])["pass_rate"] is None


async def test_partial_string_match_fails_gate(tmp_db):
    run, _ = setup_run(config={"must_contain": ["hello"], "must_not_contain": ["refund"]})
    await run_evaluation(run["id"], FakeLLM(default_response="hello refund"))
    report = get_run_detail(run["id"])
    assert report.cases[0].grades[0].score == 5
    assert report.cases[0].passed is False


async def test_failed_gate_beats_high_weight_llm_judge(tmp_db):
    run, _ = setup_run()
    prompt_id = models.get_prompt_version(run["prompt_version_id"])["prompt_id"]
    models.create_grader(prompt_id, "llm_judge", "judge", {"rubric": "Helpful", "use_solution_criteria": False}, weight=100)
    run = prepare_run(RunCreate(prompt_version_id=run["prompt_version_id"], dataset_id=run["dataset_id"]))
    fake = FakeLLM()
    fake.queue_response("hello refund")
    fake.queue_response('{"strengths": [], "weaknesses": [], "reasoning": "Helpful", "score": 10}')
    await run_evaluation(run["id"], fake)
    report = get_run_detail(run["id"])
    assert report.stats.avg_score == 10
    assert report.stats.pass_rate == 0
    assert report.cases[0].passed is False


async def test_skipped_gate_stays_inconclusive_in_persisted_api(tmp_db):
    run, _ = setup_run(gating=False)
    prompt_id = models.get_prompt_version(run["prompt_version_id"])["prompt_id"]
    models.create_grader(prompt_id, "code_syntax", "auto", {"format": "auto"}, gating=True)
    run = prepare_run(RunCreate(prompt_version_id=run["prompt_version_id"], dataset_id=run["dataset_id"]))
    await run_evaluation(run["id"], FakeLLM(default_response="hello"))
    case = get_run_detail(run["id"]).cases[0]
    assert case.status == "completed"
    assert case.passed is None
    assert get_run_detail(run["id"]).stats.pass_rate == 0


async def test_gate_api_roundtrip_and_threshold_validation(tmp_db):
    prompt = models.create_prompt("P")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/prompts/{prompt['id']}/graders", json={"type": "llm_judge", "name": "judge", "gating": True, "pass_threshold": 9, "config": {"rubric": "Helpful", "use_solution_criteria": True}})
        assert response.status_code == 201
        grader = response.json()
        assert grader["gating"] is True and grader["pass_threshold"] == 9
        assert (await client.patch(f"/api/graders/{grader['id']}", json={"pass_threshold": 11})).status_code == 422
        updated = await client.patch(f"/api/graders/{grader['id']}", json={"gating": False, "pass_threshold": 7})
        assert updated.json()["gating"] is False
        assert (await client.get(f"/api/prompts/{prompt['id']}/graders")).json()[0]["pass_threshold"] == 7


def test_migration_preserves_old_verdicts_and_is_idempotent(tmp_db):
    run, _ = setup_run(gating=False)
    case = models.create_run_case(run["id"], models.list_test_cases(run["dataset_id"])[0]["id"], 0, status="completed")
    with db.connection(write=True) as conn:
        conn.execute("ALTER TABLE run_case DROP COLUMN passed")
        conn.execute("ALTER TABLE grader DROP COLUMN gating")
        conn.execute("ALTER TABLE grader DROP COLUMN pass_threshold")
        conn.execute("ALTER TABLE run DROP COLUMN pass_rate")
    db.init_db()
    db.init_db()
    assert models.get_run_case(case["id"])["passed"] == 1
    assert models.list_graders(1)[0]["gating"] is False
