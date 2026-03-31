def normalize_etf(raw: dict) -> dict:
    if not raw:
        return {}

    return {
        "ticker": str(raw.get("ticker", "")).upper(),
        "name": raw.get("name", ""),
        "isin": raw.get("isin", ""),
        "provider": raw.get("provider", ""),
        "index_tracked": raw.get("index_tracked", ""),
        "region_scope": raw.get("region_scope", ""),
        "includes_emerging_markets": bool(raw.get("includes_emerging_markets", False)),
        "ter": float(raw.get("ter", 0)),
        "distribution_policy": raw.get("distribution_policy", ""),
        "replication_method": raw.get("replication_method", ""),
        "fund_domicile": raw.get("fund_domicile", ""),
        "fund_size_gbp_m": float(raw.get("fund_size_gbp_m", 0)),
        "core_role": raw.get("core_role", ""),
        "notes": raw.get("notes", "")
    }