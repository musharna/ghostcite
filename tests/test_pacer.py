from __future__ import annotations

import pytest

from ghostcite._pace import _Pacer


@pytest.fixture
def fake_clock(monkeypatch):
    """Drive _Pacer's clock + sleep deterministically; never real-sleep.

    Returns a controller exposing the current time and the list of sleep
    durations the pacer requested. sleep() advances the fake clock so the
    pacer sees time passing exactly as if it had slept.
    """

    state = {"now": 1000.0, "slept": []}

    def monotonic():
        return state["now"]

    def sleep(secs):
        state["slept"].append(secs)
        state["now"] += secs

    monkeypatch.setattr("ghostcite._pace.time.monotonic", monotonic)
    monkeypatch.setattr("ghostcite._pace.time.sleep", sleep)

    class Ctl:
        slept = state["slept"]

        @staticmethod
        def advance(secs):
            state["now"] += secs

    return Ctl


def test_first_call_does_not_sleep(fake_clock):
    p = _Pacer(2.0)
    p.wait()
    assert fake_clock.slept == []


def test_rps_two_second_call_sleeps_half(fake_clock):
    p = _Pacer(2.0)
    p.wait()  # primes _last, no sleep
    p.wait()  # immediately after → must wait the full 0.5s
    assert fake_clock.slept == [pytest.approx(0.5)]


def test_headers_five_per_one_second_sets_interval(fake_clock):
    p = _Pacer(None)
    p.update_from_headers({"x-rate-limit-limit": "5", "x-rate-limit-interval": "1s"})
    assert p._min_interval == pytest.approx(0.2)


def test_explicit_max_rps_wins_over_server_when_more_conservative(fake_clock):
    # --max-rps 1 → 1.0s floor; server says 5/1s → 0.2s. More conservative wins.
    p = _Pacer(1.0)
    p.update_from_headers({"x-rate-limit-limit": "5", "x-rate-limit-interval": "1s"})
    assert p._min_interval == pytest.approx(1.0)


def test_malformed_interval_does_not_crash_or_change(fake_clock):
    p = _Pacer(None)
    p.update_from_headers({"x-rate-limit-limit": "5", "x-rate-limit-interval": "banana"})
    assert p._min_interval == 0.0


def test_missing_headers_unchanged(fake_clock):
    p = _Pacer(3.0)
    before = p._min_interval
    p.update_from_headers({})
    assert p._min_interval == before


def test_zero_limit_skipped(fake_clock):
    p = _Pacer(None)
    p.update_from_headers({"x-rate-limit-limit": "0", "x-rate-limit-interval": "1s"})
    assert p._min_interval == 0.0


def test_no_sleep_when_enough_time_elapsed(fake_clock):
    p = _Pacer(2.0)
    p.wait()
    fake_clock.advance(1.0)  # more than the 0.5 interval has passed
    p.wait()
    assert fake_clock.slept == []


def test_none_max_rps_no_floor(fake_clock):
    p = _Pacer(None)
    p.wait()
    p.wait()
    assert fake_clock.slept == []
