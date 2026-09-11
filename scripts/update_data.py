#!/usr/bin/env python3
"""Collect public time series and calculate auditable power-semiconductor indicators."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import io
import json
import statistics
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

UA = "power-semiconductor-monitor/2.0 (public research dashboard; github.com/jiayutao2024)"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3y&interval=1d&events=history"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
FRED_SERIES = [
    {"id":"PCU334413334413A","name":"美国其他半导体器件PPI","short_name":"功率器件价格代理","definition":"美国生产者价格指数：其他半导体器件（含晶体管、二极管及晶圆等零部件）","source_url":"https://fred.stlouisfed.org/series/PCU334413334413A"},
    {"id":"PCU334413334413","name":"美国半导体相关器件制造PPI","short_name":"半导体器件价格代理","definition":"美国生产者价格指数：半导体及相关器件制造","source_url":"https://fred.stlouisfed.org/series/PCU334413334413"},
]


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def fetch_text(url: str, timeout: int = 35) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def fetch_json(url: str, timeout: int = 35) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def pct_change(values: list[float], sessions: int) -> float | None:
    if len(values) <= sessions or not values[-1 - sessions]: return None
    return round((values[-1] / values[-1 - sessions] - 1) * 100, 2)


def percentile_rank(values: list[float]) -> float | None:
    if not values: return None
    return round(sum(v <= values[-1] for v in values) / len(values) * 100, 1)


def fetch_market(row: dict[str, Any]) -> dict[str, Any]:
    symbol = row["symbol"]
    result = fetch_json(YAHOO.format(symbol=urllib.parse.quote(symbol, safe="")))["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    adj = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose") or quote.get("close") or []
    points = [{"date":dt.datetime.fromtimestamp(t,dt.timezone.utc).date().isoformat(),"close":round(float(c),4)} for t,c in zip(timestamps,adj) if c is not None]
    closes = [x["close"] for x in points]; meta = result.get("meta", {})
    return {**row,"price":closes[-1] if closes else None,"currency":meta.get("currency",""),"trade_date":points[-1]["date"] if points else None,
            "return_1d":pct_change(closes,1),"return_20d":pct_change(closes,20),"return_60d":pct_change(closes,60),"return_250d":pct_change(closes,250),
            "history":points,"source_name":"Yahoo Finance（公开行情聚合代理）","source_url":f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol,safe='')}/","source_tier":"T3","status":"ok" if points else "missing"}


def fetch_fred(definition: dict[str, str]) -> dict[str, Any]:
    text = fetch_text(FRED.format(series=definition["id"])); rows = []
    for row in csv.DictReader(io.StringIO(text)):
        raw = row.get(definition["id"])
        if raw and raw != ".": rows.append({"date":row.get("DATE") or row.get("observation_date"),"value":round(float(raw),4)})
    values = [x["value"] for x in rows]
    return {**definition,"unit":"Index","frequency":"monthly","source_name":"U.S. BLS / FRED","source_tier":"T1","status":"ok" if rows else "missing","history":rows,
            "latest":values[-1] if values else None,"period":rows[-1]["date"] if rows else None,"mom":pct_change(values,1),"change_3m":pct_change(values,3),"yoy":pct_change(values,12),
            "percentile_5y":percentile_rank(values[-60:]),"note":"公开宏观价格代理，不等同于具体功率器件料号现货价。"}


def demand_signal(value: float) -> int:
    if value >= 15: return 3
    if value > 0: return 2
    if value == 0: return 1
    return 0


def calculate_relative_returns(rows: list[dict[str, Any]]) -> None:
    by_symbol = {x["symbol"]:x for x in rows}
    for row in rows:
        benchmark = by_symbol.get("000300.SS" if row.get("region") == "A股" else "^SOX", {})
        row["relative_return_20d"] = round(row["return_20d"]-benchmark["return_20d"],2) if row.get("kind") != "benchmark" and row.get("return_20d") is not None and benchmark.get("return_20d") is not None else None


def calculate_market_index(rows: list[dict[str, Any]], region: str) -> list[dict[str, Any]]:
    members = [x for x in rows if x.get("region") == region and x.get("history")]; by_date: dict[str,list[float]] = {}
    if not members: return []
    common_start = max(x["history"][0]["date"] for x in members)
    for member in members:
        eligible = [x for x in member["history"] if x["date"] >= common_start]
        if not eligible: continue
        first = eligible[0]["close"]
        if not first: continue
        for point in eligible: by_date.setdefault(point["date"],[]).append(point["close"]/first*100)
    return [{"date":date,"value":round(statistics.fmean(vals),2),"members":len(vals)} for date,vals in sorted(by_date.items()) if len(vals) == len(members)]


def calculate_cycle(observations: list[dict[str, Any]], market: list[dict[str, Any]], metric_defs: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any]:
    demand_ids = {"nev_output_yoy","solar_capacity_yoy","industrial_equip_yoy"}; latest = {}
    for x in observations:
        if x.get("metric_id") in demand_ids and isinstance(x.get("value"),(int,float)) and (x["metric_id"] not in latest or x.get("period","") > latest[x["metric_id"]].get("period","")): latest[x["metric_id"]] = x
    demand = [{"metric_id":x["metric_id"],"value":x["value"],"direction_points":demand_signal(float(x["value"])),"period":x["period"]} for x in latest.values()]
    valid_market = [x for x in market if x.get("return_20d") is not None and x.get("kind") != "benchmark"]
    supply = [x for x in prices if x.get("status") == "ok" and x.get("change_3m") is not None]
    financial_companies = {x.get("company") for x in observations if x.get("company") and x.get("status") == "verified"}
    rules = metric_defs["rules"]; coverage = {"supply":len(supply),"demand":len(demand),"profit":len(financial_companies)}
    sufficient = coverage["supply"] >= 1 and coverage["demand"] >= rules["stage_min_demand"] and coverage["profit"] >= rules["stage_min_profit"]
    return {"label":"需求扩散、价格待验证" if sufficient else "证据积累期","sufficient":sufficient,
            "reason":"公开需求指标保持扩张，宏观价格代理已接入；固定SKU、交期和更多公司季度盈利仍需连续积累。",
            "supply_tightness":round(statistics.fmean([max(0,min(100,50+x["change_3m"]*5)) for x in supply]),1) if supply else None,
            "demand_breadth":round(sum(float(x["value"])>0 for x in demand)/len(demand)*100,1) if demand else None,
            "demand_strength":round(sum(x["direction_points"] for x in demand)/(3*len(demand))*100,1) if demand else None,
            "profit_confirmation":None,"market_breadth_20d":round(sum(x["return_20d"]>0 for x in valid_market)/len(valid_market)*100,1) if valid_market else None,
            "coverage":coverage,"thresholds":{**rules,"public_proxy_min":1},"demand_components":demand,"disclaimer":"阶段标签由公开规则生成，不是投资评级。价格代理不替代器件级报价。"}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--root",default="."); args=parser.parse_args(); root=Path(args.root).resolve()
    companies=read_json(root/"config"/"companies.json",{}); metric_defs=read_json(root/"config"/"metrics.json",{}); sku=read_json(root/"config"/"sku_basket.json",{})
    sources=read_json(root/"config"/"sources.json",{}); manual=read_json(root/"data"/"manual_metrics.json",{}); events=read_json(root/"data"/"events.json",{"rows":[]}).get("rows",[])
    generated=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    jobs=([{**x,"region":"A股","kind":"company"} for x in companies.get("domestic",[])]+[{**x,"region":"海外","kind":"company"} for x in companies.get("overseas",[])]+[{**x,"region":"基准","kind":"benchmark"} for x in companies.get("benchmarks",[])])
    market=[]; failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        pending={pool.submit(fetch_market,row):row for row in jobs}
        for future in concurrent.futures.as_completed(pending):
            row=pending[future]
            try: market.append(future.result())
            except Exception as exc:
                failures.append({"source":"market","symbol":row["symbol"],"error":type(exc).__name__}); market.append({**row,"price":None,"return_1d":None,"return_20d":None,"return_60d":None,"return_250d":None,"relative_return_20d":None,"history":[],"status":"failed","source_tier":"T3"})
    order={x["symbol"]:i for i,x in enumerate(jobs)}; market.sort(key=lambda x:order[x["symbol"]]); calculate_relative_returns(market)
    price_proxies=[]
    for definition in FRED_SERIES:
        try: price_proxies.append(fetch_fred(definition))
        except Exception as exc:
            failures.append({"source":"FRED","series":definition["id"],"error":type(exc).__name__}); price_proxies.append({**definition,"history":[],"status":"failed","source_tier":"T1"})
    observations=manual.get("observations",[]); cycle=calculate_cycle(observations,market,metric_defs,price_proxies)
    market_indices={"A股":calculate_market_index(market,"A股"),"海外":calculate_market_index(market,"海外")}
    health={"generated_at":generated,"status":"partial" if failures or not cycle["sufficient"] else "ok","market_success":sum(x.get("status")=="ok" for x in market),"market_total":len(market),
            "price_proxy_success":sum(x.get("status")=="ok" for x in price_proxies),"price_proxy_total":len(price_proxies),"event_count":len(events),"verified_events":sum(x.get("status")=="verified" for x in events),
            "source_failures":failures,"stale_metrics":[],"sku_observed":len(sku.get("rows",[])),"sku_target":sku.get("target_count",0)}
    payload={"meta":{"title":"功率半导体产业监测终端","subtitle":"周期 · 价格 · 应用 · 技术 · 公司 · 市场 · 事件","generated_at":generated,"timezone":"Asia/Shanghai","schedule":"每日 07:30（北京时间）","version":"2.0"},
             "cycle":cycle,"metrics":metric_defs["metrics"],"observations":observations,"price_proxies":price_proxies,"sku":sku,"market":market,"market_indices":market_indices,"companies":companies,"sources":sources.get("sources",[]),"events":events,"health":health,
             "methodology":{"chain":["终端需求","订单/排产","库存/稼动率","有效供给","价格/交期","收入/毛利","Capex","市场预期"],"stages":["去库存","需求复苏","供需趋紧/价格上涨","盈利兑现/主升扩散","扩产加速/见顶风险"],"principles":["事实与观点分层","产品发布不等于收入","宏观代理不冒充料号价格","市场表现不进入产业得分"]}}
    write_json(root/"data"/"latest.json",payload)
    print(json.dumps({"generated_at":generated,"market":f"{health['market_success']}/{health['market_total']}","price_proxies":f"{health['price_proxy_success']}/{health['price_proxy_total']}","events":len(events),"failures":failures},ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
