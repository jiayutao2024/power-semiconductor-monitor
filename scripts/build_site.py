#!/usr/bin/env python3
"""Build the zero-CDN static site and documented public JSON endpoints."""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path
from typing import Any

def read_json(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--root",default=".");args=parser.parse_args();root=Path(args.root).resolve();data=read_json(root/"data"/"latest.json");site=root/"_site"
    if site.exists(): shutil.rmtree(site)
    site.mkdir(parents=True)
    for name in ("index.html","styles.css","app.js"): shutil.copy2(root/"web"/name,site/name)
    (site/".nojekyll").write_text("",encoding="utf-8");api=site/"api";obs=data["observations"]
    demand_ids={"nev_output_yoy","solar_capacity_yoy","industrial_equip_yoy"}
    endpoints={
      "dashboard.json":data,
      "power-overview.json":{"meta":data["meta"],"cycle":data["cycle"],"health":data["health"],"latest_verified_events":[x for x in data["events"] if str(x.get("status","")).startswith("verified")][:8]},
      "power-prices.json":{"meta":data["meta"],"public_proxies":data["price_proxies"],"sku":data["sku"],"price_events":[x for x in data["events"] if "价格" in x.get("event_types",[])]},
      "power-supply.json":{"meta":data["meta"],"supply_tightness":data["cycle"]["supply_tightness"],"public_proxies":data["price_proxies"],"sku":data["sku"]},
      "power-demand.json":{"meta":data["meta"],"demand_breadth":data["cycle"]["demand_breadth"],"demand_strength":data["cycle"]["demand_strength"],"observations":[x for x in obs if x.get("metric_id") in demand_ids]},
      "power-materials.json":{"meta":data["meta"],"taxonomy":{"materials":["Silicon","SiC","GaN"],"chain":["粉料","衬底","外延","晶圆","器件","模块","系统"]},"companies":data["companies"]},
      "power-companies.json":{"meta":data["meta"],"companies":data["companies"],"financial_observations":[x for x in obs if x.get("company")]},
      "power-market.json":{"meta":data["meta"],"rows":data["market"],"indices":data["market_indices"]},
      "power-events.json":{"meta":data["meta"],"rows":data["events"],"status_definitions":{"verified":"原文已核验","pending":"二级来源待原文","discovery":"自动发现线索"}},
      "power-sources.json":{"meta":data["meta"],"rows":data["sources"]},"power-health.json":data["health"]}
    for name,value in endpoints.items():write_json(api/name,value)
    catalog={"name":data["meta"]["title"],"version":data["meta"]["version"],"generated_at":data["meta"]["generated_at"],"timezone":data["meta"]["timezone"],"refresh":data["meta"]["schedule"],"endpoints":[{"path":f"/api/{name}","description":name.removeprefix("power-").removesuffix(".json")} for name in endpoints]+[{"path":"/api/index.json","description":"接口目录"}]}
    write_json(api/"index.json",catalog);print(site);return 0
if __name__=="__main__":raise SystemExit(main())
