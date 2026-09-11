#!/usr/bin/env python3
"""Build a zero-CDN static GitHub Pages artifact and public JSON endpoints."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    payload = read_json(root / "data" / "latest.json")
    site = root / "_site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(root / "web" / name, site / name)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    api = site / "api"
    observations = payload["observations"]
    by_role = {m["id"]: m["role"] for m in payload["metrics"]}
    endpoints = {
        "dashboard.json": payload,
        "power-overview.json": {"meta": payload["meta"], "cycle": payload["cycle"], "metrics": payload["metrics"], "health": payload["health"]},
        "power-prices.json": {"meta": payload["meta"], "sku": payload["sku"], "metrics": [m for m in payload["metrics"] if m["role"] == "供给"]},
        "power-supply.json": {"meta": payload["meta"], "cycle": {"supply_tightness": payload["cycle"]["supply_tightness"], "coverage": payload["cycle"]["coverage"]["supply"]}, "sku": payload["sku"]},
        "power-demand.json": {"meta": payload["meta"], "cycle": {"demand_breadth": payload["cycle"]["demand_breadth"], "demand_strength": payload["cycle"]["demand_strength"]}, "observations": [x for x in observations if by_role.get(x["metric_id"]) == "需求"]},
        "power-materials.json": {"meta": payload["meta"], "taxonomy": {"materials": ["Silicon", "SiC", "GaN"], "chain": ["粉料", "衬底", "外延", "晶圆", "器件", "模块", "封装材料", "系统"]}, "companies": payload["companies"]},
        "power-companies.json": {"meta": payload["meta"], "companies": payload["companies"], "market": payload["market"], "financial_observations": [x for x in observations if x.get("company")]},
        "power-events.json": {"meta": payload["meta"], "rows": payload["events"], "evidence_stages": ["传闻", "官方发布/路线图", "展示/点亮", "送样", "客户验证", "合同/定点", "量产", "出货/收入"]},
        "power-sources.json": {"meta": payload["meta"], "rows": payload["sources"]},
        "power-health.json": payload["health"],
    }
    for name, value in endpoints.items():
        write_json(api / name, value)
    write_json(api / "index.json", {
        "name": payload["meta"]["title"],
        "generated_at": payload["meta"]["generated_at"],
        "timezone": payload["meta"]["timezone"],
        "refresh": payload["meta"]["schedule"],
        "endpoints": [{"path": f"/api/{name}", "description": name.replace("power-", "").replace(".json", "")} for name in endpoints] + [{"path": "/api/index.json", "description": "接口目录"}],
    })
    print(site)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
