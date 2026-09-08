import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Severity order for sorting alerts
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3, "INFO": 4}

# Rule-based clinical recommendation templates
RECOMMENDATION_RULES = [
    {
        "trigger_keywords": ["warfarin", "acenocoumarol"],
        "co_trigger": ["aspirin", "ibuprofen", "naproxen", "diclofenac", "nsaid"],
        "text": "Monitor INR closely. Concurrent use of anticoagulants with NSAIDs/antiplatelet agents significantly increases bleeding risk. Consider alternative analgesics (e.g., Paracetamol ≤2g/day).",
        "severity": "CRITICAL",
    },
    {
        "trigger_keywords": ["ciprofloxacin", "levofloxacin", "ofloxacin"],
        "co_trigger": ["glimepiride", "glibenclamide", "glipizide", "sulfonylurea"],
        "text": "Fluoroquinolone antibiotics may potentiate hypoglycaemia with sulfonylureas. Monitor blood glucose more frequently during antibiotic course.",
        "severity": "HIGH",
    },
    {
        "trigger_keywords": ["losartan", "telmisartan", "enalapril", "ramipril"],
        "co_trigger": ["spironolactone", "eplerenone"],
        "text": "ARB/ACE-inhibitor combined with aldosterone antagonist carries hyperkalemia risk in elderly. Monitor serum potassium every 2–4 weeks.",
        "severity": "HIGH",
    },
    {
        "trigger_keywords": ["atorvastatin", "rosuvastatin", "simvastatin"],
        "co_trigger": ["azithromycin", "erythromycin", "clarithromycin"],
        "text": "Statin + macrolide combination may increase myopathy risk. Consider temporarily withholding statin during short antibiotic course or switching to azithromycin.",
        "severity": "MODERATE",
    },
    {
        "trigger_keywords": ["furosemide", "torsemide"],
        "co_trigger": ["losartan", "telmisartan", "enalapril"],
        "co_trigger2": ["ibuprofen", "naproxen", "diclofenac"],
        "text": "Triple Whammy combination (ARB/ACEI + Loop Diuretic + NSAID) carries acute kidney injury risk. Avoid NSAIDs; monitor renal function and electrolytes.",
        "severity": "CRITICAL",
    },
    {
        "trigger_keywords": ["metformin"],
        "co_trigger": [],
        "age_threshold": 75,
        "text": "Metformin should be used with caution in patients ≥75 years or with eGFR <45 mL/min/1.73m². Reassess renal function every 6 months.",
        "severity": "MODERATE",
    },
    {
        "trigger_keywords": ["alprazolam", "clonazepam", "diazepam", "lorazepam"],
        "co_trigger": [],
        "text": "Benzodiazepines are Beers Criteria high-risk medications in elderly patients. Increases fall risk and cognitive impairment. Explore non-pharmacological alternatives.",
        "severity": "HIGH",
    },
    {
        "trigger_keywords": ["zolpidem", "zopiclone"],
        "co_trigger": [],
        "text": "Z-drugs (zolpidem, zopiclone) are listed on the Beers Criteria for elderly patients. Limit to lowest effective dose ≤5mg; reassess monthly.",
        "severity": "HIGH",
    },
]


class ReportGenerator:
    """
    Generates structured patient safety reports from MediSafe AI module outputs.
    Combines reconciliation changes, safety alerts, schedule, and adherence data
    into a unified clinical document.
    """

    def __init__(self):
        pass

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def generate_report(
        self,
        patient_info: dict,
        reconciliation_result: dict = None,
        safety_result: dict = None,
        schedule_timetable: dict = None,
        adherence_stats: dict = None,
        medicines_list: list = None,
        report_date: date = None,
    ) -> dict:
        """
        Produce a complete patient safety report dict.

        Parameters
        ----------
        patient_info : dict
            Keys: name, age, sex, allergies, conditions, patient_id
        reconciliation_result : dict
            Output of ReconciliationEngine.reconcile()
        safety_result : dict
            Output of SafetyEngine.evaluate_regimen()
        schedule_timetable : dict
            Output of SchedulerEngine.generate_daily_timetable()
        adherence_stats : dict
            Output of db.get_adherence_rate()
        medicines_list : list[str]
            Raw medicine text lines (used when engine outputs are absent)
        report_date : date
            Date for report header (defaults to today)
        """
        if report_date is None:
            report_date = date.today()

        # ── 1. Patient header ────────────────────────────────────────────────
        header = self._build_header(patient_info, report_date)

        # ── 2. Reconciliation summary ────────────────────────────────────────
        reconciliation_summary = self._build_reconciliation_summary(reconciliation_result)

        # ── 3. Safety alert panel (from SafetyEngine + rule-based extras) ────
        safety_panel = self._build_safety_panel(
            safety_result, medicines_list or [], patient_info.get('age', 0)
        )

        # ── 4. Schedule table ────────────────────────────────────────────────
        schedule_table = self._build_schedule_table(schedule_timetable)

        # ── 5. Adherence chart data ──────────────────────────────────────────
        adherence_chart = self._build_adherence_chart(adherence_stats)

        # ── 6. Clinical recommendations ──────────────────────────────────────
        recommendations = self._build_recommendations(
            medicines_list or [],
            safety_result,
            patient_info.get('age', 0)
        )

        # ── 7. Risk score ────────────────────────────────────────────────────
        risk_score = self._compute_risk_score(safety_panel, reconciliation_summary, adherence_chart)

        return {
            'header': header,
            'reconciliation_summary': reconciliation_summary,
            'safety_panel': safety_panel,
            'schedule_table': schedule_table,
            'adherence_chart': adherence_chart,
            'recommendations': recommendations,
            'risk_score': risk_score,
            'generated_at': datetime.now().strftime('%d-%b-%Y %H:%M:%S'),
            'report_date': report_date.strftime('%d-%b-%Y'),
            'disclaimer': (
                "DECISION SUPPORT ONLY — This report is generated by an automated "
                "AI-assisted system (MediSafe AI) for educational and informational purposes. "
                "It does NOT constitute medical advice and must NOT replace the clinical "
                "judgement of a licensed physician or pharmacist. Always verify all "
                "medication details with a qualified healthcare professional before "
                "making any clinical decisions."
            ),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Private builders
    # ──────────────────────────────────────────────────────────────────────────

    def _build_header(self, patient_info: dict, report_date: date) -> dict:
        return {
            'patient_name': patient_info.get('name', 'Unknown Patient'),
            'patient_age': patient_info.get('age', 'N/A'),
            'patient_sex': patient_info.get('sex', 'N/A'),
            'patient_id': patient_info.get('patient_id', 'MED-001'),
            'allergies': patient_info.get('allergies', 'None reported'),
            'conditions': patient_info.get('conditions', 'Not specified'),
            'report_date': report_date.strftime('%d-%b-%Y'),
            'report_title': 'Medication Safety & Adherence Report',
            'institution': 'VET Institute of Arts and Science College — MediSafe AI',
        }

    def _build_reconciliation_summary(self, result: dict) -> dict:
        if not result:
            return {
                'available': False,
                'changes': [],
                'counts': {},
                'total': 0,
                'has_high_risk_changes': False,
            }

        changes = result.get('changes', [])
        counts = {}
        high_risk_categories = {'DISCONTINUED', 'DUPLICATE'}
        has_high_risk = False

        for change in changes:
            cat = change.get('category', 'UNKNOWN')
            counts[cat] = counts.get(cat, 0) + 1
            if cat in high_risk_categories:
                has_high_risk = True

        return {
            'available': True,
            'changes': changes,
            'counts': counts,
            'total': len(changes),
            'has_high_risk_changes': has_high_risk,
            'old_label': result.get('old_label', 'Previous Regimen'),
            'new_label': result.get('new_label', 'Current Regimen'),
        }

    def _build_safety_panel(self, safety_result: dict, medicines_list: list, age: int) -> dict:
        alerts = []

        if safety_result:
            # DDI alerts from SafetyEngine
            for ddi in safety_result.get('drug_interactions', []):
                alerts.append({
                    'type': 'DDI',
                    'severity': ddi.get('severity', 'MODERATE'),
                    'title': f"Drug Interaction: {ddi.get('drug_a', '')} + {ddi.get('drug_b', '')}",
                    'description': ddi.get('description', ''),
                    'clinical_effect': ddi.get('clinical_effect', ''),
                    'recommendation': ddi.get('recommendation', ''),
                    'source': 'SafetyEngine DDI Database',
                })

            # Allergy alerts
            for allergy in safety_result.get('allergy_alerts', []):
                alerts.append({
                    'type': 'ALLERGY',
                    'severity': 'CRITICAL',
                    'title': f"Allergy Alert: {allergy.get('medicine', '')}",
                    'description': allergy.get('reason', ''),
                    'clinical_effect': 'Potential allergic reaction including anaphylaxis',
                    'recommendation': 'Discontinue immediately and consult prescribing physician.',
                    'source': 'Patient Allergy Profile',
                })

            # Dose limit alerts
            for dose_alert in safety_result.get('dose_limit_alerts', []):
                alerts.append({
                    'type': 'DOSE',
                    'severity': dose_alert.get('severity', 'HIGH'),
                    'title': f"Dose Limit Exceeded: {dose_alert.get('medicine', '')}",
                    'description': dose_alert.get('reason', ''),
                    'clinical_effect': dose_alert.get('effect', 'Risk of toxicity or adverse effects'),
                    'recommendation': dose_alert.get('recommendation', 'Reduce dose or discontinue.'),
                    'source': 'Geriatric Dose Limit Guidelines',
                })

        # Sort by severity
        alerts.sort(key=lambda a: SEVERITY_ORDER.get(a['severity'], 99))

        critical_count = sum(1 for a in alerts if a['severity'] == 'CRITICAL')
        high_count = sum(1 for a in alerts if a['severity'] == 'HIGH')

        return {
            'alerts': alerts,
            'total_alerts': len(alerts),
            'critical_count': critical_count,
            'high_count': high_count,
            'is_safe': len(alerts) == 0,
            'overall_severity': (
                'CRITICAL' if critical_count > 0 else
                'HIGH' if high_count > 0 else
                'MODERATE' if alerts else
                'SAFE'
            ),
        }

    def _build_schedule_table(self, timetable: dict) -> dict:
        if not timetable:
            return {'available': False, 'slots': [], 'total_doses': 0}

        slots_out = []
        slot_order = ['morning', 'afternoon', 'evening', 'night', 'sos']
        slot_labels = {
            'morning': ('Morning', '08:00 AM', '🌅'),
            'afternoon': ('Afternoon', '01:00 PM', '☀️'),
            'evening': ('Evening', '05:00 PM', '🌇'),
            'night': ('Night / Bedtime', '08:30 PM', '🌙'),
            'sos': ('As Needed (SOS)', 'PRN', '🚨'),
        }
        total = 0

        slots_data = timetable.get('slots', {})
        for key in slot_order:
            slot = slots_data.get(key, {})
            doses = slot.get('doses', [])
            if doses:
                label, time_str, icon = slot_labels.get(key, (key, '', ''))
                slots_out.append({
                    'slot_key': key,
                    'label': label,
                    'time': time_str,
                    'icon': icon,
                    'doses': doses,
                    'count': len(doses),
                })
                total += len(doses)

        return {
            'available': True,
            'slots': slots_out,
            'total_doses': total,
            'target_date': timetable.get('date', date.today().strftime('%Y-%m-%d')),
            'patient_name': timetable.get('patient_name', ''),
        }

    def _build_adherence_chart(self, adherence_stats: dict) -> dict:
        if not adherence_stats:
            # Return synthetic demo data for visualization
            today = date.today()
            demo_days = []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                rate = [82, 90, 75, 88, 95, 70, 85][6 - i]
                demo_days.append({
                    'date': d.strftime('%d %b'),
                    'rate': rate,
                    'taken': int(rate * 0.05),
                    'missed': int((100 - rate) * 0.05),
                    'is_demo': True,
                })
            avg = sum(d['rate'] for d in demo_days) // 7
            return {
                'available': True,
                'is_demo': True,
                'days': demo_days,
                'average_rate': avg,
                'trend': 'stable',
                'total_taken': sum(d['taken'] for d in demo_days),
                'total_missed': sum(d['missed'] for d in demo_days),
            }

        days = adherence_stats.get('daily', [])
        avg = adherence_stats.get('overall_rate', 0)
        rates = [d.get('rate', 0) for d in days if d.get('rate') is not None]
        trend = 'improving' if len(rates) >= 2 and rates[-1] > rates[0] else \
                'declining' if len(rates) >= 2 and rates[-1] < rates[0] else 'stable'

        return {
            'available': True,
            'is_demo': False,
            'days': days,
            'average_rate': round(avg, 1),
            'trend': trend,
            'total_taken': adherence_stats.get('total_taken', 0),
            'total_missed': adherence_stats.get('total_missed', 0),
        }

    def _build_recommendations(self, medicines_list: list, safety_result: dict, age: int) -> list:
        recs = []
        med_text = ' '.join(medicines_list).lower()

        for rule in RECOMMENDATION_RULES:
            triggers = rule.get('trigger_keywords', [])
            co_triggers = rule.get('co_trigger', [])
            age_threshold = rule.get('age_threshold', 0)

            trigger_match = any(kw in med_text for kw in triggers)
            if not trigger_match:
                continue

            if age_threshold and age < age_threshold:
                continue

            if co_triggers:
                co_match = any(kw in med_text for kw in co_triggers)
                if not co_match:
                    continue

            recs.append({
                'severity': rule['severity'],
                'text': rule['text'],
            })

        # Add generic elderly polypharmacy recommendation if 5+ medicines
        med_lines = [l for l in medicines_list if l.strip()]
        if len(med_lines) >= 5:
            recs.append({
                'severity': 'MODERATE',
                'text': (
                    f"Patient is prescribed {len(med_lines)} medications (polypharmacy). "
                    "WHO recommends regular medication review for elderly patients on 5+ drugs. "
                    "Consider a structured pharmacist-led medication reconciliation review."
                ),
            })

        # Deduplicate
        seen = set()
        unique = []
        for r in recs:
            key = r['text'][:60]
            if key not in seen:
                seen.add(key)
                unique.append(r)

        # Sort by severity
        unique.sort(key=lambda r: SEVERITY_ORDER.get(r['severity'], 99))
        return unique

    def _compute_risk_score(
        self, safety_panel: dict, reconciliation_summary: dict, adherence_chart: dict
    ) -> dict:
        score = 0
        factors = []

        crit = safety_panel.get('critical_count', 0)
        high = safety_panel.get('high_count', 0)
        total_alerts = safety_panel.get('total_alerts', 0)

        score += crit * 30 + high * 15 + (total_alerts - crit - high) * 5

        if crit > 0:
            factors.append(f"{crit} CRITICAL safety alert(s)")
        if high > 0:
            factors.append(f"{high} HIGH severity interaction(s)")

        if reconciliation_summary.get('has_high_risk_changes'):
            score += 10
            factors.append("High-risk prescription changes (DISCONTINUED / DUPLICATE)")

        avg_adherence = adherence_chart.get('average_rate', 100)
        if avg_adherence < 70:
            score += 20
            factors.append(f"Poor medication adherence ({avg_adherence:.0f}% avg over 7 days)")
        elif avg_adherence < 85:
            score += 10
            factors.append(f"Suboptimal adherence ({avg_adherence:.0f}% avg)")

        score = min(score, 100)

        if score >= 60:
            level = 'CRITICAL'
            color = 'danger'
            label = 'High Risk — Urgent pharmacist or physician review required'
        elif score >= 35:
            level = 'HIGH'
            color = 'warning'
            label = 'Moderate Risk — Schedule medication review within 48 hours'
        elif score >= 15:
            level = 'MODERATE'
            color = 'info'
            label = 'Low-Moderate Risk — Routine monitoring recommended'
        else:
            level = 'SAFE'
            color = 'success'
            label = 'Low Risk — Continue current regimen with standard follow-up'

        return {
            'score': score,
            'level': level,
            'color': color,
            'label': label,
            'factors': factors,
        }
