"""
Tests for rules/recommendation_rules.py — signal scoring logic.
Covers: score calculation, signal label assignment, edge cases.
"""
import pytest
from rules.recommendation_rules import evaluate_asset, evaluate_all


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_item(**kwargs):
    """Build a minimal price item dict with sensible defaults."""
    defaults = {
        "latest_price":       100.0,
        "previous_close":     100.0,
        "daily_change_pct":   0.0,
        "weekly_change_pct":  0.0,
        "monthly_change_pct": 0.0,
        "vs_ma5_pct":         0.0,
        "vs_ma20_pct":        0.0,
        "volume_ratio":       1.0,
        "asset_type":         "etf",
    }
    defaults.update(kwargs)
    return defaults


def _make_poll(items: dict):
    return {"data": items}


# ── evaluate_asset ──────────────────────────────────────────────────────────────

class TestScoreTicker:
    def test_flat_market_score_near_zero(self):
        item = _make_item()
        result = evaluate_asset("TEST", item)
        assert -10 <= result["score"] <= 10

    def test_strong_uptrend_buy_signal(self):
        item = _make_item(
            daily_change_pct=3.5,
            weekly_change_pct=6.0,
            monthly_change_pct=12.0,
            vs_ma5_pct=4.0,
            vs_ma20_pct=8.0,
            volume_ratio=2.5,
        )
        result = evaluate_asset("TEST", item)
        assert result["signal"] in ("strong_buy", "buy")
        assert result["score"] > 0

    def test_strong_downtrend_sell_signal(self):
        item = _make_item(
            daily_change_pct=-3.5,
            weekly_change_pct=-6.0,
            monthly_change_pct=-12.0,
            vs_ma5_pct=-4.0,
            vs_ma20_pct=-8.0,
            volume_ratio=2.5,
        )
        result = evaluate_asset("TEST", item)
        assert result["signal"] in ("strong_sell", "sell")
        assert result["score"] < 0

    def test_score_is_integer_or_float(self):
        result = evaluate_asset("TEST", _make_item())
        assert isinstance(result["score"], (int, float))

    def test_result_contains_required_keys(self):
        result = evaluate_asset("TEST", _make_item())
        for key in ("score", "signal", "signal_label", "price_snapshot"):
            assert key in result, f"Missing key: {key}"

    def test_signal_label_zh(self):
        item = _make_item(daily_change_pct=4.0, weekly_change_pct=8.0, monthly_change_pct=15.0,
                          vs_ma20_pct=10.0, volume_ratio=3.0)
        result = evaluate_asset("TEST", item, lang="zh")
        assert result["signal_label"] in ("强烈买入", "买入", "持有", "卖出", "强烈卖出")

    def test_signal_label_en(self):
        item = _make_item(daily_change_pct=4.0, weekly_change_pct=8.0, monthly_change_pct=15.0,
                          vs_ma20_pct=10.0, volume_ratio=3.0)
        result = evaluate_asset("TEST", item, lang="en")
        assert result["signal_label"] in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")


# ── evaluate_all ──────────────────────────────────────────────────────────────

class TestEvaluateAll:
    def test_returns_ratings_key(self):
        poll = _make_poll({"VUAG": _make_item(), "CSP1": _make_item()})
        result = evaluate_all(poll)
        assert "ratings" in result

    def test_all_tickers_scored(self):
        poll = _make_poll({"VUAG": _make_item(), "CSP1": _make_item(), "SWDA": _make_item()})
        result = evaluate_all(poll)
        assert set(result["ratings"].keys()) == {"VUAG", "CSP1", "SWDA"}

    def test_empty_poll(self):
        poll = _make_poll({})
        result = evaluate_all(poll)
        assert result["ratings"] == {}

    def test_missing_data_key(self):
        result = evaluate_all({})
        assert "ratings" in result
        assert result["ratings"] == {}
