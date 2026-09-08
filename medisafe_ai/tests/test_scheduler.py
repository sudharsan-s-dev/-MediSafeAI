# tests/test_scheduler.py
# Unit tests for MediSafe AI Module 3: Medication Scheduler & Reminders

import unittest
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scheduler import SchedulerEngine
from database.db import init_db

class TestSchedulerEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.scheduler = SchedulerEngine()

    def test_frequency_slot_allocation(self):
        """Test correct mapping of prescription frequencies to meal-based time slots."""
        med_od = self.scheduler.process_medication_entry("Tab Telma 40mg 1-0-0 (morning)")
        self.assertEqual(med_od['slots'], ['morning'])

        med_bd = self.scheduler.process_medication_entry("Tab Glycomet 500mg 1-0-1 after food")
        self.assertEqual(med_bd['slots'], ['morning', 'night'])

        med_tds = self.scheduler.process_medication_entry("Tab Dolo 650mg 1-1-1 after food")
        self.assertEqual(med_tds['slots'], ['morning', 'afternoon', 'night'])

        med_sos = self.scheduler.process_medication_entry("Tab Calpol 650mg SOS")
        self.assertEqual(med_sos['slots'], ['sos'])

    def test_chronic_vs_fixed_duration(self):
        """Test distinction between ongoing maintenance medicines and short-duration courses."""
        # Chronic maintenance
        chronic_med = self.scheduler.process_medication_entry("Tab Telma 40mg 1-0-0 daily")
        self.assertTrue(chronic_med['is_chronic'])
        self.assertIsNone(chronic_med['end_date'])

        # Fixed 5-day antibiotic course
        start = date(2026, 9, 1)
        acute_med = self.scheduler.process_medication_entry("Tab Augmentin 625mg 1-0-1 for 5 days", start_date=start)
        self.assertFalse(acute_med['is_chronic'])
        self.assertEqual(acute_med['duration_days'], 5)
        self.assertEqual(acute_med['start_date'], '2026-09-01')
        self.assertEqual(acute_med['end_date'], '2026-09-05')

    def test_course_expiration_logic(self):
        """Test that short courses are active during therapy and flagged COMPLETED after end date."""
        start = date(2026, 9, 1)
        med = self.scheduler.process_medication_entry("Tab Augmentin 625mg 1-0-1 for 5 days", start_date=start)

        # Day 3 (within 5-day window)
        target_active = date(2026, 9, 3)
        status_active = self.scheduler.evaluate_course_status(med, target_active)
        self.assertTrue(status_active['is_active'])
        self.assertEqual(status_active['status_code'], 'ACTIVE')
        self.assertIn('Day 3 of 5', status_active['status_label'])

        # Day 8 (after 5-day window)
        target_expired = date(2026, 9, 8)
        status_expired = self.scheduler.evaluate_course_status(med, target_expired)
        self.assertFalse(status_expired['is_active'])
        self.assertEqual(status_expired['status_code'], 'COMPLETED')
        self.assertIn('Course Completed', status_expired['status_label'])

    def test_daily_timetable_generation(self):
        """Test full generation of the 5-slot daily timetable."""
        meds = [
            "Tab Telma 40mg 1-0-0 (morning)",
            "Tab Glycomet 500mg 1-0-1 after food",
            "Tab Atorva 10mg 0-0-1 night",
            "Tab Dolo 650mg SOS"
        ]
        timetable = self.scheduler.generate_daily_timetable(meds, target_date=date.today(), patient_id=99)
        slots = timetable['slots']

        # Morning should have Telma and Glycomet
        morning_brands = [i['medicine']['brand_name'] for i in slots['morning']['items']]
        self.assertIn('Telma', morning_brands)
        self.assertIn('Glycomet', morning_brands)

        # Night should have Glycomet and Atorva
        night_brands = [i['medicine']['brand_name'] for i in slots['night']['items']]
        self.assertIn('Glycomet', night_brands)
        self.assertIn('Atorva', night_brands)

        # SOS should have Dolo
        sos_brands = [i['medicine']['brand_name'] for i in slots['sos']['items']]
        self.assertIn('Dolo', sos_brands)

    def test_adherence_logging(self):
        """Test dose recording and compliance rate calculation."""
        test_patient_id = 999
        self.scheduler.record_dose_status(test_patient_id, "Tab Telma 40mg", "morning", "2026-09-08", "TAKEN")
        self.scheduler.record_dose_status(test_patient_id, "Tab Glycomet 500mg", "morning", "2026-09-08", "TAKEN")
        self.scheduler.record_dose_status(test_patient_id, "Tab Atorva 10mg", "night", "2026-09-08", "MISSED")

        rate_info = self.scheduler.generate_daily_timetable([], patient_id=test_patient_id)['weekly_adherence']
        self.assertEqual(rate_info['total_logged'], 3)
        self.assertEqual(rate_info['taken_count'], 2)
        self.assertEqual(rate_info['missed_count'], 1)
        self.assertAlmostEqual(rate_info['adherence_percentage'], 66.7, places=1)

if __name__ == '__main__':
    unittest.main()
