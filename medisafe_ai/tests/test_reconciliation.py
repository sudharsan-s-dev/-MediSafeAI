# tests/test_reconciliation.py
# Unit tests for MediSafe AI Module 1: Medication Reconciliation Engine

import unittest
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.reconciliation import ReconciliationEngine

class TestReconciliationEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = ReconciliationEngine()

    def test_brand_to_generic_resolution(self):
        """Test exact and fuzzy brand resolution to canonical active ingredients."""
        # Exact brand lookup
        res_dolo = self.engine.match_brand_to_generic('Dolo 650')
        self.assertTrue(res_dolo['matched'])
        self.assertEqual(res_dolo['canonical_generic'], 'paracetamol')

        # Telma -> Telmisartan
        res_telma = self.engine.match_brand_to_generic('Tab Telma 40')
        self.assertTrue(res_telma['matched'])
        self.assertEqual(res_telma['canonical_generic'], 'telmisartan')

        # Augmentin -> Amoxicillin + Clavulanic Acid
        res_aug = self.engine.match_brand_to_generic('Augmentin 625')
        self.assertTrue(res_aug['matched'])
        self.assertEqual(res_aug['canonical_generic'], 'amoxicillin + clavulanic acid')
        self.assertTrue(res_aug['is_combination'])

        # Fuzzy match (slight typo)
        res_fuzzy = self.engine.match_brand_to_generic('Ecosprn 75')
        self.assertTrue(res_fuzzy['matched'])
        self.assertEqual(res_fuzzy['canonical_generic'], 'aspirin')

    def test_reconciliation_categories(self):
        """
        Comprehensive test covering all 5 reconciliation categories:
        SAME, CHANGED, DISCONTINUED, NEW, and DUPLICATE.
        """
        old_regimen = [
            'Tab Telma 20mg 1-0-0 (morning)',               # Will be changed to 40mg
            'Tab Glycomet 500mg 1-0-0 after food',           # Will be changed to BD
            'Tab Ecosprin 75mg 0-0-1 after food',            # Will remain SAME
            'Tab Pantocid 40mg 1-0-0 before breakfast',      # Will be DISCONTINUED
            'Tab Dolo 650mg SOS',                            # Will be brand-switched to Calpol
        ]

        new_regimen = [
            'Tab Telma 40mg 1-0-0 (morning)',               # CHANGED: dose increased
            'Tab Glycomet 500mg 1-0-1 after food',           # CHANGED: frequency increased to BD
            'Tab Ecosprin 75mg 0-0-1 after food',            # SAME
            'Tab Calpol 650mg SOS',                          # CHANGED: brand substitution
            'Tab Atorva 10mg 0-0-1 bedtime',                 # NEW: statin added
        ]

        result = self.engine.reconcile(old_regimen, new_regimen)
        summary = result['summary']

        self.assertEqual(summary['total_old_medicines'], 5)
        self.assertEqual(summary['total_new_medicines'], 5)
        self.assertEqual(summary['same_count'], 1)           # Ecosprin
        self.assertEqual(summary['changed_count'], 3)        # Telma (dose), Glycomet (freq), Dolo->Calpol (brand)
        self.assertEqual(summary['discontinued_count'], 1)   # Pantocid
        self.assertEqual(summary['new_count'], 1)            # Atorva

        # Check category specifics
        cats = {d['generic_name'].lower(): d for d in result['discrepancies']}

        # Telmisartan: Changed dose
        self.assertEqual(cats['telmisartan']['category'], 'CHANGED')
        self.assertIn('Dose increased', cats['telmisartan']['change_details']['strength_change'])

        # Metformin: Changed frequency
        self.assertEqual(cats['metformin']['category'], 'CHANGED')
        self.assertIn('Frequency changed', cats['metformin']['change_details']['frequency_change'])

        # Aspirin: Same
        self.assertEqual(cats['aspirin']['category'], 'SAME')

        # Pantoprazole: Discontinued
        self.assertEqual(cats['pantoprazole']['category'], 'DISCONTINUED')
        self.assertIn('STOP', cats['pantoprazole']['clinical_note'])

        # Atorvastatin: New
        self.assertEqual(cats['atorvastatin']['category'], 'NEW')
        self.assertIn('START NEW', cats['atorvastatin']['clinical_note'])

    def test_internal_duplicate_active_ingredient(self):
        """Test detection of duplicate active ingredients in new prescription."""
        old_regimen = ['Tab Dolo 650mg SOS']
        # Patient is prescribed both Dolo and Calpol (both Paracetamol) in new visit
        new_regimen = [
            'Tab Dolo 650mg TDS',
            'Tab Crocin 500mg BD'
        ]

        result = self.engine.reconcile(old_regimen, new_regimen)
        self.assertTrue(result['summary']['duplicate_count'] > 0)
        self.assertTrue(result['summary']['has_critical_alerts'])

        # Verify duplicate discrepancy exists
        dup_items = [d for d in result['discrepancies'] if d['category'] == 'DUPLICATE']
        self.assertTrue(len(dup_items) > 0)
        self.assertIn('CRITICAL DUPLICATE', dup_items[0]['clinical_note'])

if __name__ == '__main__':
    unittest.main()
