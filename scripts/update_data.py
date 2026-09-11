#!/usr/bin/env python3
"""Collect public observations and calculate reproducible power-semiconductor indicators."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import statistics
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

UA = "power-semiconductor-monitor/1.0 (public research dashboard; contact: jiayutao2024@users.noreply.github.com)"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d&events=history"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def fetch_json(url: str, timeout: int = 25) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def pct_change(values: list[float], sessions: int) -> float | None:
    if len(values) <= sessions or not values[-1 - sessions]:
        return None
    return round((values[-1] / values[-1 - sessions] - 1) * 100, 2)


def fetch_market(row: dict[str, Any]) -> dict[str, Any]:
    symbol = row["symbol"]
    url = YAHOO.format(symbol=urllib.parse.quote(symbol, safe=""))
    payload = fetch_json(url)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    adj = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose") or quote.get("close") or []
    points = []
    for stamp, close in zip(timestamps, adj):
        if close is None:
            continue
        points.append({"date": dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date().isoformat(), "close": round(float(close), 4)})
    closes = [x["close"] for x in points]
    meta = result.get("meta", {})
    return {
        **row,
        "price": closes[-1] if closes else None,
        "currency": meta.get("currency", ""),
        "trade_date": points[-1]["date"] if points else None,
        "return_1d": pct_change(closes, 1),
        "return_20d": pct_change(closes, 20),
        "return_60d": pct_change(closes, 60),
        "history": points,
        "source_name": "Yahoo Finance（公开行情聚合代理）",
        "source_url": f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol, safe='')}/",
        "source_tier": "T3",
        "status": "ok" if points else "missing",
    }


def demand_signal(value: float) -> int:
    """Transparent direction score; this is not a forecast or percentile."""
    if value >= 15:
        return 3
    if value > 0:
        return 2
    if value == 0:
        return 1
    return 0


def calculate_cycle(observations: list[dict[str, Any]], market: list[dict[str, Any]], metric_defs: dict[str, Any]) -> dict[str, Any]:
    demand_ids = {"nev_output_yoy", "solar_capacity_yoy", "industrial_equip_yoy"}
    demand = [x for x in observations if x.get("metric_id") in demand_ids and isinstance(x.get("value"), (int, float))]
    demand_components = [
        {"metric_id": x["metric_id"], "value": x["value"], "direction_points": demand_signal(float(x["value"])), "period": x["period"]}
        for x in demand
    ]
    demand_breadth = round(sum(float(x["value"]) > 0 for x in demand) / len(demand) * 100, 1) if demand else None
    demand_strength = round(sum(x["direction_points"] for x in demand_components) / (3 * len(demand_components)) * 100, 1) if demand_components else None

    valid_market = [x for x in market if x.get("return_20d") is not None and x.get("kind") != "benchmark"]
    positive_market = sum(x["return_20d"] > 0 for x in valid_market)
    market_breadth = round(positive_market / len(valid_market) * 100, 1) if valid_market else None

    rules = metric_defs["rules"]
    supply_coverage = 0  # SKU observations must accumulate; no proxy substitution.
    demand_coverage = len(demand_components)
    profit_coverage = 0  # Requires at least two comparable quarterly observations per company.
    sufficient = supply_coverage >= rules["stage_min_supply"] and demand_coverage >= rules["stage_min_demand"] and profit_coverage >= rules["stage_min_profit"]
    return {
        "label": "证据积累期" if not sufficient else "待计算",
        "sufficient": sufficient,
        "reason": "固定SKU供给历史与可比季度财务序列尚未达到最低覆盖，不输出伪精确产业阶段。" if not sufficient else "覆盖门槛已满足。",
        "supply_tightness": None,
        "demand_breadth": demand_breadth,
        "demand_strength": demand_strength,
        "profit_confirmation": None,
        "market_breadth_20d": market_breadth,
        "coverage": {"supply": supply_coverage, "demand": demand_coverage, "profit": profit_coverage},
        "thresholds": rules,
        "demand_components": demand_components,
    }


def calculate_relative_returns(rows: list[dict[str, Any]]) -> None:
    by_symbol = {x["symbol"]: x for x in rows}
    domestic_benchmark = by_symbol.get("000300.SS", {})
    overseas_benchmark = by_symbol.get("^SOX", {})
    for row in rows:
        if row.get("kind") == "benchmark" or row.get("return_20d") is None:
            row["relative_return_20d"] = None
            continue
        benchmark = domestic_benchmark if row.get("region") == "A股" else overseas_benchmark
        bench_return = benchmark.get("return_20d")
        row["relative_return_20d"] = round(row["return_20d"] - bench_return, 2) if bench_return is not None else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    companies = read_json(root / "config" / "companies.json", {})
    metric_defs = read_json(root / "config" / "metrics.json", {})
    sku = read_json(root / "config" / "sku_basket.json", {})
    sources = read_json(root / "config" / "sources.json", {})
    manual = read_json(root / "data" / "manual_metrics.json", {})
    generated = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")

    jobs = []
    for row in companies.get("domestic", []):
        jobs.append({**row, "region": "A股", "kind": "company"})
    for row in companies.get("overseas", []):
        jobs.append({**row, "region": "海外", "kind": "company"})
    for row in companies.get("benchmarks", []):
        jobs.append({**row, "region": "基准", "kind": "benchmark"})

    market: list[dict[str, Any]] = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        future_map = {pool.submit(fetch_market, row): row for row in jobs}
        for future in concurrent.futures.as_completed(future_map):
            row = future_map[future]
            try:
                market.append(future.result())
            except Exception as exc:  # preserve partial dashboard instead of aborting all sources
                failures.append({"source": "market", "symbol": row["symbol"], "error": type(exc).__name__})
                market.append({**row, "price": None, "return_1d": None, "return_20d": None, "return_60d": None, "relative_return_20d": None, "history": [], "status": "failed", "source_tier": "T3"})
    order = {row["symbol"]: i for i, row in enumerate(jobs)}
    market.sort(key=lambda x: order[x["symbol"]])
    calculate_relative_returns(market)

    observations = manual.get("observations", [])
    cycle = calculate_cycle(observations, market, metric_defs)
    price_rows = sku.get("rows", [])
    health = {
        "generated_at": generated,
        "status": "partial" if failures or not cycle["sufficient"] else "ok",
        "market_success": sum(x.get("status") == "ok" for x in market),
        "market_total": len(market),
        "source_failures": failures,
        "stale_metrics": [],
        "sku_observed": len(price_rows),
        "sku_target": sku.get("target_count", 0),
    }
    payload = {
        "meta": {
            "title": "功率半导体产业景气与投资线索跟踪",
            "subtitle": "价格 × 供给 × 下游需求 × 技术材料 × 财务验证",
            "generated_at": generated,
            "timezone": "Asia/Shanghai",
            "schedule": "每日 07:30（北京时间）",
            "build_status": "complete",
        },
        "cycle": cycle,
        "metrics": metric_defs["metrics"],
        "observations": observations,
        "sku": sku,
        "market": market,
        "companies": companies,
        "sources": sources.get("sources", []),
        "events": [],
        "health": health,
        "methodology": {
            "chain": ["终端需求", "订单/排产", "库存/稼动率", "有效供给", "价格/交期", "收入/毛利", "Capex", "市场预期"],
            "stages": ["去库存", "需求复苏", "供需趋紧/价格上涨", "盈利兑现/主升扩散", "扩产加速/见顶风险"],
            "note": "股票表现只衡量市场预期，不进入产业景气得分。",
        },
    }
    write_json(root / "data" / "latest.json", payload)
    print(json.dumps({"generated_at": generated, "market": f"{health['market_success']}/{health['market_total']}", "stage": cycle["label"], "failures": failures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
