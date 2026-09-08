# tests/test_safety.py
# Unit tests for MediSafe AI Module 2: Safety Checks Engine

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.safety import SafetyEngine

class TestSafetyEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.safety_engine = SafetyEngine()

    def test_ddi_detection(self):
        """Test detection of high-risk drug interaction pairs."""
        regimen = [
            'Tab Telma 40mg 1-0-0',         # Telmisartan
            'Tab Aldactone 25mg 1-0-0'      # Spironolactone
        ]
        result = self.safety_engine.evaluate_regimen(regimen)
        interactions = result['alerts']['drug_interactions']
        
        self.assertTrue(len(interactions) > 0)
        self.assertEqual(interactions[0]['severity'], 'HIGH')
        self.assertIn('Hyperkalemia', interactions[0]['category'])
        self.assertIn('High Potassium', interactions[0]['patient_warning'])

    def test_combination_drug_ddi_unpacking(self):
        """Test that combination drugs (e.g. Combiflam = Ibuprofen + Paracetamol) unpack constituent ingredients."""
        regimen = [
            'Tab Combiflam 1-0-1',          # Ibuprofen + Paracetamol
            'Tab Coumadin 2mg 0-0-1'        # Warfarin
        ]
        result = self.safety_engine.evaluate_regimen(regimen)
        interactions = result['alerts']['drug_interactions']
        
        # Should detect Ibuprofen + Warfarin major bleeding risk
        bleeding_alerts = [i for i in interactions if 'Bleeding' in i['category']]
        self.assertTrue(len(bleeding_alerts) > 0)
        self.assertEqual(bleeding_alerts[0]['severity'], 'HIGH')

    def test_allergy_screening_by_class(self):
        """Test allergy screening against drug class hierarchy (Penicillin -> Augmentin)."""
        regimen = [
            'Tab Augmentin 625mg 1-0-1',    # Amoxicillin + Clavulanic Acid
            'Tab Pantocid 40mg 1-0-0'
        ]
        result = self.safety_engine.evaluate_regimen(regimen, declared_allergies="Penicillin")
        allergies = result['alerts']['allergies']
        
        self.assertTrue(len(allergies) > 0)
        self.assertEqual(allergies[0]['declared_allergy'], 'Penicillin')
        self.assertEqual(allergies[0]['severity'], 'CRITICAL')
        self.assertIn('SEVERE ALLERGY CONFLICT', allergies[0]['patient_warning'])

    def test_elderly_dose_limit_exceeded(self):
        """Test cumulative dose limits for Paracetamol (>3000mg/day in elderly)."""
        # Patient taking Dolo 650 3 times a day (1950mg) + Crocin 500 3 times a day (1500mg) = 3450mg/day
        regimen = [
            'Tab Dolo 650mg TDS',
            'Tab Crocin 500mg TDS'
        ]
        result = self.safety_engine.evaluate_regimen(regimen, patient_age=72)
        dose_alerts = result['alerts']['geriatric_dose_limits']
        
        self.assertTrue(len(dose_alerts) > 0)
        self.assertEqual(dose_alerts[0]['ingredient'], 'Paracetamol')
        self.assertIn('3450', dose_alerts[0]['calculated_daily_dose'])
        self.assertIn('Excessive Daily Dose Alert', dose_alerts[0]['patient_warning'])

    def test_triple_whammy_detection(self):
        """Test the famous geriatric 'Triple Whammy' (ARB + Loop Diuretic + NSAID)."""
        regimen = [
            'Tab Telma 40mg 1-0-0',         # ARB
            'Tab Lasix 40mg 1-0-0',          # Loop Diuretic (Furosemide)
            'Tab Brufen 400mg 1-0-1'        # NSAID (Ibuprofen)
        ]
        result = self.safety_engine.evaluate_regimen(regimen)
        interactions = result['alerts']['drug_interactions']
        
        # Should flag Telmisartan + Ibuprofen, Furosemide + Ibuprofen, and Furosemide + Telmisartan
        self.assertGreaterEqual(len(interactions), 2)
        high_alerts = [i for i in interactions if i['severity'] == 'HIGH']
        self.assertTrue(len(high_alerts) >= 2)
        self.assertTrue(result['summary']['has_critical_alerts'])

if __name__ == '__main__':
    unittest.main()
