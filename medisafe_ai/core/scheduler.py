# core/scheduler.py
# MediSafe AI - Module 3: Medication Scheduler & Reminders
# Daily Pillbox Timetable, Chronic vs Acute Duration Handling, and Adherence Tracking
# Decision-Support Only: Does not replace professional medical judgment.

import re
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from core.reconciliation import ReconciliationEngine
from database.db import (
    save_medication_schedules,
    get_patient_schedules,
    log_adherence_event,
    get_adherence_logs_for_date,
    get_adherence_rate
)

class SchedulerEngine:
    """
    Scheduler engine for MediSafe AI.
    Converts medication frequencies and durations into an elderly-friendly,
    meal-anchored pillbox schedule (Morning, Afternoon, Evening, Night, SOS)
    and manages adherence logs.
    """

    SLOT_DEFINITIONS = {
        "morning": {
            "key": "morning",
            "title": "Morning (Breakfast)",
            "time_str": "08:00 AM",
            "icon": "sun",
            "badge": "warning text-dark"
        },
        "afternoon": {
            "key": "afternoon",
            "title": "Afternoon (Lunch)",
            "time_str": "01:00 PM",
            "icon": "brightness-high",
            "badge": "primary"
        },
        "evening": {
            "key": "evening",
            "title": "Evening (Snack / Tea)",
            "time_str": "05:00 PM",
            "icon": "cloud-sun",
            "badge": "info text-dark"
        },
        "night": {
            "key": "night",
            "title": "Night (Dinner / Bedtime)",
            "time_str": "08:30 PM",
            "icon": "moon-stars",
            "badge": "dark"
        },
        "sos": {
            "key": "sos",
            "title": "As Needed (SOS / PRN)",
            "time_str": "When required",
            "icon": "exclamation-circle",
            "badge": "secondary"
        }
    }

    # Frequency mapping to slots
    FREQ_TO_SLOTS = {
        "OD": ["morning"],
        "OD-M": ["morning"],
        "OD-A": ["afternoon"],
        "HS": ["night"],
        "BD": ["morning", "night"],
        "TDS": ["morning", "afternoon", "night"],
        "QID": ["morning", "afternoon", "evening", "night"],
        "PRN": ["sos"],
        "QOD": ["morning"]
    }

    def __init__(self):
        self.reconciliation_engine = ReconciliationEngine()

    def parse_duration_info(self, raw_duration: str, start_date: date) -> Dict[str, Any]:
        """
        Calculates whether a medicine is chronic (ongoing) or fixed-duration,
        and determines start and end dates.
        """
        match = re.search(r'(\d+)\s*(day|days|week|weeks|month|months)', raw_duration, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            unit = match.group(2).lower()
            if 'week' in unit:
                days = num * 7
            elif 'month' in unit:
                days = num * 30
            else:
                days = num

            end_date = start_date + timedelta(days=days - 1)
            return {
                'is_chronic': False,
                'duration_days': days,
                'duration_label': f"{days} Days Course",
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d')
            }
        else:
            return {
                'is_chronic': True,
                'duration_days': None,
                'duration_label': "Ongoing / Chronic Maintenance",
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': None
            }

    def process_medication_entry(self, med_entry: Any, start_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Normalizes a medicine entry and computes its schedule slots and duration bounds.
        """
        if start_date is None:
            start_date = date.today()

        norm = self.reconciliation_engine.normalize_medicine(med_entry)
        dur_info = self.parse_duration_info(norm['duration'], start_date)

        freq_code = norm['frequency']
        assigned_slots = self.FREQ_TO_SLOTS.get(freq_code, ["morning"])

        return {
            'raw_name': norm['raw_name'],
            'brand_name': norm['brand_name'],
            'generic_name': norm['generic_name'],
            'display_generic': norm['display_generic'],
            'drug_class': norm['drug_class'],
            'strength': norm['strength'],
            'unit': norm['unit'],
            'dosage_str': f"{norm['strength'] or ''}{norm['unit']}".strip(),
            'frequency': norm['frequency'],
            'frequency_label': norm['frequency_label'],
            'timing': norm['timing'],
            'timing_label': norm['timing_label'],
            'instructions': norm.get('instructions', ''),
            'is_chronic': dur_info['is_chronic'],
            'duration_days': dur_info['duration_days'],
            'duration_label': dur_info['duration_label'],
            'start_date': dur_info['start_date'],
            'end_date': dur_info['end_date'],
            'slots': assigned_slots
        }

    def evaluate_course_status(self, med: Dict[str, Any], target_date: date) -> Dict[str, Any]:
        """
        Checks whether a medicine course is Active, Completed, or Pending on the target date.
        """
        start = datetime.strptime(med['start_date'], '%Y-%m-%d').date() if med.get('start_date') else target_date

        if med['is_chronic']:
            return {
                'is_active': target_date >= start,
                'status_code': 'ACTIVE',
                'badge_class': 'success',
                'status_label': 'Ongoing Daily Maintenance'
            }

        end = datetime.strptime(med['end_date'], '%Y-%m-%d').date()
        if target_date < start:
            return {
                'is_active': False,
                'status_code': 'UPCOMING',
                'badge_class': 'secondary',
                'status_label': f"Starts on {med['start_date']}"
            }
        elif start <= target_date <= end:
            day_num = (target_date - start).days + 1
            return {
                'is_active': True,
                'status_code': 'ACTIVE',
                'badge_class': 'primary',
                'status_label': f"Day {day_num} of {med['duration_days']} (Active Course)"
            }
        else:
            return {
                'is_active': False,
                'status_code': 'COMPLETED',
                'badge_class': 'danger',
                'status_label': f"Course Completed on {med['end_date']} (Do NOT continue)"
            }

    def generate_daily_timetable(
        self,
        medicines: List[Any],
        target_date: Optional[date] = None,
        patient_id: int = 1
    ) -> Dict[str, Any]:
        """
        Generates the 5-slot pillbox timetable for the target date.
        """
        if target_date is None:
            target_date = date.today()

        target_date_str = target_date.strftime('%Y-%m-%d')
        adherence_lookup = get_adherence_logs_for_date(patient_id, target_date_str)

        processed_meds = [self.process_medication_entry(m, target_date) for m in medicines]

        # Initialize slot buckets
        slots = {}
        for key, defn in self.SLOT_DEFINITIONS.items():
            slots[key] = {
                'key': key,
                'title': defn['title'],
                'time_str': defn['time_str'],
                'icon': defn['icon'],
                'badge': defn['badge'],
                'doses': [],
                'items': []
            }

        total_scheduled_doses = 0
        total_taken_doses = 0

        for med in processed_meds:
            course_status = self.evaluate_course_status(med, target_date)
            for slot_key in med['slots']:
                if slot_key in slots:
                    dose_id = f"{med['brand_name']}|||{slot_key}"
                    logged_status = adherence_lookup.get(dose_id, "PENDING")

                    if course_status['is_active'] and slot_key != 'sos':
                        total_scheduled_doses += 1
                        if logged_status == 'TAKEN':
                            total_taken_doses += 1

                    dose_entry = {
                        'medicine': med,
                        'slot_key': slot_key,
                        'course_status': course_status,
                        'adherence_status': logged_status,
                        'dose_key': dose_id
                    }
                    slots[slot_key]['doses'].append(dose_entry)
                    slots[slot_key]['items'].append(dose_entry)

        # Calculate daily compliance rate
        compliance_pct = round((total_taken_doses / total_scheduled_doses * 100), 1) if total_scheduled_doses > 0 else 100.0

        # Overall weekly adherence from database
        weekly_adherence = get_adherence_rate(patient_id, days=7)

        return {
            'target_date': target_date_str,
            'target_date_display': target_date.strftime('%A, %d %B %Y'),
            'slots': slots,
            'daily_summary': {
                'total_scheduled': total_scheduled_doses,
                'total_taken': total_taken_doses,
                'compliance_percentage': compliance_pct
            },
            'weekly_adherence': weekly_adherence,
            'medicines_count': len(processed_meds)
        }

    def record_dose_status(self, patient_id: int, medicine_name: str, slot_key: str, scheduled_date: str, status: str) -> int:
        """Records dose taken or missed."""
        return log_adherence_event(
            patient_id=patient_id,
            medicine_name=medicine_name,
            slot_name=slot_key,
            scheduled_date=scheduled_date,
            status=status
        )
