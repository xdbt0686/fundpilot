"""
Tests for core/router.py — intent classification (regex fallback + ML classifier).
Covers: explicit keyword queries, paraphrased queries, cross-lingual queries,
        ticker extraction, and edge cases.
"""
import pytest
from core.router import classify_intent, _rule_based_intent


# ── Regex fallback ────────────────────────────────────────────────────────────

class TestRegexFallback:
    def test_overlap_keyword_zh(self):
        assert _rule_based_intent("VUAG和SWDA持仓重叠有多少") == "overlap"

    def test_overlap_keyword_en(self):
        assert _rule_based_intent("overlap between VUAG and CSP1") == "overlap"

    def test_compare_keyword_zh(self):
        assert _rule_based_intent("CSP1和VUAG哪个更好") == "compare"

    def test_compare_vs(self):
        assert _rule_based_intent("SWDA vs VWRP") == "compare"

    def test_portfolio_keyword_zh(self):
        assert _rule_based_intent("我的仓位配置怎么样") == "portfolio"

    def test_portfolio_keyword_en(self):
        assert _rule_based_intent("analyze my portfolio") == "portfolio"

    def test_ask_fallback(self):
        assert _rule_based_intent("今天市场怎么样") == "ask"

    def test_empty_string(self):
        assert _rule_based_intent("") == "ask"


# ── ML classifier (classify_intent) ──────────────────────────────────────────

class TestClassifyIntent:
    """These use the full pipeline (ML first, regex fallback)."""

    # --- overlap ---
    def test_overlap_explicit(self):
        intent, _ = classify_intent("VUAG和SWDA持仓重叠有多少")
        assert intent == "overlap"

    def test_overlap_paraphrase_zh(self):
        # no keyword "重叠" — ML should catch this
        intent, _ = classify_intent("帮我看看有没有买了差不多东西的ETF")
        assert intent == "overlap"

    def test_overlap_en(self):
        intent, _ = classify_intent("find duplicate stocks across my ETFs")
        assert intent == "overlap"

    # --- compare ---
    def test_compare_explicit(self):
        intent, _ = classify_intent("CSP1和VUAG哪个更好")
        assert intent == "compare"

    def test_compare_en(self):
        intent, _ = classify_intent("compare SWDA and VWRP")
        assert intent == "compare"

    def test_compare_paraphrase_zh(self):
        intent, _ = classify_intent("HMWS和VWRL差别大吗")
        assert intent == "compare"

    # --- portfolio ---
    def test_portfolio_explicit(self):
        intent, _ = classify_intent("我的仓位配置怎么样")
        assert intent == "portfolio"

    def test_portfolio_en(self):
        intent, _ = classify_intent("what does my overall allocation look like")
        assert intent == "portfolio"

    # --- ask ---
    def test_ask_general(self):
        intent, _ = classify_intent("今天市场风险多大")
        assert intent == "ask"

    def test_ask_en(self):
        intent, _ = classify_intent("is bitcoin going up today")
        assert intent == "ask"

    # --- ticker extraction ---
    def test_ticker_extraction(self):
        _, tickers = classify_intent("VUAG和CSP1重叠严重吗", known_tickers=["VUAG", "CSP1", "SWDA"])
        assert "VUAG" in tickers
        assert "CSP1" in tickers

    def test_no_ticker_mentioned(self):
        _, tickers = classify_intent("今天市场怎么样", known_tickers=["VUAG", "CSP1"])
        assert tickers == []
