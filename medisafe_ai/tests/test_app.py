# tests/test_app.py
# Integration tests for Flask endpoints and HTML template rendering

import unittest
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database.db import get_reconciliation_history

class TestAppIntegration(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_homepage_redirect(self):
        """Verify root route redirects to /reconcile."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/reconcile', response.headers['Location'])

    def test_reconcile_get_page(self):
        """Verify reconciliation page renders properly."""
        response = self.client.get('/reconcile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Medication Reconciliation Engine', response.data)
        self.assertIn(b'Decision Support Only', response.data)
        self.assertIn(b'Ramaswamy K.', response.data)

    def test_reconcile_post_form(self):
        """Verify POST reconciliation form submission and result rendering."""
        data = {
            'old_label': 'Admission',
            'new_label': 'Discharge',
            'old_medicines': 'Tab Telma 20mg 1-0-0\nTab Pantocid 40mg 1-0-0',
            'new_medicines': 'Tab Telma 40mg 1-0-0\nTab Atorva 10mg 0-0-1'
        }
        response = self.client.post('/reconcile', data=data)
        self.assertEqual(response.status_code, 200)
        # Check rendered badges and notes
        self.assertIn(b'CHANGED', response.data)
        self.assertIn(b'DISCONTINUED', response.data)
        self.assertIn(b'NEW', response.data)
        self.assertIn(b'Reconciliation Report', response.data)

    def test_api_reconcile_json(self):
        """Verify REST API endpoint /api/reconcile."""
        payload = {
            'old_medicines': ['Tab Dolo 650mg 1-0-1'],
            'new_medicines': ['Tab Calpol 650mg 1-0-1']
        }
        response = self.client.post(
            '/api/reconcile',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        discrepancies = data['data']['discrepancies']
        self.assertEqual(len(discrepancies), 1)
        # Brand substitution of same ingredient
        self.assertEqual(discrepancies[0]['category'], 'CHANGED')
        self.assertEqual(discrepancies[0]['generic_name'], 'Paracetamol')

    def test_safety_get_page(self):
        """Verify safety page renders properly."""
        response = self.client.get('/safety')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Medication Safety & Risk Screening', response.data)
        self.assertIn(b'Active Medication Regimen', response.data)

    def test_safety_post_form(self):
        """Verify POST /safety evaluation and template rendering."""
        data = {
            'medicines_input': 'Tab Telma 40mg 1-0-0\nTab Aldactone 25mg 1-0-0',
            'allergies_input': 'Penicillin',
            'patient_age': '72'
        }
        response = self.client.post('/safety', data=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Safety Evaluation Report', response.data)
        self.assertIn(b'Hyperkalemia', response.data)

    def test_api_safety_json(self):
        """Verify REST API endpoint /api/safety."""
        payload = {
            'medicines': ['Tab Augmentin 625mg 1-0-1'],
            'declared_allergies': 'Penicillin',
            'patient_age': 70
        }
        response = self.client.post(
            '/api/safety',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        allergies = data['data']['alerts']['allergies']
        self.assertEqual(len(allergies), 1)
        self.assertEqual(allergies[0]['severity'], 'CRITICAL')

    def test_schedule_get_page(self):
        """Verify schedule page renders properly with daily pillbox."""
        response = self.client.get('/schedule')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Daily Medication Timetable & Adherence', response.data)
        self.assertIn(b'Morning', response.data)
        self.assertIn(b'Breakfast', response.data)

    def test_schedule_post_form(self):
        """Verify POST /schedule generates timetable properly."""
        data = {
            'target_date': '2026-09-08',
            'medicines_input': 'Tab Telma 40mg 1-0-0\nTab Augmentin 625mg 1-0-1 for 5 days'
        }
        response = self.client.post('/schedule', data=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Daily Pillbox', response.data)
        self.assertIn(b'Telma', response.data)
        self.assertIn(b'Augmentin', response.data)

    def test_api_schedule_json(self):
        """Verify REST API endpoint /api/schedule."""
        payload = {
            'medicines': ['Tab Telma 40mg 1-0-0'],
            'target_date': '2026-09-08',
            'patient_id': 1
        }
        response = self.client.post(
            '/api/schedule',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('slots', data['data'])
        self.assertEqual(len(data['data']['slots']['morning']['items']), 1)

    def test_api_adherence_logging_and_stats(self):
        """Verify 1-click dose adherence logging and stats retrieval."""
        log_payload = {
            'patient_id': 1,
            'medicine_name': 'Telma',
            'slot_key': 'morning',
            'scheduled_date': '2026-09-08',
            'status': 'TAKEN'
        }
        post_res = self.client.post(
            '/api/adherence/log',
            data=json.dumps(log_payload),
            content_type='application/json'
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.get_json()['status'], 'success')

        # Retrieve stats
        stats_res = self.client.get('/api/adherence/stats?patient_id=1')
        self.assertEqual(stats_res.status_code, 200)
        stats_data = stats_res.get_json()
        self.assertEqual(stats_data['status'], 'success')
        self.assertGreaterEqual(stats_data['stats']['total_logged'], 1)

if __name__ == '__main__':
    unittest.main()
