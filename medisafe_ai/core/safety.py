# core/safety.py
# MediSafe AI - Module 2: Safety Checks Engine
# Curated Geriatric Drug-Drug Interactions, User Allergy Detection & Elderly Dose Limits
# Decision-Support Only: Does not replace professional medical judgment.

import os
import json
import re
from typing import List, Dict, Any, Tuple, Optional
from core.reconciliation import ReconciliationEngine

class SafetyEngine:
    """
    Safety analysis engine for MediSafe AI.
    Screens active patient medications against:
    1. Curated Drug-Drug Interaction (DDI) pairs
    2. User-declared allergies (active ingredients & drug classes)
    3. Duplicate active ingredients across multiple commercial brands
    4. Geriatric cumulative daily dosage thresholds (e.g. Beers criteria / geriatric guidelines)
    """

    ALLERGY_CLASS_MAP = {
        "penicillin": ["amoxicillin", "amoxicillin + clavulanic acid", "ampicillin", "augmentin", "amoxyclav"],
        "nsaid": ["aspirin", "ibuprofen", "ibuprofen + paracetamol", "diclofenac", "naproxen", "combiflam"],
        "aspirin": ["aspirin", "ecosprin", "disprin", "asa"],
        "sulfa": ["glimepiride", "sulfamethoxazole", "trimethoprim"],
        "statin": ["atorvastatin", "rosuvastatin", "simvastatin"],
        "opioid": ["tramadol", "codeine", "morphine"],
        "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "ofloxacin"]
    }

    # Geriatric daily dosage thresholds (mg/day)
    GERIATRIC_DOSE_LIMITS = {
        "paracetamol": {
            "max_daily_mg": 3000.0,
            "caution": "Elderly daily threshold is 3,000 mg (lower than the standard adult 4,000 mg limit to protect against hepatotoxicity/liver strain)."
        },
        "alprazolam": {
            "max_daily_mg": 0.5,
            "caution": "Beers Criteria warning: Alprazolam doses above 0.5 mg/day significantly elevate dizziness, delirium, and severe fall risk in older adults."
        },
        "zolpidem": {
            "max_daily_mg": 5.0,
            "caution": "Geriatric guideline: Zolpidem clearance is markedly reduced in older adults. Maximum recommended dose is 5 mg at bedtime to avoid nocturnal confusion and falls."
        },
        "tramadol": {
            "max_daily_mg": 200.0,
            "caution": "Geriatric threshold: Reduced renal clearance in elderly necessitates lower maximum daily doses to avoid central nervous system toxicity."
        }
    }

    def __init__(self, interactions_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if interactions_path is None:
            interactions_path = os.path.join(base_dir, 'data', 'drug_interactions.json')
        
        self.interactions_path = interactions_path
        self.interactions_db = self._load_interactions(interactions_path)
        self.reconciliation_engine = ReconciliationEngine()

    def _load_interactions(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)

    def check_drug_interactions(self, normalized_meds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Screens all pairwise combinations of active medications for known interactions.
        Handles combination drugs by unpacking constituent active ingredients.
        """
        detected_interactions = []
        seen_pairs = set()

        for i in range(len(normalized_meds)):
            for j in range(i + 1, len(normalized_meds)):
                med1 = normalized_meds[i]
                med2 = normalized_meds[j]

                # Extract list of active ingredients for each
                ings1 = med1.get('ingredients', [med1['generic_name']])
                ings2 = med2.get('ingredients', [med2['generic_name']])

                for ing1 in ings1:
                    ing1_norm = ing1.lower().strip()
                    for ing2 in ings2:
                        ing2_norm = ing2.lower().strip()

                        # Canonical pair key for deduplication
                        pair_key = tuple(sorted([ing1_norm, ing2_norm]))
                        if pair_key in seen_pairs:
                            continue

                        # Check against curated interactions
                        match = self._find_interaction_match(ing1_norm, ing2_norm)
                        if match:
                            seen_pairs.add(pair_key)
                            detected_interactions.append({
                                'drug_1': f"{med1['brand_name']} ({ing1.title()})",
                                'drug_2': f"{med2['brand_name']} ({ing2.title()})",
                                'ingredient_a': ing1.title(),
                                'ingredient_b': ing2.title(),
                                'severity': match['severity'],
                                'category': match['category'],
                                'patient_warning': match['patient_warning'],
                                'clinical_recommendation': match['clinical_recommendation'],
                                'mechanism': match.get('mechanism', '')
                            })

        # Sort by severity (HIGH first, then MODERATE, then LOW)
        severity_order = {'HIGH': 0, 'MODERATE': 1, 'LOW': 2}
        detected_interactions.sort(key=lambda x: severity_order.get(x['severity'], 3))
        return detected_interactions

    def _find_interaction_match(self, ing1: str, ing2: str) -> Optional[Dict[str, Any]]:
        for rule in self.interactions_db:
            ra = rule['drug_a'].lower().strip()
            rb = rule['drug_b'].lower().strip()
            if (ra == ing1 and rb == ing2) or (ra == ing2 and rb == ing1):
                return rule
        return None

    def check_allergies(self, normalized_meds: List[Dict[str, Any]], declared_allergies_str: str) -> List[Dict[str, Any]]:
        """
        Cross-references medicines against user-declared allergies.
        Recognizes both specific active ingredients and drug classes.
        """
        if not declared_allergies_str:
            return []

        declared_list = [a.strip().lower() for a in re.split(r'[,;/|]+', declared_allergies_str) if a.strip()]
        allergy_alerts = []

        for med in normalized_meds:
            brand_lower = med['brand_name'].lower()
            generic_lower = med['generic_name'].lower()
            ings = [ing.lower() for ing in med.get('ingredients', [generic_lower])]

            for allergy in declared_list:
                matched = False
                match_reason = ""

                # 1. Exact or substring match in brand or generic
                if allergy in brand_lower or allergy in generic_lower:
                    matched = True
                    match_reason = f"Direct match with declared allergy '{allergy.title()}'"
                # 2. Check constituent ingredients
                elif any(allergy in ing for ing in ings):
                    matched = True
                    match_reason = f"Active constituent ingredient matches '{allergy.title()}'"
                # 3. Check drug class hierarchy
                else:
                    for class_key, class_drugs in self.ALLERGY_CLASS_MAP.items():
                        if class_key in allergy:
                            if generic_lower in class_drugs or any(ing in class_drugs for ing in ings) or brand_lower in class_drugs:
                                matched = True
                                match_reason = f"Belongs to the '{class_key.title()}' class of medications"
                                break

                if matched:
                    allergy_alerts.append({
                        'medicine_name': f"{med['brand_name']} ({med['display_generic']} {med['strength']}{med['unit']})",
                        'declared_allergy': allergy.title(),
                        'severity': 'CRITICAL',
                        'reason': match_reason,
                        'patient_warning': f"🚨 SEVERE ALLERGY CONFLICT: You declared an allergy to '{allergy.title()}'. This medicine ({med['brand_name']}) contains or belongs to that substance and could trigger an allergic reaction. DO NOT TAKE without physician clearance.",
                        'clinical_recommendation': f"Contraindicated due to declared allergy to {allergy.title()}. Substitute with an alternative therapeutic class."
                    })
                    break

        return allergy_alerts

    def check_geriatric_dose_limits(self, normalized_meds: List[Dict[str, Any]], age: int = 72) -> List[Dict[str, Any]]:
        """
        Calculates total daily intake for each active ingredient and compares
        against elderly-specific safety guidelines.
        """
        dose_map: Dict[str, Dict[str, Any]] = {}

        for med in normalized_meds:
            strength = med.get('strength') or 0.0
            freq_per_day = med.get('frequency_per_day') or 1.0
            daily_intake = strength * freq_per_day

            for ing in med.get('ingredients', [med['generic_name']]):
                ing_lower = ing.lower()
                if ing_lower not in dose_map:
                    dose_map[ing_lower] = {
                        'total_daily_mg': 0.0,
                        'medicines': [],
                        'unit': med.get('unit', 'mg')
                    }
                dose_map[ing_lower]['total_daily_mg'] += daily_intake
                dose_map[ing_lower]['medicines'].append(f"{med['brand_name']} ({strength}{med['unit']} {med['frequency_label']})")

        warnings = []
        for ing, data in dose_map.items():
            if ing in self.GERIATRIC_DOSE_LIMITS:
                threshold = self.GERIATRIC_DOSE_LIMITS[ing]
                max_allowed = threshold['max_daily_mg']
                if data['total_daily_mg'] > max_allowed:
                    warnings.append({
                        'ingredient': ing.title(),
                        'calculated_daily_dose': f"{data['total_daily_mg']:.1f} {data['unit']}/day",
                        'max_recommended_dose': f"{max_allowed:.1f} {data['unit']}/day",
                        'severity': 'HIGH',
                        'medicines_involved': data['medicines'],
                        'patient_warning': f"⚠️ Excessive Daily Dose Alert: Your combined daily intake of {ing.title()} is {data['total_daily_mg']:.0f} {data['unit']}/day, which exceeds the safe elderly threshold of {max_allowed:.0f} {data['unit']}/day. {threshold['caution']}",
                        'clinical_recommendation': f"Reduce total daily dose to <= {max_allowed:.0f} mg/day to minimize organ toxicity in this geriatric patient (Age {age})."
                    })

        return warnings

    def evaluate_regimen(self, medicine_entries: List[Any], declared_allergies: str = "", patient_age: int = 72) -> Dict[str, Any]:
        """
        Full Comprehensive Safety Check Pipeline.
        1. Normalizes medicine entries
        2. Detects duplicate active ingredients
        3. Screens for Drug-Drug Interactions
        4. Cross-references patient allergies
        5. Computes cumulative elderly daily doses
        """
        normalized_meds = [self.reconciliation_engine.normalize_medicine(m) for m in medicine_entries]

        # 1. Intra-regimen duplicates
        duplicate_alerts = self.reconciliation_engine.check_internal_duplicates(normalized_meds)

        # 2. Drug-Drug Interactions
        ddi_alerts = self.check_drug_interactions(normalized_meds)

        # 3. Allergy Screening
        allergy_alerts = self.check_allergies(normalized_meds, declared_allergies)

        # 4. Elderly Dose Limits
        dose_alerts = self.check_geriatric_dose_limits(normalized_meds, patient_age)

        # Aggregate counts
        high_severity_count = (
            sum(1 for a in ddi_alerts if a['severity'] == 'HIGH') +
            len(allergy_alerts) +
            len(duplicate_alerts) +
            sum(1 for d in dose_alerts if d['severity'] == 'HIGH')
        )

        moderate_severity_count = sum(1 for a in ddi_alerts if a['severity'] == 'MODERATE')
        low_severity_count = sum(1 for a in ddi_alerts if a['severity'] == 'LOW')

        total_issues = len(ddi_alerts) + len(allergy_alerts) + len(duplicate_alerts) + len(dose_alerts)

        if high_severity_count > 0:
            status_label = "High Risk - Immediate Attention Required"
            status_badge = "danger"
        elif moderate_severity_count > 0:
            status_label = "Moderate Risk - Monitoring Advised"
            status_badge = "warning"
        elif total_issues > 0:
            status_label = "Low Clinical Risk"
            status_badge = "info"
        else:
            status_label = "No Interactions or Safety Conflicts Detected"
            status_badge = "success"

        return {
            'patient_info': {
                'age': patient_age,
                'declared_allergies': declared_allergies
            },
            'summary': {
                'total_medications': len(normalized_meds),
                'total_alerts': total_issues,
                'high_severity_count': high_severity_count,
                'moderate_severity_count': moderate_severity_count,
                'low_severity_count': low_severity_count,
                'has_critical_alerts': high_severity_count > 0,
                'status_label': status_label,
                'status_badge': status_badge
            },
            'alerts': {
                'drug_interactions': ddi_alerts,
                'allergies': allergy_alerts,
                'duplicate_ingredients': duplicate_alerts,
                'geriatric_dose_limits': dose_alerts
            },
            'normalized_medications': normalized_meds
        }
