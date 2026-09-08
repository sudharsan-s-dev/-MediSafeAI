import sys
import unittest
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.report import ReportGenerator

SAMPLE_PATIENT = {
    'name': 'Ramaswamy K.',
    'age': 72,
    'sex': 'Male',
    'allergies': 'Penicillin, Sulfa drugs',
    'conditions': 'Hypertension, T2DM',
    'patient_id': 'MED-001',
}

HIGH_RISK_MEDS = [
    'Tab Telma 40mg OD',
    'Tab Glycomet 500mg BD PC',
    'Tab Atorva 10mg HS',
    'Tab Warfarin 2mg OD',
    'Tab Aspirin 75mg OD PC',
    'Tab Ciprofloxacin 500mg BD',
    'Tab Amlodipine 5mg OD',
]

SAFETY_RESULT_MOCK = {
    'drug_interactions': [
        {
            'drug_a': 'Warfarin',
            'drug_b': 'Aspirin',
            'severity': 'CRITICAL',
            'description': 'Increased bleeding risk',
            'clinical_effect': 'Major haemorrhage',
            'recommendation': 'Avoid concurrent use',
        }
    ],
    'allergy_alerts': [],
    'dose_limit_alerts': [],
}

RECONCILE_MOCK = {
    'changes': [
        {'category': 'SAME', 'medicine_name': 'Telma', 'generic_name': 'telmisartan',
         'old_entry': {'strength': '40', 'unit': 'mg', 'frequency': 'OD'},
         'new_entry': {'strength': '40', 'unit': 'mg', 'frequency': 'OD'}},
        {'category': 'NEW', 'medicine_name': 'Warfarin', 'generic_name': 'warfarin',
         'old_entry': None,
         'new_entry': {'strength': '2', 'unit': 'mg', 'frequency': 'OD'}},
        {'category': 'DISCONTINUED', 'medicine_name': 'Dolo', 'generic_name': 'paracetamol',
         'old_entry': {'strength': '650', 'unit': 'mg', 'frequency': 'SOS'},
         'new_entry': None},
    ],
    'old_label': 'Previous Regimen',
    'new_label': 'Current Regimen',
}


class TestReportGenerator(unittest.TestCase):

    def setUp(self):
        self.gen = ReportGenerator()

    # ── Header ──────────────────────────────────────────────────────────────
    def test_header_fields(self):
        report = self.gen.generate_report(patient_info=SAMPLE_PATIENT)
        header = report['header']
        self.assertEqual(header['patient_name'], 'Ramaswamy K.')
        self.assertEqual(header['patient_age'], 72)
        self.assertEqual(header['patient_sex'], 'Male')
        self.assertIn('Penicillin', header['allergies'])

    # ── Safety panel — no data ───────────────────────────────────────────────
    def test_safety_panel_no_data_returns_safe(self):
        report = self.gen.generate_report(patient_info=SAMPLE_PATIENT)
        self.assertTrue(report['safety_panel']['is_safe'])
        self.assertEqual(report['safety_panel']['total_alerts'], 0)

    # ── Safety panel — with mock safety result ───────────────────────────────
    def test_safety_panel_with_critical_ddi(self):
        report = self.gen.generate_report(
            patient_info=SAMPLE_PATIENT,
            safety_result=SAFETY_RESULT_MOCK,
        )
        panel = report['safety_panel']
        self.assertFalse(panel['is_safe'])
        self.assertEqual(panel['critical_count'], 1)
        self.assertEqual(panel['overall_severity'], 'CRITICAL')

    # ── Reconciliation summary ────────────────────────────────────────────────
    def test_reconciliation_summary_counts(self):
        report = self.gen.generate_report(
            patient_info=SAMPLE_PATIENT,
            reconciliation_result=RECONCILE_MOCK,
        )
        summary = report['reconciliation_summary']
        self.assertTrue(summary['available'])
        self.assertEqual(summary['counts'].get('SAME'), 1)
        self.assertEqual(summary['counts'].get('NEW'), 1)
        self.assertEqual(summary['counts'].get('DISCONTINUED'), 1)
        self.assertTrue(summary['has_high_risk_changes'])

    # ── Recommendations — Warfarin+Aspirin trigger ────────────────────────────
    def test_recommendations_warfarin_aspirin(self):
        report = self.gen.generate_report(
            patient_info=SAMPLE_PATIENT,
            medicines_list=['Tab Warfarin 2mg OD', 'Tab Aspirin 75mg OD'],
        )
        recs = report['recommendations']
        texts = ' '.join(r['text'] for r in recs).lower()
        self.assertIn('anticoagulant', texts)

    # ── Recommendations — polypharmacy trigger (5+ drugs) ────────────────────
    def test_recommendations_polypharmacy(self):
        report = self.gen.generate_report(
            patient_info=SAMPLE_PATIENT,
            medicines_list=HIGH_RISK_MEDS,
        )
        recs = report['recommendations']
        texts = ' '.join(r['text'] for r in recs).lower()
        self.assertIn('polypharmacy', texts)

    # ── Risk score — critical safety → high score ──────────────────────────
    def test_risk_score_critical_safety(self):
        report = self.gen.generate_report(
            patient_info=SAMPLE_PATIENT,
            safety_result=SAFETY_RESULT_MOCK,
        )
        self.assertGreaterEqual(report['risk_score']['score'], 30)
        self.assertIn(report['risk_score']['level'], ('CRITICAL', 'HIGH', 'MODERATE'))

    # ── Risk score — no alerts → low ─────────────────────────────────────────
    def test_risk_score_safe_default(self):
        report = self.gen.generate_report(patient_info=SAMPLE_PATIENT)
        self.assertLessEqual(report['risk_score']['score'], 20)

    # ── Adherence chart demo mode ─────────────────────────────────────────────
    def test_adherence_chart_demo_mode(self):
        report = self.gen.generate_report(patient_info=SAMPLE_PATIENT)
        chart = report['adherence_chart']
        self.assertTrue(chart['is_demo'])
        self.assertEqual(len(chart['days']), 7)
        self.assertIn('average_rate', chart)

    # ── Disclaimer is present ─────────────────────────────────────────────────
    def test_disclaimer_present(self):
        report = self.gen.generate_report(patient_info=SAMPLE_PATIENT)
        self.assertIn('DECISION SUPPORT ONLY', report['disclaimer'])
        self.assertIn('physician or pharmacist', report['disclaimer'])

    # ── Duration pluralization fix (days→days) ────────────────────────────────
    def test_report_keys_present(self):
        report = self.gen.generate_report(patient_info=SAMPLE_PATIENT)
        required_keys = [
            'header', 'reconciliation_summary', 'safety_panel',
            'schedule_table', 'adherence_chart', 'recommendations',
            'risk_score', 'generated_at', 'report_date', 'disclaimer',
        ]
        for key in required_keys:
            self.assertIn(key, report, f"Missing key: {key}")


if __name__ == '__main__':
    unittest.main()
