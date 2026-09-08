# database/db.py
# MediSafe AI - Local SQLite Database Layer
# Note: All patient data is stored locally in SQLite to guarantee patient privacy.
# No cloud upload is performed.

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(DB_DIR, "medisafe.db")

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Patients table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT,
        known_allergies TEXT DEFAULT '',
        medical_conditions TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Prescriptions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        visit_type TEXT NOT NULL,
        visit_date TEXT,
        doctor_name TEXT,
        hospital_name TEXT,
        items_json TEXT NOT NULL,
        raw_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    )
    """)

    # Reconciliation history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reconciliation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        old_label TEXT,
        new_label TEXT,
        summary_json TEXT NOT NULL,
        details_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    )
    """)

    # Medication schedules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medication_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        raw_name TEXT NOT NULL,
        brand_name TEXT NOT NULL,
        generic_name TEXT NOT NULL,
        strength REAL,
        unit TEXT,
        frequency_code TEXT,
        timing_code TEXT,
        is_chronic BOOLEAN,
        duration_days INTEGER,
        start_date TEXT,
        end_date TEXT,
        instructions TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    )
    """)

    # Adherence logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS adherence_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        medicine_name TEXT NOT NULL,
        slot_name TEXT NOT NULL,
        scheduled_date TEXT NOT NULL,
        status TEXT NOT NULL, -- 'TAKEN', 'MISSED', 'SKIPPED'
        logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    )
    """)

    # Insert default elderly demo patient if empty
    cursor.execute("SELECT COUNT(*) FROM patients")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO patients (name, age, gender, known_allergies, medical_conditions)
        VALUES (?, ?, ?, ?, ?)
        """, (
            "Ramaswamy K.", 
            72, 
            "Male", 
            "Penicillin, Sulfa drugs", 
            "Hypertension, Type-2 Diabetes Mellitus, Mild Osteoarthritis"
        ))

    conn.commit()
    conn.close()

def save_reconciliation_record(patient_id: Optional[int], old_label: str, new_label: str, result: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO reconciliation_history (patient_id, old_label, new_label, summary_json, details_json)
    VALUES (?, ?, ?, ?, ?)
    """, (
        patient_id or 1,
        old_label,
        new_label,
        json.dumps(result['summary']),
        json.dumps(result)
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id

def get_reconciliation_history(limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, old_label, new_label, summary_json, created_at
    FROM reconciliation_history
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    history = []
    for r in rows:
        history.append({
            'id': r['id'],
            'old_label': r['old_label'],
            'new_label': r['new_label'],
            'summary': json.loads(r['summary_json']),
            'created_at': r['created_at']
        })
    conn.close()
    return history

def save_medication_schedules(patient_id: int, items: List[Dict[str, Any]]):
    """Saves or replaces active medication schedule items for a patient."""
    conn = get_connection()
    cursor = conn.cursor()
    # Clear existing schedule for this patient
    cursor.execute("DELETE FROM medication_schedules WHERE patient_id = ?", (patient_id,))
    for item in items:
        cursor.execute("""
        INSERT INTO medication_schedules (
            patient_id, raw_name, brand_name, generic_name, strength, unit,
            frequency_code, timing_code, is_chronic, duration_days, start_date, end_date, instructions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_id,
            item['raw_name'],
            item['brand_name'],
            item['generic_name'],
            item.get('strength'),
            item.get('unit', 'mg'),
            item.get('frequency', 'OD'),
            item.get('timing', 'after_food'),
            1 if item.get('is_chronic', True) else 0,
            item.get('duration_days'),
            item.get('start_date'),
            item.get('end_date'),
            item.get('instructions', '')
        ))
    conn.commit()
    conn.close()

def get_patient_schedules(patient_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM medication_schedules WHERE patient_id = ? ORDER BY id ASC
    """, (patient_id,))
    rows = cursor.fetchall()
    schedules = [dict(r) for r in rows]
    conn.close()
    return schedules

def log_adherence_event(patient_id: int, medicine_name: str, slot_name: str, scheduled_date: str, status: str, notes: str = "") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    # Remove existing log for this exact dose on this date if previously recorded
    cursor.execute("""
    DELETE FROM adherence_logs
    WHERE patient_id = ? AND medicine_name = ? AND slot_name = ? AND scheduled_date = ?
    """, (patient_id, medicine_name, slot_name, scheduled_date))
    cursor.execute("""
    INSERT INTO adherence_logs (patient_id, medicine_name, slot_name, scheduled_date, status, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (patient_id, medicine_name, slot_name, scheduled_date, status, notes))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_adherence_logs_for_date(patient_id: int, scheduled_date: str) -> Dict[str, str]:
    """Returns a dict of {(medicine_name, slot_name): status} for the date."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT medicine_name, slot_name, status FROM adherence_logs
    WHERE patient_id = ? AND scheduled_date = ?
    """, (patient_id, scheduled_date))
    rows = cursor.fetchall()
    lookup = {f"{r['medicine_name']}|||{r['slot_name']}": r['status'] for r in rows}
    conn.close()
    return lookup

def get_adherence_rate(patient_id: int, days: int = 7) -> Dict[str, Any]:
    """Calculates compliance percentage over recent days."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT status, COUNT(*) as count FROM adherence_logs
    WHERE patient_id = ?
    GROUP BY status
    """, (patient_id,))
    rows = cursor.fetchall()
    counts = {r['status']: r['count'] for r in rows}
    total = sum(counts.values())
    taken = counts.get('TAKEN', 0)
    rate = round((taken / total * 100), 1) if total > 0 else 100.0
    conn.close()
    return {
        'total_logged': total,
        'taken_count': taken,
        'missed_count': counts.get('MISSED', 0),
        'skipped_count': counts.get('SKIPPED', 0),
        'adherence_percentage': rate
    }

