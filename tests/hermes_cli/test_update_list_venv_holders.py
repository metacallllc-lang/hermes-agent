"""``hermes update --list-venv-holders``: read-only JSON twin of the Windows venv-holder refusal.

Drives ``cmd_update`` (the production entry point) so the wiring in ``_update_preflight_handled``
is what is proven, not the helper alone.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from hermes_cli import main as cli_main
from hermes_cli import update_cmd_windows


def _args(**overrides):
    base = dict(list_venv_holders=True, plan=False, check=False, gateway=False, branch=None)
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.fixture
def _quiet_preflight(monkeypatch):
    monkeypatch.setattr("hermes_cli.config.is_managed", lambda: False)
    # No live psutil lookups: the fixture tuple IS the process table.
    monkeypatch.setattr(update_cmd_windows, "_psutil", lambda: None)


def test_list_venv_holders_json_and_exit_3_when_holders_present(monkeypatch, capsys, _quiet_preflight):
    holders = [
        (4242, "python.exe", r"C:\hermes\venv\Scripts\python.exe -m hermes_cli.main serve --port 8642"),
        (4343, "python.exe", r"C:\hermes\venv\Scripts\python.exe -m hermes_cli.main gateway run"),
        (4444, "python.exe", r"C:\hermes\venv\Scripts\python.exe -m hermes_cli.main -p work kanban list"),
        (4545, "python.exe", r"C:\hermes\venv\Scripts\python.exe some_script.py"),
    ]
    monkeypatch.setattr(update_cmd_windows, "_detect_venv_python_processes", lambda: holders)
    assert cli_main._detect_venv_python_processes() == []  # frozen old-updater shim stays inert

    with pytest.raises(SystemExit) as exc:
        cli_main.cmd_update(_args())

    assert exc.value.code == update_cmd_windows.VENV_HOLDERS_EXIT == 3
    payload = json.loads(capsys.readouterr().out)
    assert [(h["pid"], h["kind"]) for h in payload] == [
        (4242, "backend"), (4343, "gateway"), (4444, "hermes:kanban"), (4545, "python")]
    assert set(payload[0]) == {"pid", "exe", "argv", "kind"}
    assert payload[0]["argv"].endswith("serve --port 8642")


def test_list_venv_holders_empty_list_exits_zero_without_updating(monkeypatch, capsys, _quiet_preflight):
    monkeypatch.setattr(update_cmd_windows, "_detect_venv_python_processes", list)

    def _boom(*_a, **_k):  # the mutating update body must never run behind the read-only flag
        raise AssertionError("update body ran")

    monkeypatch.setattr("hermes_cli.update_cmd._cmd_update_impl", _boom)

    assert cli_main.cmd_update(_args()) is None
    assert json.loads(capsys.readouterr().out) == []


@pytest.mark.platforms("windows")
def test_scanner_uses_this_installs_committed_pm_environment(monkeypatch, tmp_path):
    from pm.environments import install_state_dir, runtime_facts_path

    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli_main, "PROJECT_ROOT", root)
    venv = install_state_dir(root) / "environments" / "generation-one" / "venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("version = 3.14.9\n", encoding="utf-8")
    facts = runtime_facts_path(root)
    facts.write_text(json.dumps({"packages": {"venv": {"environment": str(venv)}}}), encoding="utf-8")
    exe = venv / "Scripts" / "python.exe"
    foreign = tmp_path / "other-install" / "venv" / "Scripts" / "python.exe"
    processes = [
        SimpleNamespace(info={"pid": pid, "exe": str(path), "name": "python.exe"},
                        cmdline=lambda path=path: [str(path), "-c", "import time"])
        for pid, path in ((4242, exe), (4343, foreign))
    ]
    monkeypatch.setattr(update_cmd_windows, "_psutil", lambda: SimpleNamespace(process_iter=lambda fields: processes))
    monkeypatch.setattr(update_cmd_windows, "_self_and_non_gateway_ancestor_pids", lambda _: set())

    assert [row[0] for row in update_cmd_windows._detect_venv_python_processes()] == [4242]


@pytest.mark.platforms("windows")
@pytest.mark.parametrize("selection", ["foreign", "malformed"])
def test_invalid_pm_selection_cannot_claim_an_empty_inventory(monkeypatch, tmp_path, selection):
    from pm.environments import runtime_facts_path

    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli_main, "PROJECT_ROOT", root)
    facts = runtime_facts_path(root)
    facts.parent.mkdir(parents=True)
    foreign = tmp_path / "foreign" / "venv"
    foreign.mkdir(parents=True)
    (foreign / "pyvenv.cfg").write_text("version = 3.14.9\n", encoding="utf-8")
    facts.write_text("{" if selection == "malformed" else json.dumps(
        {"packages": {"venv": {"environment": str(foreign)}}}), encoding="utf-8")
    monkeypatch.setattr(update_cmd_windows, "_psutil", lambda: SimpleNamespace())

    with pytest.raises(RuntimeError, match="dependency environment"):
        update_cmd_windows._detect_venv_python_processes()
