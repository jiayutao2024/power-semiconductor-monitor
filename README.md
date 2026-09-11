# 功率半导体产业景气看板

独立、公开、可复算的功率半导体监测站。页面由 GitHub Pages 托管，GitHub Actions 每天北京时间 07:30 更新，无需本地常驻进程。

## 看板结构

1. 景气总览
2. 价格与供给
3. 下游应用
4. 技术与材料
5. 公司与财务
6. 市场与催化

## 数据原则

- 核心判断只使用公开数值或由公开数值计算的技术指标。
- 披露值、计算值、事件和研究判断分开存储。
- 单一来源失败时保留最近成功数据并标记陈旧，不用空值覆盖。
- 股票涨跌不进入产业景气得分。
- 固定 SKU 价格篮子从首次上线日起积累，历史不足时明确显示“证据积累中”。

## 本地验证（仅开发需要）

```powershell
py -3 scripts/update_data.py --root .
py -3 scripts/build_site.py --root .
py -3 -m unittest discover -s tests -v
```

线上运行不依赖本地环境，定时流程见 `.github/workflows/daily.yml`。

## 公共接口

- `/api/dashboard.json`
- `/api/power-overview.json`
- `/api/power-prices.json`
- `/api/power-supply.json`
- `/api/power-demand.json`
- `/api/power-materials.json`
- `/api/power-companies.json`
- `/api/power-events.json`
- `/api/power-health.json`
- `/api/index.json`

## 口径边界

网页仅用于产业研究与数据监测，不构成投资建议。Yahoo Finance 在本项目中只作为公开行情聚合代理；公司财务以交易所、监管文件和公司 IR 为最终核验来源。
