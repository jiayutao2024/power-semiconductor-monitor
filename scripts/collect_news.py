#!/usr/bin/env python3
"""Collect recent public news into a reviewable evidence feed."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

UA = "power-semiconductor-monitor/2.0 (public research dashboard)"


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def normalize_title(value: str) -> str:
    value = re.sub(r"\s+-\s+[^-]{2,40}$", "", value)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def classify(text: str) -> tuple[list[str], list[str], list[str]]:
    lower = text.lower(); event_types=[]; products=[]; applications=[]
    for label, terms in {"价格":["price","涨价","调价"],"供给":["capacity","supply","产能","扩产"],"产品发布":["launch","introduce","推出","发布"],"客户/合同":["contract","design win","定点","合同","合作"],"财务":["earnings","revenue","财报","收入"]}.items():
        if any(term in lower for term in terms): event_types.append(label)
    for label, terms in {"SiC":["sic","silicon carbide","碳化硅"],"GaN":["gan","gallium nitride","氮化镓"],"IGBT":["igbt"],"MOSFET":["mosfet"]}.items():
        if any(term in lower for term in terms): products.append(label)
    for label, terms in {"AI数据中心":["ai data center","ai datacenter","800v","数据中心"],"汽车":["automotive","vehicle","汽车","新能源车"],"光储":["solar","storage","光伏","储能"],"工业":["industrial","工业"]}.items():
        if any(term in lower for term in terms): applications.append(label)
    return event_types or ["产业动态"], products or ["功率器件"], applications or ["多应用"]


def tier_for(url: str, config: dict[str, Any]) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(x in host for x in config["tier1_domains"]): return "T1"
    if any(x in host for x in config["tier2_domains"]): return "T2"
    return "T3"


def collect_query(query: str, cutoff: dt.date, config: dict[str, Any]) -> list[dict[str, Any]]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q":f"{query} when:{config['lookback_days']}d","hl":"zh-CN","gl":"CN","ceid":"CN:zh-Hans"})
    request = urllib.request.Request(url, headers={"User-Agent":UA})
    with urllib.request.urlopen(request, timeout=25) as response: root = ET.fromstring(response.read())
    rows=[]
    for item in root.findall("./channel/item"):
        title=(item.findtext("title") or "").strip(); link=(item.findtext("link") or "").strip(); pub=item.findtext("pubDate") or ""
        if not title or any(term.lower() in title.lower() for term in config["exclude_terms"]): continue
        relevance_terms = ["power semiconductor","功率半导体","sic","碳化硅","gan","氮化镓","igbt","mosfet","infineon","英飞凌","onsemi","安森美","rohm","罗姆","renesas","瑞萨","wolfspeed","士兰微","扬杰科技","华润微","捷捷微电","斯达半导","东微半导","新洁能","天岳先进"]
        relevance = sum(term in title.lower() for term in relevance_terms)
        if relevance == 0: continue
        evidence_terms = ["price","涨价","调价","launch","推出","发布","product","产品","capacity","产能","扩产","contract","合同","合作","定点","validation","验证","mass production","量产","shipment","出货","revenue","收入","财报","data center","数据中心","800v","电力","power supply","收购"]
        if not any(term in title.lower() for term in evidence_terms): continue
        try: published=parsedate_to_datetime(pub).date()
        except (TypeError,ValueError): continue
        if published < cutoff: continue
        source=item.find("source"); publisher=(source.text or "Google News") if source is not None else "Google News"; source_url=source.attrib.get("url","") if source is not None else ""
        effective_url=source_url or link; types,products,apps=classify(title)
        rows.append({"id":"rss-"+hashlib.sha1(normalize_title(title).encode()).hexdigest()[:12],"title":title,"published_at":published.isoformat(),"publisher":publisher,"url":link,
                     "source_tier":tier_for(effective_url,config),"status":"discovery","evidence_stage":"新闻线索/待核验","event_types":types,"products":products,"applications":apps,"companies":[],
                     "relevance_score":relevance,"summary":"自动发现的公开新闻线索；需打开原文并交叉核验后，才可进入正式指标。"})
    return rows


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--root",default="."); args=parser.parse_args(); root=Path(args.root).resolve()
    config=read_json(root/"config"/"news_sources.json",{}); manual=read_json(root/"data"/"manual_events.json",{"rows":[]}).get("rows",[])
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date(); cutoff=today-dt.timedelta(days=config.get("lookback_days",15)); discovered=[]; failures=[]
    for query in config.get("queries",[]):
        try: discovered.extend(collect_query(query,cutoff,config))
        except Exception as exc: failures.append({"query":query,"error":type(exc).__name__})
    merged={normalize_title(x["title"]):x for x in discovered}
    for row in manual: merged[normalize_title(row["title"])]=row
    rows=sorted(merged.values(),key=lambda x:(x.get("published_at",""),x.get("status","").startswith("verified"),x.get("relevance_score",0)),reverse=True)
    write_json(root/"data"/"events.json",{"generated_at":dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),"lookback_start":cutoff.isoformat(),"rows":rows,"failures":failures})
    print(json.dumps({"rows":len(rows),"verified":sum(x.get("status","").startswith("verified") for x in rows),"failures":failures},ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
