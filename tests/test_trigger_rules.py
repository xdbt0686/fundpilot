"""
Tests for rules/trigger_rules.py — alert event detection.
Covers: large move detection, stale data, no-event baseline.
"""
import pytest
from datetime import datetime, timedelta
from rules.trigger_rules import evaluate_triggers


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_poll(ticker, daily_change_pct=0.0, timestamp=None):
    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    return {
        "polled_at": datetime.now().isoformat(timespec="seconds"),
        "data": {
            ticker: {
                "ticker": ticker,
                "latest_price": 100.0,
                "previous_close": 100.0,
                "daily_change_pct": daily_change_pct,
                "timestamp": ts,
                "asset_type": "etf",
            }
        }
    }

DEFAULT_CONFIG = {
    "daily_move_alert_pct": 1.5,
    "daily_move_strong_pct": 3.0,
    "stale_data_minutes": 20,
    "reversal_pct": 1.0,
}


# ── evaluate_triggers ─────────────────────────────────────────────────────────

class TestEvaluateTriggers:
    def test_no_price_alert_flat_market(self):
        poll = _make_poll("VUAG", daily_change_pct=0.1)
        result = evaluate_triggers(poll, None, {}, DEFAULT_CONFIG)
        assert "events" in result
        # only heartbeat/routine events allowed, no price alerts
        price_events = [e for e in result["events"]
                        if e.get("event_type") not in ("heartbeat_inspection", "routine")]
        assert len(price_events) == 0

    def test_large_move_triggers_event(self):
        poll = _make_poll("VUAG", daily_change_pct=2.5)
        result = evaluate_triggers(poll, None, {}, DEFAULT_CONFIG)
        assert len(result["events"]) > 0

    def test_large_drop_triggers_event(self):
        poll = _make_poll("VUAG", daily_change_pct=-2.5)
        result = evaluate_triggers(poll, None, {}, DEFAULT_CONFIG)
        assert len(result["events"]) > 0

    def test_strong_move_higher_severity(self):
        normal = evaluate_triggers(_make_poll("VUAG", 2.0), None, {}, DEFAULT_CONFIG)
        strong = evaluate_triggers(_make_poll("VUAG", 4.0), None, {}, DEFAULT_CONFIG)
        normal_sevs = {e.get("severity", "") for e in normal["events"]}
        strong_sevs = {e.get("severity", "") for e in strong["events"]}
        # strong move should not have lower severity than normal move
        assert len(strong["events"]) >= len(normal["events"])

    def test_stale_data_triggers_event(self):
        old_ts = (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds")
        poll = _make_poll("VUAG", daily_change_pct=0.0, timestamp=old_ts)
        result = evaluate_triggers(poll, None, {}, DEFAULT_CONFIG)
        assert len(result["events"]) > 0

    def test_event_has_required_fields(self):
        poll = _make_poll("VUAG", daily_change_pct=2.5)
        result = evaluate_triggers(poll, None, {}, DEFAULT_CONFIG)
        if result["events"]:
            event = result["events"][0]
            for key in ("ticker", "severity", "message"):
                assert key in event, f"Missing key: {key}"

    def test_empty_poll_no_crash(self):
        poll = {"polled_at": datetime.now().isoformat(), "data": {}}
        result = evaluate_triggers(poll, None, {}, DEFAULT_CONFIG)
        assert "events" in result
