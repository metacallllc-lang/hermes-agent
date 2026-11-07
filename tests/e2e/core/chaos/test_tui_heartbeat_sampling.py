"""Heartbeat observation budgets stay consistent with the allowed RPC latency.

These data-only gates run on every host; no gateway, provider or process is started.
"""
from types import SimpleNamespace

import pytest

from tests.e2e.core.chaos.test_tui_gateway_turn_liveness import (
    HEARTBEAT_MAX_S,
    _assert_heartbeat,
    _required_heartbeats,
)


@pytest.mark.parametrize("turn_s,required", [(1.995, 1), (2.005, 1), (10.0, 3), (16.0, 5), (600.0, 5)])
def test_sample_requirement_uses_the_allowed_probe_budget(turn_s, required):
    assert _required_heartbeats(turn_s) == required
    hb = SimpleNamespace(latencies=[0.01] * required, failures=[])
    _assert_heartbeat(SimpleNamespace(id="sampling-fixture"), hb, {}, turn_s)


@pytest.mark.parametrize("latencies,failures,turn_s,accepted", [
    ([1.576, 0.009, 0.026], [], 2.005, True),
    ([], [], 1.995, False),
    ([HEARTBEAT_MAX_S], [], 2.005, False),
    ([0.01], ["RPC failed"], 2.005, False),
    ([0.01] * 4, [], 16.0, False),
])
def test_fast_turns_have_no_clock_cliff_and_unhealthy_observations_still_fail(latencies, failures, turn_s, accepted):
    hb = SimpleNamespace(latencies=latencies, failures=failures)
    if accepted:
        _assert_heartbeat(SimpleNamespace(id="sampling-fixture"), hb, {}, turn_s)
    else:
        with pytest.raises(AssertionError):
            _assert_heartbeat(SimpleNamespace(id="sampling-fixture"), hb, {}, turn_s)
