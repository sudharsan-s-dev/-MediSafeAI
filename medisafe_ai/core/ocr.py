import os
import json
import re
import shutil
from pathlib import Path

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    import pytesseract
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent.parent
BRAND_DB_PATH = BASE_DIR / "data" / "brand_generic_db.json"
SAMPLE_DIR = BASE_DIR / "data" / "sample_prescriptions"

FREQUENCY_MAP = {
    "od": ("once daily", "Morning"),
    "once daily": ("once daily", "Morning"),
    "qd": ("once daily", "Morning"),
    "bd": ("twice daily", "Morning, Evening"),
    "bid": ("twice daily", "Morning, Evening"),
    "twice daily": ("twice daily", "Morning, Evening"),
    "tds": ("thrice daily", "Morning, Afternoon, Evening"),
    "tid": ("thrice daily", "Morning, Afternoon, Evening"),
    "thrice daily": ("thrice daily", "Morning, Afternoon, Evening"),
    "three times": ("thrice daily", "Morning, Afternoon, Evening"),
    "qid": ("four times daily", "Morning, Afternoon, Evening, Night"),
    "four times": ("four times daily", "Morning, Afternoon, Evening, Night"),
    "hs": ("at bedtime", "Night"),
    "bedtime": ("at bedtime", "Night"),
    "nocte": ("at bedtime", "Night"),
    "prn": ("as needed", "SOS"),
    "sos": ("as needed", "SOS"),
    "as needed": ("as needed", "SOS"),
    "stat": ("immediately", "SOS"),
    "ac": ("before meals", "Before meals"),
    "pc": ("after meals", "After meals"),
    "before meals": ("before meals", "Before meals"),
    "after meals": ("after meals", "After meals"),
}

TIMING_PATTERNS = [
    (r'\bac\b', 'before meals'),
    (r'\bpc\b', 'after meals'),
    (r'before\s+meal', 'before meals'),
    (r'after\s+meal', 'after meals'),
    (r'with\s+meal', 'with meals'),
    (r'empty\s+stomach', 'empty stomach'),
    (r'hs\b', 'at bedtime'),
    (r'bedtime', 'at bedtime'),
]

DURATION_PATTERN = re.compile(
    r'(\d+)\s*'
    r'(day|days|week|weeks|month|months|year|years)',
    re.IGNORECASE
)

STRENGTH_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(mg|mcg|ug|g|ml|iu|mmol|mEq|%)',
    re.IGNORECASE
)

NOISE_LINES = re.compile(
    r'^(date|patient|name|age|sex|gender|address|phone|tel|rx|rp|doctor|dr\.|clinic|hospital|'
    r'signature|stamp|ref|refill|dispensed|pharmacy|weight|bp|diagnosis|advice|follow|review|'
    r'next\s+visit|prescribed\s+by|print|page|\s*[-=_*#]+\s*)$',
    re.IGNORECASE
)


class PrescriptionOCREngine:
    """
    Prescription OCR engine with graceful Tesseract fallback.
    When Tesseract is unavailable, uses pre-defined sample extractions for demo.
    """

    def __init__(self):
        self.brand_catalog = self._load_brand_catalog()
        self.tesseract_available = TESSERACT_AVAILABLE
        self.cv2_available = CV2_AVAILABLE

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_brand_catalog(self) -> dict:
        """Load brand-generic mapping from JSON catalog.
        The catalog is a flat dict keyed by generic name, each value has:
          generic_name, drug_class, brands (list of brand name strings).
        """
        try:
            with open(BRAND_DB_PATH, encoding='utf-8-sig') as f:
                data = json.load(f)
            catalog = {}
            for generic_key, family in data.items():
                generic = family.get('generic_name', generic_key).lower()
                drug_class = family.get('drug_class', '')
                # Add brand name entries
                for brand in family.get('brands', []):
                    catalog[brand.lower()] = {
                        'generic': generic,
                        'drug_class': drug_class,
                        'brand_name': brand.title(),
                    }
                # Add generic name entry (title-cased)
                catalog[generic] = {
                    'generic': generic,
                    'drug_class': drug_class,
                    'brand_name': generic.title(),
                }
            return catalog
        except Exception:
            return {}

    def _parse_strength(self, text: str):
        m = STRENGTH_PATTERN.search(text)
        if m:
            return m.group(1), m.group(2).lower()
        return None, None

    def _parse_frequency(self, text: str):
        lower = text.lower()
        for key, (label, timing) in FREQUENCY_MAP.items():
            if re.search(r'\b' + re.escape(key) + r'\b', lower):
                return label, timing
        return None, None

    def _parse_timing(self, text: str):
        lower = text.lower()
        for pattern, label in TIMING_PATTERNS:
            if re.search(pattern, lower, re.IGNORECASE):
                return label
        return None

    def _parse_duration(self, text: str):
        m = DURATION_PATTERN.search(text)
        if m:
            count = m.group(1)
            unit = m.group(2).lower()
            # Normalize to plural form
            if not unit.endswith('s'):
                unit = unit + 's'
            return f"{count} {unit}"
        return None

    def _match_drug(self, text: str):
        """Return (brand_name, generic_name, drug_class, confidence) or None."""
        lower = text.lower()
        # Exact match
        for key, info in self.brand_catalog.items():
            pattern = r'\b' + re.escape(key) + r'\b'
            if re.search(pattern, lower):
                conf = 0.9 if len(key) > 5 else 0.7
                return info['brand_name'], info['generic'], info['drug_class'], conf
        return None, None, None, 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def preprocess_image(self, image_path: str):
        """
        OpenCV pipeline: grayscale -> bilateral filter -> CLAHE -> Otsu binarization.
        Returns numpy array or None if cv2 unavailable.
        """
        if not self.cv2_available:
            return None
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(bilateral)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    def extract_text(self, image_path: str) -> list:
        """
        Extract raw text lines from a prescription image using Tesseract.
        Falls back gracefully to [] if Tesseract is unavailable.
        """
        if not self.tesseract_available:
            return []
        try:
            preprocessed = self.preprocess_image(image_path)
            if preprocessed is not None:
                pil_img = Image.fromarray(preprocessed)
            else:
                pil_img = Image.open(image_path)
            config = '--oem 3 --psm 6'
            raw_text = pytesseract.image_to_string(pil_img, config=config)
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            return lines
        except Exception:
            return []

    def parse_lines(self, lines: list) -> list:
        """
        Parse raw OCR text lines into structured medicine records.
        Returns list of dicts with keys:
          raw_line, extracted_brand, extracted_generic, drug_class,
          strength, unit, frequency, frequency_label, timing, duration,
          confidence_score, requires_review
        """
        results = []
        for line in lines:
            # Skip obvious noise / header lines
            if NOISE_LINES.match(line.strip()):
                continue
            if len(line.strip()) < 4:
                continue

            brand, generic, drug_class, conf = self._match_drug(line)
            strength, unit = self._parse_strength(line)
            freq, freq_label = self._parse_frequency(line)
            timing = self._parse_timing(line)
            duration = self._parse_duration(line)

            # Only include lines that have at least a drug match OR strength
            if brand is None and strength is None:
                continue

            requires_review = (
                conf < 0.75
                or brand is None
                or freq is None
            )

            results.append({
                'raw_line': line,
                'extracted_brand': brand or '',
                'extracted_generic': generic or '',
                'drug_class': drug_class or '',
                'strength': strength or '',
                'unit': unit or '',
                'frequency': freq or '',
                'frequency_label': freq_label or '',
                'timing': timing or '',
                'duration': duration or '',
                'confidence_score': round(conf, 2),
                'requires_review': requires_review,
            })
        return results

    def extract_from_sample(self, sample_name: str) -> dict:
        """
        Demo mode: returns pre-defined structured extractions when Tesseract is absent.
        """
        samples = {
            'sample_cardiac_clinic': {
                'image_path': str(SAMPLE_DIR / 'sample_cardiac_clinic.png'),
                'clinic_name': 'Cardiac Care Clinic',
                'patient_name': 'Ramaswamy K.',
                'patient_age': '72',
                'patient_sex': 'Male',
                'date': '08-Sep-2026',
                'medicines': [
                    {
                        'raw_line': 'Tab. Amlodipine 5mg OD AC',
                        'extracted_brand': 'Amlodipine',
                        'extracted_generic': 'amlodipine',
                        'drug_class': 'Calcium Channel Blocker',
                        'strength': '5',
                        'unit': 'mg',
                        'frequency': 'once daily',
                        'frequency_label': 'Morning',
                        'timing': 'before meals',
                        'duration': '30 days',
                        'confidence_score': 0.92,
                        'requires_review': False,
                    },
                    {
                        'raw_line': 'Tab. Atorvastatin 20mg HS',
                        'extracted_brand': 'Atorvastatin',
                        'extracted_generic': 'atorvastatin',
                        'drug_class': 'Statin',
                        'strength': '20',
                        'unit': 'mg',
                        'frequency': 'at bedtime',
                        'frequency_label': 'Night',
                        'timing': 'at bedtime',
                        'duration': '90 days',
                        'confidence_score': 0.95,
                        'requires_review': False,
                    },
                    {
                        'raw_line': 'Tab. Metoprolol 25mg BD PC',
                        'extracted_brand': 'Metoprolol',
                        'extracted_generic': 'metoprolol',
                        'drug_class': 'Beta Blocker',
                        'strength': '25',
                        'unit': 'mg',
                        'frequency': 'twice daily',
                        'frequency_label': 'Morning, Evening',
                        'timing': 'after meals',
                        'duration': '30 days',
                        'confidence_score': 0.91,
                        'requires_review': False,
                    },
                    {
                        'raw_line': 'Tab. Warfarin 2mg OD',
                        'extracted_brand': 'Warfarin',
                        'extracted_generic': 'warfarin',
                        'drug_class': 'Anticoagulant',
                        'strength': '2',
                        'unit': 'mg',
                        'frequency': 'once daily',
                        'frequency_label': 'Morning',
                        'timing': '',
                        'duration': '30 days',
                        'confidence_score': 0.90,
                        'requires_review': False,
                    },
                ],
                'raw_lines': [
                    'CARDIAC CARE CLINIC',
                    'Patient: Ramaswamy K.    Age: 72   Sex: M',
                    'Date: 08-Sep-2026',
                    'Tab. Amlodipine 5mg OD AC',
                    'Tab. Atorvastatin 20mg HS',
                    'Tab. Metoprolol 25mg BD PC',
                    'Tab. Warfarin 2mg OD',
                ],
                'ocr_mode': 'demo',
            },
            'sample_discharge_order': {
                'image_path': str(SAMPLE_DIR / 'sample_discharge_order.png'),
                'clinic_name': 'General Hospital Discharge',
                'patient_name': 'Ramaswamy K.',
                'patient_age': '72',
                'patient_sex': 'Male',
                'date': '08-Sep-2026',
                'medicines': [
                    {
                        'raw_line': 'Tab. Metformin 500mg BD PC',
                        'extracted_brand': 'Metformin',
                        'extracted_generic': 'metformin',
                        'drug_class': 'Biguanide',
                        'strength': '500',
                        'unit': 'mg',
                        'frequency': 'twice daily',
                        'frequency_label': 'Morning, Evening',
                        'timing': 'after meals',
                        'duration': '30 days',
                        'confidence_score': 0.93,
                        'requires_review': False,
                    },
                    {
                        'raw_line': 'Tab. Glimepiride 2mg OD AC',
                        'extracted_brand': 'Glimepiride',
                        'extracted_generic': 'glimepiride',
                        'drug_class': 'Sulfonylurea',
                        'strength': '2',
                        'unit': 'mg',
                        'frequency': 'once daily',
                        'frequency_label': 'Morning',
                        'timing': 'before meals',
                        'duration': '30 days',
                        'confidence_score': 0.91,
                        'requires_review': False,
                    },
                    {
                        'raw_line': 'Tab. Losartan 50mg OD',
                        'extracted_brand': 'Losartan',
                        'extracted_generic': 'losartan',
                        'drug_class': 'ARB',
                        'strength': '50',
                        'unit': 'mg',
                        'frequency': 'once daily',
                        'frequency_label': 'Morning',
                        'timing': '',
                        'duration': '30 days',
                        'confidence_score': 0.92,
                        'requires_review': False,
                    },
                    {
                        'raw_line': 'Tab. Aspirin 75mg OD PC - CAUTION: Do not combine with Warfarin',
                        'extracted_brand': 'Aspirin',
                        'extracted_generic': 'aspirin',
                        'drug_class': 'NSAID / Antiplatelet',
                        'strength': '75',
                        'unit': 'mg',
                        'frequency': 'once daily',
                        'frequency_label': 'Morning',
                        'timing': 'after meals',
                        'duration': '30 days',
                        'confidence_score': 0.88,
                        'requires_review': True,
                    },
                    {
                        'raw_line': 'Tab. Ciprofloxacin 500mg BD x 7 days',
                        'extracted_brand': 'Ciprofloxacin',
                        'extracted_generic': 'ciprofloxacin',
                        'drug_class': 'Fluoroquinolone Antibiotic',
                        'strength': '500',
                        'unit': 'mg',
                        'frequency': 'twice daily',
                        'frequency_label': 'Morning, Evening',
                        'timing': '',
                        'duration': '7 days',
                        'confidence_score': 0.90,
                        'requires_review': False,
                    },
                ],
                'raw_lines': [
                    'GENERAL HOSPITAL - DISCHARGE ORDER',
                    'Patient: Ramaswamy K.   Age: 72   Sex: M',
                    'Date: 08-Sep-2026',
                    'Tab. Metformin 500mg BD PC',
                    'Tab. Glimepiride 2mg OD AC',
                    'Tab. Losartan 50mg OD',
                    'Tab. Aspirin 75mg OD PC - CAUTION: Do not combine with Warfarin',
                    'Tab. Ciprofloxacin 500mg BD x 7 days',
                ],
                'ocr_mode': 'demo',
            },
        }
        return samples.get(sample_name, {})

    def get_sample_list(self) -> list:
        """Returns metadata about the available sample prescriptions."""
        return [
            {
                'id': 'sample_cardiac_clinic',
                'label': 'Cardiac Clinic Prescription',
                'description': 'Multi-drug cardiac care (Amlodipine, Atorvastatin, Metoprolol, Warfarin)',
                'image_path': str(SAMPLE_DIR / 'sample_cardiac_clinic.png'),
                'filename': 'sample_cardiac_clinic.png',
                'medicines_count': 4,
                'high_risk': True,
            },
            {
                'id': 'sample_discharge_order',
                'label': 'Hospital Discharge Order',
                'description': 'Discharge poly-pharmacy with DDI risk (Aspirin + Warfarin flag, Ciprofloxacin + Glimepiride flag)',
                'image_path': str(SAMPLE_DIR / 'sample_discharge_order.png'),
                'filename': 'sample_discharge_order.png',
                'medicines_count': 5,
                'high_risk': True,
            },
        ]
