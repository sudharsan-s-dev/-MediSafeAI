# core/reconciliation.py
# MediSafe AI - Module 1: Medication Reconciliation Engine
# Academic Prototype for Elderly Patients
# Decision-Support Only: Does not replace professional medical judgment.

import re
import os
import json
import difflib
from typing import List, Dict, Any, Optional

class ReconciliationEngine:
    """
    Medication Reconciliation Engine for MediSafe AI.
    Maps brand names to generic active ingredients and reconciles
    old vs new prescription regimens into SAME, CHANGED, DISCONTINUED, NEW, and DUPLICATE.
    """

    COMMON_PREFIXES = re.compile(r'^(tab|tablet|cap|capsule|syr|syrup|inj|injection|oint|ointment|susp|suspension|drop|drops)\b\.?\s*', re.IGNORECASE)

    FREQ_PATTERNS = [
        (re.compile(r'\b(1-0-1|bd|bid|twice daily|2 times a day|two times daily)\b', re.IGNORECASE), 'BD', 2.0, 'Twice daily (morning and night)'),
        (re.compile(r'\b(1-1-1|tds|tid|thrice daily|3 times a day|three times daily)\b', re.IGNORECASE), 'TDS', 3.0, 'Three times daily (morning, afternoon, night)'),
        (re.compile(r'\b(1-1-1-1|qid|4 times a day|four times daily)\b', re.IGNORECASE), 'QID', 4.0, 'Four times daily'),
        (re.compile(r'\b(1-0-0|morning only|once daily in morning)\b', re.IGNORECASE), 'OD-M', 1.0, 'Once daily in the morning'),
        (re.compile(r'\b(0-0-1|hs|bedtime|night only|at night|before sleeping)\b', re.IGNORECASE), 'HS', 1.0, 'Once daily at bedtime'),
        (re.compile(r'\b(0-1-0|afternoon only)\b', re.IGNORECASE), 'OD-A', 1.0, 'Once daily in the afternoon'),
        (re.compile(r'\b(od|once daily|once a day|daily|1 time a day)\b', re.IGNORECASE), 'OD', 1.0, 'Once daily'),
        (re.compile(r'\b(prn|sos|as needed|when required|if needed)\b', re.IGNORECASE), 'PRN', 0.0, 'As needed (SOS)'),
        (re.compile(r'\b(qod|alternate day|every other day)\b', re.IGNORECASE), 'QOD', 0.5, 'Every alternate day'),
    ]

    TIMING_PATTERNS = [
        (re.compile(r'\b(after food|after meal|pc|post cibum|post meal)\b', re.IGNORECASE), 'after_food', 'After food'),
        (re.compile(r'\b(before food|before meal|ac|ante cibum|empty stomach)\b', re.IGNORECASE), 'before_food', 'Before food / empty stomach'),
        (re.compile(r'\b(with food|with meal)\b', re.IGNORECASE), 'with_food', 'With food'),
        (re.compile(r'\b(at bedtime|before sleep|night)\b', re.IGNORECASE), 'bedtime', 'At bedtime'),
    ]

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, 'data', 'brand_generic_db.json')
        
        self.db_path = db_path
        self.catalog = self._load_catalog(db_path)
        self.brand_lookup = self._build_brand_lookup()

    def _load_catalog(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)

    def _build_brand_lookup(self) -> Dict[str, str]:
        lookup = {}
        for generic_key, details in self.catalog.items():
            lookup[generic_key.lower()] = generic_key.lower()
            for brand in details.get('brands', []):
                lookup[brand.lower()] = generic_key.lower()
        return lookup

    def clean_drug_name(self, name: str) -> str:
        """Strips common prescription prefixes (Tab, Cap, etc.), parenthesized notes, and dosages."""
        cleaned = self.COMMON_PREFIXES.sub('', name.strip())
        cleaned = re.sub(r'\(.*?\)', '', cleaned)
        cleaned = re.sub(r'\s*\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu)?\b', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def match_brand_to_generic(self, raw_name: str) -> Dict[str, Any]:
        """
        Resolves brand or generic string to canonical active ingredient(s).
        Uses exact alias match first, followed by token match and difflib fuzzy matching.
        """
        cleaned = self.clean_drug_name(raw_name).lower()
        
        # 1. Exact match in brand lookup
        if cleaned in self.brand_lookup:
            generic_key = self.brand_lookup[cleaned]
            details = self.catalog[generic_key]
            return {
                'matched': True,
                'canonical_generic': generic_key,
                'matched_brand': cleaned.title(),
                'ingredients': details.get('ingredients', [generic_key]),
                'drug_class': details.get('drug_class', 'General Medication'),
                'is_combination': len(details.get('ingredients', [])) > 1,
                'default_unit': details.get('default_unit', 'mg'),
                'match_confidence': 1.0,
                'matched_via': 'exact'
            }

        # 2. Token sub-match
        tokens = re.findall(r'[a-zA-Z]+', cleaned)
        for t in tokens:
            if t in self.brand_lookup:
                generic_key = self.brand_lookup[t]
                details = self.catalog[generic_key]
                return {
                    'matched': True,
                    'canonical_generic': generic_key,
                    'matched_brand': t.title(),
                    'ingredients': details.get('ingredients', [generic_key]),
                    'drug_class': details.get('drug_class', 'General Medication'),
                    'is_combination': len(details.get('ingredients', [])) > 1,
                    'default_unit': details.get('default_unit', 'mg'),
                    'match_confidence': 0.95,
                    'matched_via': f'token_match ({t})'
                }

        # 3. Fuzzy match against brand and generic catalog
        all_candidates = list(self.brand_lookup.keys())
        matches = difflib.get_close_matches(cleaned, all_candidates, n=1, cutoff=0.75)
        if matches:
            best_match = matches[0]
            ratio = difflib.SequenceMatcher(None, cleaned, best_match).ratio()
            generic_key = self.brand_lookup[best_match]
            details = self.catalog[generic_key]
            return {
                'matched': True,
                'canonical_generic': generic_key,
                'matched_brand': best_match.title(),
                'ingredients': details.get('ingredients', [generic_key]),
                'drug_class': details.get('drug_class', 'General Medication'),
                'is_combination': len(details.get('ingredients', [])) > 1,
                'default_unit': details.get('default_unit', 'mg'),
                'match_confidence': round(ratio, 2),
                'matched_via': f'fuzzy_match ({best_match})'
            }

        # 4. Fallback if not recognized in catalog
        return {
            'matched': False,
            'canonical_generic': cleaned.lower(),
            'ingredients': [cleaned.lower()],
            'drug_class': 'Unclassified / Other',
            'is_combination': False,
            'default_unit': 'mg',
            'match_confidence': 0.5,
            'matched_via': 'unverified_fallback'
        }

    def parse_entry_text(self, text: str) -> Dict[str, Any]:
        """
        Extracts structured fields (strength, unit, frequency, timing, duration)
        from a string (e.g. 'Tab Dolo 650mg 1-0-1 after food for 5 days').
        """
        original_text = text.strip()

        # Extract strength & unit
        strength_val = None
        strength_unit = 'mg'
        strength_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)\b', original_text, re.IGNORECASE)
        if strength_match:
            strength_val = float(strength_match.group(1))
            strength_unit = strength_match.group(2).lower()
        else:
            number_match = re.search(r'\b([A-Za-z]+)\s+(\d{1,4})\b', original_text)
            if number_match:
                strength_val = float(number_match.group(2))
                strength_unit = 'mg'

        # Extract frequency
        freq_code = 'OD'
        freq_per_day = 1.0
        freq_label = 'Once daily'
        for pat, code, count, label in self.FREQ_PATTERNS:
            if pat.search(original_text):
                freq_code = code
                freq_per_day = count
                freq_label = label
                break

        # Extract timing
        timing_code = 'after_food'
        timing_label = 'After food'
        for pat, code, label in self.TIMING_PATTERNS:
            if pat.search(original_text):
                timing_code = code
                timing_label = label
                break

        # Extract duration
        duration = 'Ongoing / Chronic'
        dur_match = re.search(r'\b(?:for\s+)?(\d+\s*(?:days?|weeks?|months?))\b', original_text, re.IGNORECASE)
        if dur_match:
            duration = dur_match.group(1)
        elif re.search(r'\b(sos|prn|as needed)\b', original_text, re.IGNORECASE):
            duration = 'As needed'

        # Extract candidate name
        name_candidate = original_text
        if dur_match:
            name_candidate = name_candidate.replace(dur_match.group(0), '')
        for pat, _, _, _ in self.FREQ_PATTERNS:
            name_candidate = pat.sub('', name_candidate)
        for pat, _, _ in self.TIMING_PATTERNS:
            name_candidate = pat.sub('', name_candidate)
        name_candidate = re.sub(r'\bfor\b', '', name_candidate, flags=re.IGNORECASE)
        name_candidate = self.clean_drug_name(name_candidate)

        return {
            'candidate_name': name_candidate,
            'strength': strength_val,
            'unit': strength_unit,
            'frequency': freq_code,
            'frequency_per_day': freq_per_day,
            'frequency_label': freq_label,
            'timing': timing_code,
            'timing_label': timing_label,
            'duration': duration
        }

    def normalize_medicine(self, item: Any) -> Dict[str, Any]:
        """
        Converts either a raw string or dict into a standardized Medicine record.
        """
        if isinstance(item, str):
            parsed = self.parse_entry_text(item)
            raw_name = item
            brand_candidate = parsed['candidate_name']
            strength = parsed['strength']
            unit = parsed['unit']
            freq = parsed['frequency']
            freq_per_day = parsed['frequency_per_day']
            freq_label = parsed['frequency_label']
            timing = parsed['timing']
            timing_label = parsed['timing_label']
            duration = parsed['duration']
            instructions = ''
        elif isinstance(item, dict):
            raw_name = item.get('raw_name') or item.get('name', '')
            parsed = self.parse_entry_text(raw_name)
            brand_candidate = item.get('brand_name') or parsed['candidate_name']
            strength = float(item.get('strength')) if item.get('strength') is not None else parsed['strength']
            unit = item.get('unit') or parsed['unit']
            freq = item.get('frequency') or parsed['frequency']
            freq_per_day = float(item.get('frequency_per_day', 0.0)) or parsed['frequency_per_day']
            freq_label = item.get('frequency_label') or parsed['frequency_label']
            timing = item.get('timing') or parsed['timing']
            timing_label = item.get('timing_label') or parsed['timing_label']
            duration = item.get('duration') or parsed['duration']
            instructions = item.get('instructions', '')
        else:
            raise ValueError(f'Unsupported medicine item type: {type(item)}')

        match_info = self.match_brand_to_generic(brand_candidate or raw_name)

        if strength is None:
            cat_details = self.catalog.get(match_info['canonical_generic'])
            if cat_details and cat_details.get('common_strengths'):
                strength = float(cat_details['common_strengths'][0])
                unit = cat_details.get('default_unit', 'mg')

        return {
            'raw_name': raw_name,
            'brand_name': match_info.get('matched_brand') or self.clean_drug_name(brand_candidate or raw_name).title(),
            'generic_name': match_info['canonical_generic'],
            'display_generic': match_info['canonical_generic'].title(),
            'ingredients': match_info['ingredients'],
            'is_combination': match_info['is_combination'],
            'drug_class': match_info['drug_class'],
            'form': 'Tablet',
            'strength': strength,
            'unit': unit or 'mg',
            'frequency': freq,
            'frequency_per_day': freq_per_day,
            'frequency_label': freq_label,
            'timing': timing,
            'timing_label': timing_label,
            'duration': duration,
            'instructions': instructions,
            'match_confidence': match_info['match_confidence'],
            'matched_via': match_info['matched_via']
        }

    def check_internal_duplicates(self, medicine_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans a list for multiple medicines containing identical active ingredients.
        """
        ingredient_map = {}
        for med in medicine_list:
            for ing in med['ingredients']:
                ing_lower = ing.lower()
                if ing_lower not in ingredient_map:
                    ingredient_map[ing_lower] = []
                ingredient_map[ing_lower].append(med)

        duplicates = []
        for ing, items in ingredient_map.items():
            if len(items) > 1:
                names = [f"{i['brand_name']} ({i['strength']}{i['unit']})" for i in items]
                duplicates.append({
                    'ingredient': ing.title(),
                    'medicines': [i['raw_name'] for i in items],
                    'items': items,
                    'warning': f"High Risk of Duplicate Therapy: Multiple medicines ({', '.join(names)}) share the active ingredient '{ing.title()}'. This can lead to accidental overdose."
                })
        return duplicates

    def reconcile(self, old_regimen: List[Any], new_regimen: List[Any]) -> Dict[str, Any]:
        """
        Reconciles old vs new prescriptions by generic ingredient(s).
        Returns categorized discrepancies and actionable notes.
        """
        norm_old = [self.normalize_medicine(m) for m in old_regimen]
        norm_new = [self.normalize_medicine(m) for m in new_regimen]

        new_internal_dups = self.check_internal_duplicates(norm_new)

        old_map: Dict[str, List[Dict[str, Any]]] = {}
        for item in norm_old:
            key = item['generic_name']
            if key not in old_map:
                old_map[key] = []
            old_map[key].append(item)

        new_map: Dict[str, List[Dict[str, Any]]] = {}
        for item in norm_new:
            key = item['generic_name']
            if key not in new_map:
                new_map[key] = []
            new_map[key].append(item)

        discrepancies = []
        handled_new_keys = set()

        # Compare old items against new
        for generic_key, old_items in old_map.items():
            if generic_key in new_map:
                handled_new_keys.add(generic_key)
                new_items = new_map[generic_key]

                if len(new_items) > 1:
                    discrepancies.append({
                        'category': 'DUPLICATE',
                        'generic_name': generic_key.title(),
                        'drug_class': new_items[0]['drug_class'],
                        'old_entry': old_items[0],
                        'new_entry': new_items,
                        'change_details': {
                            'brand_change': 'Multiple medicines share the same active ingredient'
                        },
                        'clinical_note': f"🚨 CRITICAL DUPLICATE: Active ingredient '{generic_key.title()}' is prescribed multiple times in your new regimen. Consult your doctor before taking."
                    })
                    continue

                old_item = old_items[0]
                new_item = new_items[0]

                strength_same = (old_item['strength'] == new_item['strength']) and (old_item['unit'] == new_item['unit'])
                freq_same = (old_item['frequency_per_day'] == new_item['frequency_per_day'])
                brand_same = (old_item['brand_name'].strip().lower() == new_item['brand_name'].strip().lower())

                if strength_same and freq_same:
                    if not brand_same:
                        discrepancies.append({
                            'category': 'CHANGED',
                            'generic_name': generic_key.title(),
                            'drug_class': new_item['drug_class'],
                            'old_entry': old_item,
                            'new_entry': new_item,
                            'change_details': {
                                'strength_change': None,
                                'frequency_change': None,
                                'brand_change': f"Brand substituted: {old_item['brand_name']} -> {new_item['brand_name']}"
                            },
                            'clinical_note': f"ℹ️ Brand Substitution: Switched from '{old_item['brand_name']}' to '{new_item['brand_name']}'. The active ingredient remains {generic_key.title()} ({new_item['strength']}{new_item['unit']}). Do NOT take both."
                        })
                    else:
                        discrepancies.append({
                            'category': 'SAME',
                            'generic_name': generic_key.title(),
                            'drug_class': new_item['drug_class'],
                            'old_entry': old_item,
                            'new_entry': new_item,
                            'change_details': None,
                            'clinical_note': f"✅ Continue: Keep taking {new_item['brand_name']} ({new_item['strength']}{new_item['unit']}) {new_item['frequency_label'].lower()} {new_item['timing_label'].lower()} as before."
                        })
                else:
                    strength_diff = None
                    if not strength_same:
                        if old_item['strength'] and new_item['strength']:
                            if new_item['strength'] > old_item['strength']:
                                strength_diff = f"Dose increased: {old_item['strength']}{old_item['unit']} -> {new_item['strength']}{new_item['unit']}"
                            else:
                                strength_diff = f"Dose decreased: {old_item['strength']}{old_item['unit']} -> {new_item['strength']}{new_item['unit']}"
                        else:
                            strength_diff = f"Dose updated to {new_item['strength']}{new_item['unit']}"

                    freq_diff = None
                    if not freq_same:
                        freq_diff = f"Frequency changed: {old_item['frequency_label']} -> {new_item['frequency_label']}"

                    brand_diff = None
                    if not brand_same:
                        brand_diff = f"Brand: {old_item['brand_name']} -> {new_item['brand_name']}"

                    notes = [n for n in [strength_diff, freq_diff, brand_diff] if n]
                    discrepancies.append({
                        'category': 'CHANGED',
                        'generic_name': generic_key.title(),
                        'drug_class': new_item['drug_class'],
                        'old_entry': old_item,
                        'new_entry': new_item,
                        'change_details': {
                            'strength_change': strength_diff,
                            'frequency_change': freq_diff,
                            'brand_change': brand_diff
                        },
                        'clinical_note': f"⚠️ Prescription Modified: {'; '.join(notes)}. Follow the updated directions."
                    })
            else:
                for old_item in old_items:
                    discrepancies.append({
                        'category': 'DISCONTINUED',
                        'generic_name': generic_key.title(),
                        'drug_class': old_item['drug_class'],
                        'old_entry': old_item,
                        'new_entry': None,
                        'change_details': {
                            'action': 'STOP'
                        },
                        'clinical_note': f"🛑 STOP TAKING: {old_item['brand_name']} ({old_item['generic_name'].title()} {old_item['strength']}{old_item['unit']}) was NOT renewed in your new prescription."
                    })

        # Check for NEW items
        for generic_key, new_items in new_map.items():
            if generic_key not in handled_new_keys:
                if len(new_items) > 1:
                    discrepancies.append({
                        'category': 'DUPLICATE',
                        'generic_name': generic_key.title(),
                        'drug_class': new_items[0]['drug_class'],
                        'old_entry': None,
                        'new_entry': new_items,
                        'change_details': {
                            'brand_change': 'Multiple duplicate brands added'
                        },
                        'clinical_note': f"🚨 CRITICAL DUPLICATE: Active ingredient '{generic_key.title()}' appears multiple times in the new prescription. Clarify with doctor."
                    })
                else:
                    new_item = new_items[0]
                    discrepancies.append({
                        'category': 'NEW',
                        'generic_name': generic_key.title(),
                        'drug_class': new_item['drug_class'],
                        'old_entry': None,
                        'new_entry': new_item,
                        'change_details': {
                            'action': 'START'
                        },
                        'clinical_note': f"✨ START NEW: {new_item['brand_name']} ({new_item['generic_name'].title()} {new_item['strength']}{new_item['unit']}), {new_item['frequency_label'].lower()} {new_item['timing_label'].lower()}."
                    })

        counts = {
            'SAME': sum(1 for d in discrepancies if d['category'] == 'SAME'),
            'CHANGED': sum(1 for d in discrepancies if d['category'] == 'CHANGED'),
            'DISCONTINUED': sum(1 for d in discrepancies if d['category'] == 'DISCONTINUED'),
            'NEW': sum(1 for d in discrepancies if d['category'] == 'NEW'),
            'DUPLICATE': sum(1 for d in discrepancies if d['category'] == 'DUPLICATE') + len(new_internal_dups)
        }

        return {
            'summary': {
                'total_old_medicines': len(norm_old),
                'total_new_medicines': len(norm_new),
                'same_count': counts['SAME'],
                'changed_count': counts['CHANGED'],
                'discontinued_count': counts['DISCONTINUED'],
                'new_count': counts['NEW'],
                'duplicate_count': counts['DUPLICATE'],
                'has_critical_alerts': counts['DUPLICATE'] > 0 or counts['DISCONTINUED'] > 0
            },
            'discrepancies': discrepancies,
            'internal_duplicates': new_internal_dups,
            'normalized_old': norm_old,
            'normalized_new': norm_new
        }
