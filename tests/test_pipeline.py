import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_data", ROOT / "scripts" / "update_data.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class PipelineTests(unittest.TestCase):
    def test_pct_change(self):
        self.assertEqual(MOD.pct_change([100, 110], 1), 10.0)
        self.assertIsNone(MOD.pct_change([100], 1))

    def test_demand_signal_boundaries(self):
        self.assertEqual(MOD.demand_signal(15), 3)
        self.assertEqual(MOD.demand_signal(1), 2)
        self.assertEqual(MOD.demand_signal(0), 1)
        self.assertEqual(MOD.demand_signal(-1), 0)

    def test_stage_refuses_missing_supply_and_profit(self):
        defs = json.loads((ROOT / "config" / "metrics.json").read_text(encoding="utf-8"))
        observations = json.loads((ROOT / "data" / "manual_metrics.json").read_text(encoding="utf-8"))["observations"]
        cycle = MOD.calculate_cycle(observations, [], defs)
        self.assertFalse(cycle["sufficient"])
        self.assertEqual(cycle["label"], "证据积累期")

    def test_company_symbols_unique(self):
        data = json.loads((ROOT / "config" / "companies.json").read_text(encoding="utf-8"))
        symbols = [x["symbol"] for group in ("domestic", "overseas", "benchmarks") for x in data[group]]
        self.assertEqual(len(symbols), len(set(symbols)))


if __name__ == "__main__":
    unittest.main()
