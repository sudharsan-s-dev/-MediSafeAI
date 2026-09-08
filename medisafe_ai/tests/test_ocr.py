import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ocr import PrescriptionOCREngine


class TestOCREngine(unittest.TestCase):

    def setUp(self):
        self.engine = PrescriptionOCREngine()

    # ── Brand catalog loading ──────────────────────────────────────────────
    def test_brand_catalog_loaded(self):
        """Brand catalog must have at least 10 entries."""
        self.assertGreater(len(self.engine.brand_catalog), 10,
                           "Brand catalog should have many entries")

    # ── Strength parsing ───────────────────────────────────────────────────
    def test_parse_strength_mg(self):
        strength, unit = self.engine._parse_strength("Tab. Metformin 500mg BD")
        self.assertEqual(strength, "500")
        self.assertEqual(unit, "mg")

    def test_parse_strength_mcg(self):
        strength, unit = self.engine._parse_strength("Thyroxine 25mcg OD")
        self.assertEqual(strength, "25")
        self.assertEqual(unit, "mcg")

    def test_parse_strength_none(self):
        strength, unit = self.engine._parse_strength("Take with water")
        self.assertIsNone(strength)
        self.assertIsNone(unit)

    # ── Frequency parsing ─────────────────────────────────────────────────
    def test_parse_frequency_bd(self):
        freq, label = self.engine._parse_frequency("Tab Metformin 500mg BD after meals")
        self.assertEqual(freq, "twice daily")
        self.assertIn("Morning", label)

    def test_parse_frequency_od(self):
        freq, label = self.engine._parse_frequency("Tab Atorvastatin 20mg OD HS")
        self.assertEqual(freq, "once daily")

    def test_parse_frequency_tds(self):
        freq, label = self.engine._parse_frequency("Amoxicillin 250mg TDS")
        self.assertEqual(freq, "thrice daily")

    def test_parse_frequency_sos(self):
        freq, label = self.engine._parse_frequency("Tab Dolo 650mg SOS")
        self.assertEqual(freq, "as needed")

    # ── Duration parsing ──────────────────────────────────────────────────
    def test_parse_duration_days(self):
        duration = self.engine._parse_duration("Amoxicillin 500mg TDS x 7 days")
        self.assertEqual(duration, "7 days")

    def test_parse_duration_weeks(self):
        duration = self.engine._parse_duration("Tab Prednisolone 10mg OD 2 weeks")
        self.assertEqual(duration, "2 weeks")

    # ── Timing parsing ────────────────────────────────────────────────────
    def test_parse_timing_ac(self):
        timing = self.engine._parse_timing("Tab Glimepiride 2mg OD AC")
        self.assertEqual(timing, "before meals")

    def test_parse_timing_pc(self):
        timing = self.engine._parse_timing("Tab Metformin 500mg BD PC")
        self.assertEqual(timing, "after meals")

    # ── Line parsing heuristics ───────────────────────────────────────────
    def test_parse_lines_recognises_drug(self):
        lines = [
            "DISCHARGE SUMMARY",
            "Tab. Metformin 500mg BD PC",
            "Patient: Ramaswamy K. Age: 72",
        ]
        results = self.engine.parse_lines(lines)
        brands = [r['extracted_brand'] for r in results]
        self.assertTrue(any("Metformin" in b or "metformin" in b.lower() for b in brands),
                        f"Metformin not found in parsed results: {results}")

    def test_parse_lines_filters_noise(self):
        lines = [
            "DATE: 01-Sep-2026",
            "Doctor: Dr. Rajesh Kumar",
            "Rx",
            "Tab. Amlodipine 5mg OD",
        ]
        results = self.engine.parse_lines(lines)
        # Only the Amlodipine line should survive noise filtering
        self.assertLessEqual(len(results), 2)

    def test_parse_lines_requires_review_flag(self):
        lines = ["X 100mg"]  # no drug match -> confidence 0
        results = self.engine.parse_lines(lines)
        if results:
            self.assertTrue(results[0]['requires_review'])

    # ── Sample extractions ────────────────────────────────────────────────
    def test_sample_cardiac_clinic(self):
        result = self.engine.extract_from_sample("sample_cardiac_clinic")
        self.assertIn('medicines', result)
        self.assertGreater(len(result['medicines']), 0)
        brands = [m['extracted_brand'] for m in result['medicines']]
        self.assertIn("Amlodipine", brands)
        self.assertIn("Warfarin", brands)

    def test_sample_discharge_order(self):
        result = self.engine.extract_from_sample("sample_discharge_order")
        self.assertIn('medicines', result)
        self.assertGreater(len(result['medicines']), 0)
        brands = [m['extracted_brand'] for m in result['medicines']]
        self.assertIn("Aspirin", brands)
        self.assertIn("Ciprofloxacin", brands)

    def test_sample_unknown_returns_empty(self):
        result = self.engine.extract_from_sample("nonexistent_sample")
        self.assertEqual(result, {})

    def test_get_sample_list(self):
        samples = self.engine.get_sample_list()
        self.assertEqual(len(samples), 2)
        ids = [s['id'] for s in samples]
        self.assertIn('sample_cardiac_clinic', ids)
        self.assertIn('sample_discharge_order', ids)

    # ── Tesseract fallback ────────────────────────────────────────────────
    def test_extract_text_returns_list(self):
        """extract_text must always return a list (empty if Tesseract absent)."""
        result = self.engine.extract_text("nonexistent_image.png")
        self.assertIsInstance(result, list)


if __name__ == '__main__':
    unittest.main()
