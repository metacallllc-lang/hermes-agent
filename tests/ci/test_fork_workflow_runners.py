"""Replay runner and publication routing for upstream and an unprovisioned fork."""
from pathlib import Path

import hermes_yaml as yaml

from tests.ci import _gha_expr as gha

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
STANDARD = {
    "ubuntu-latest-32-core": "ubuntu-latest",
    "windows-latest-32-core": "windows-latest",
    "windows-latest-32-arm-core": "windows-11-arm",
}


def placements(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"runner", "runs-on"}:
                yield from item if isinstance(item, list) else [item]
            else:
                yield from placements(item)
    elif isinstance(value, list):
        for item in value:
            yield from placements(item)


def test_runner_routing_preserves_os_and_architecture_without_larger_runner_access():
    exercised = False
    for path in WORKFLOWS.glob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for value in placements(workflow):
            if not any(label in str(value) for label in STANDARD):
                continue
            for arch in ("x64", "arm64"):
                context = {"inputs": {"arch": arch}, "github": {"repository": "NousResearch/hermes-agent"}}
                upstream = gha.render(value, context)
                context["github"]["repository"] = "example/integration-fork"
                fork = gha.render(value, context)
                assert upstream in STANDARD, (path.name, value, upstream)
                assert fork == STANDARD[upstream], (path.name, arch, fork)
                exercised = True
    assert exercised, "No runner routing was exercised"


def test_canary_jobs_cannot_tag_publish_or_prune_from_an_integration_fork():
    workflow = yaml.safe_load((WORKFLOWS / "canary-release.yml").read_text(encoding="utf-8"))
    context = {"github": {"repository": "example/integration-fork", "ref_name": "main",
                          "event": {"repository": {"default_branch": "main"}}},
               "needs": {"tag": {"result": "success"}}, "__status__": {"always": True}}
    for name in ("tag", "prune"):
        assert not gha.condition(workflow["jobs"][name]["if"], context), name
        context["github"]["repository"] = "NousResearch/hermes-agent"
        assert gha.condition(workflow["jobs"][name]["if"], context), name
        context["github"]["repository"] = "example/integration-fork"
    context["github"].update(repository="NousResearch/hermes-agent", ref_name="feature")
    assert not gha.condition(workflow["jobs"]["tag"]["if"], context)


def test_fork_worker_limits_fit_standard_runners_without_dropping_checks():
    os_workflow = yaml.safe_load((WORKFLOWS / "tests-os.yml").read_text(encoding="utf-8"))
    js_workflow = yaml.safe_load((WORKFLOWS / "js-tests.yml").read_text(encoding="utf-8"))
    os_step = next(step for step in os_workflow["jobs"]["os-tests"]["steps"]
                   if "HERMES_TEST_WORKERS" in step.get("env", {}))
    js_step = next(step for step in js_workflow["jobs"]["check"]["steps"]
                   if "run-workspace-checks.mjs" in step.get("run", ""))
    for repository, workers, concurrency in [("example/fork", "2", "1"),
                                              ("NousResearch/hermes-agent", "16", "32")]:
        for arch in ("X64", "ARM64"):
            context = {"github": {"repository": repository}, "matrix": {"marker": "windows"},
                       "runner": {"arch": arch}}
            assert str(gha.render(os_step["env"]["HERMES_TEST_WORKERS"], context)) == workers
            assert gha.render(js_step["run"], context).split() == [
                "node", ".github/scripts/run-workspace-checks.mjs", "--concurrency", concurrency]


def test_windows_sdk_covers_distinct_native_x64_and_arm64_hosts():
    workflow = yaml.safe_load((WORKFLOWS / "windows-bundle-sdk.yml").read_text(encoding="utf-8"))
    runners = workflow["jobs"]["windows-bundle-tools"]["strategy"]["matrix"]["runner"]
    for repository, expected in [("example/fork", {"windows-latest", "windows-11-arm"}),
                                  ("NousResearch/hermes-agent", {"windows-latest-32-core", "windows-latest-32-arm-core"})]:
        assert {gha.render(value, {"github": {"repository": repository}}) for value in runners} == expected


def test_linux_fork_slices_cover_the_suite_without_overloading_workers():
    import tempfile

    from scripts.run_tests_parallel import _slice_files

    job = yaml.safe_load((WORKFLOWS / "tests.yml").read_text(encoding="utf-8"))["jobs"]["test"]
    step = next(step for step in job["steps"] if "HERMES_TEST_SLICE" in step.get("env", {}))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        files = [root / f"test_fixture_{i}.py" for i in range(40)]
        for file in files:
            file.write_text("def test_example(): pass\n", encoding="utf-8")
        for repository, total, workers in [("example/fork", 8, "4"),
                                           ("NousResearch/hermes-agent", 2, "32")]:
            context = {"github": {"repository": repository}}
            slices = gha.render(job["strategy"]["matrix"]["slice"], context)
            assert slices == list(range(1, total + 1))
            assert str(gha.render(step["env"]["HERMES_TEST_WORKERS"], context)) == workers
            selected = []
            for index in slices:
                context["matrix"] = {"slice": index}
                # Force mixed-template interpolation rather than whole-value evaluation.
                spec = gha.render("slice=" + step["env"]["HERMES_TEST_SLICE"], context).removeprefix("slice=")
                assert spec == f"{index}/{total}"
                selected.extend(_slice_files(files, index, total, {}, root))
            assert len(selected) == len(files)
            assert set(selected) == set(files)
