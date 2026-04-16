from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 意图标签 ──────────────────────────────────────────────────────────────────

INTENT_OVERLAP   = "overlap"
INTENT_COMPARE   = "compare"
INTENT_PORTFOLIO = "portfolio"
INTENT_ASK       = "ask"        # 通用问答（兜底）

# ── 意图关键词（fallback） ─────────────────────────────────────────────────────

_OVERLAP_PATTERNS = [
    r"重叠", r"overlap", r"重复", r"持仓.*相同", r"是否.*一样",
    r"重合", r"雷同", r"一样.*吗",
]

_COMPARE_PATTERNS = [
    r"对比", r"比较", r"compare", r"区别", r"差异", r"vs\.?",
    r"和.*哪个", r"哪个更好", r"优劣", r"更适合",
]

_PORTFOLIO_PATTERNS = [
    r"组合", r"portfolio", r"配置", r"权重", r"仓位",
    r"分散", r"整体", r"全部.*etf", r"所有.*etf", r"总体",
]

# Confidence threshold — below this the rule-based result is used instead
_MODEL_CONFIDENCE_THRESHOLD = 0.60


def _matches_any(text: str, patterns: List[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def _extract_tickers(text: str, known_tickers: List[str]) -> List[str]:
    upper = text.upper()
    return [t for t in known_tickers if t in upper]


def _rule_based_intent(question: str) -> str:
    """Pure regex fallback — returns intent string (no tickers)."""
    if _matches_any(question, _OVERLAP_PATTERNS):
        return INTENT_OVERLAP
    if _matches_any(question, _COMPARE_PATTERNS):
        return INTENT_COMPARE
    if _matches_any(question, _PORTFOLIO_PATTERNS):
        return INTENT_PORTFOLIO
    return INTENT_ASK


def classify_intent(
    question: str,
    known_tickers: Optional[List[str]] = None,
) -> Tuple[str, List[str]]:
    """
    根据用户问题判断意图，返回 (intent, mentioned_tickers)。

    策略：
      1. 优先使用 PyTorch 意图分类器（字符 n-gram MLP）
      2. 若置信度低于阈值或模型未加载，回退至规则匹配
      优先级（规则）：overlap > compare > portfolio > ask
    """
    mentioned = _extract_tickers(question, known_tickers or [])

    # ── PyTorch classifier ────────────────────────────────────────────────────
    try:
        from core.intent_classifier import get_classifier
        clf = get_classifier()
        if clf.available:
            ml_intent, confidence = clf.predict(question)
            if confidence >= _MODEL_CONFIDENCE_THRESHOLD:
                logger.debug(
                    "ML intent: %s (conf=%.2f) for %r", ml_intent, confidence, question
                )
                return ml_intent, mentioned
            logger.debug(
                "ML conf %.2f < threshold %.2f, using rule-based", confidence, _MODEL_CONFIDENCE_THRESHOLD
            )
    except Exception as exc:
        logger.debug("IntentClassifier error: %s — using rule-based", exc)

    # ── Rule-based fallback ───────────────────────────────────────────────────
    intent = _rule_based_intent(question)
    return intent, mentioned


class Router:
    """
    将用户问题路由到合适工具，预计算工具结果并以 extra_context 的形式
    注入 EventAgent，让 AI 回答时有更丰富的结构化上下文。

    用法：
        router = Router(watchlist=["VUAG", "CSP1", ...])
        route = router.route(question, current_poll)
        # route["intent"] / route["extra_context"]
    """

    def __init__(self, watchlist: List[str]) -> None:
        self.watchlist = [t.upper().strip() for t in watchlist if t.strip()]

    def route(
        self,
        question: str,
        current_poll: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        返回路由结果：
          {
            "intent":        str,
            "tickers":       List[str],   # 问题中提到的 ticker，空则用全 watchlist
            "extra_context": dict,        # 工具预计算结果，供注入 prompt
          }
        """
        intent, mentioned = classify_intent(question, self.watchlist)
        tickers = mentioned if mentioned else self.watchlist
        extra: Dict[str, Any] = {}

        if intent == INTENT_OVERLAP:
            try:
                from tools.overlap import analyze_watchlist_overlap
                extra["overlap_report"] = analyze_watchlist_overlap(tickers)
            except Exception as e:
                extra["overlap_error"] = str(e)

        elif intent == INTENT_COMPARE and len(tickers) >= 2:
            try:
                from tools.compare import compare_etfs
                extra["compare_result"] = compare_etfs(tickers[0], tickers[1], current_poll)
            except Exception as e:
                extra["compare_error"] = str(e)

        elif intent == INTENT_PORTFOLIO:
            try:
                from tools.portfolio import analyze_portfolio
                extra["portfolio_result"] = analyze_portfolio(tickers, current_poll)
            except Exception as e:
                extra["portfolio_error"] = str(e)

        return {
            "intent": intent,
            "tickers": tickers,
            "extra_context": extra,
        }
