# app.py
# MediSafe AI: AI-Powered Medication Safety, Reconciliation and Adherence System
# Academic Prototype - VET Institute of Arts and Science College
# Developed by: Sudharsan S

import os
import json
from pathlib import Path
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from core.reconciliation import ReconciliationEngine
from core.safety import SafetyEngine
from core.scheduler import SchedulerEngine
from core.ocr import PrescriptionOCREngine
from core.report import ReportGenerator
from database.db import init_db, save_reconciliation_record, get_reconciliation_history, get_adherence_rate

UPLOAD_FOLDER = Path(__file__).parent / 'static' / 'uploads'
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'tiff', 'tif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'medisafe-ai-academic-key-2026'

# Ensure database tables exist
init_db()

# Initialize core engines
reconciliation_engine = ReconciliationEngine()
safety_engine = SafetyEngine()
scheduler_engine = SchedulerEngine()
ocr_engine = PrescriptionOCREngine()
report_generator = ReportGenerator()

@app.route('/')
def index():
    return redirect(url_for('reconcile_view'))

@app.route('/reconcile', methods=['GET', 'POST'])
def reconcile_view():
    result = None
    old_label = "Previous Regimen"
    new_label = "Current Regimen"
    old_text = ""
    new_text = ""

    if request.method == 'POST':
        old_label = request.form.get('old_label', 'Previous Regimen').strip()
        new_label = request.form.get('new_label', 'Current Regimen').strip()
        old_text = request.form.get('old_medicines', '').strip()
        new_text = request.form.get('new_medicines', '').strip()

        old_list = [line.strip() for line in old_text.splitlines() if line.strip()]
        new_list = [line.strip() for line in new_text.splitlines() if line.strip()]

        if old_list or new_list:
            result = reconciliation_engine.reconcile(old_list, new_list)
            # Persist locally in SQLite
            try:
                save_reconciliation_record(
                    patient_id=1,
                    old_label=old_label,
                    new_label=new_label,
                    result=result
                )
            except Exception as e:
                app.logger.error(f"Error saving to SQLite: {e}")

    return render_template(
        'reconcile.html',
        result=result,
        old_label=old_label,
        new_label=new_label,
        old_text=old_text,
        new_text=new_text
    )

@app.route('/api/reconcile', methods=['POST'])
def api_reconcile():
    """
    Programmatic REST API endpoint for medication reconciliation.
    Accepts JSON:
    {
        "old_medicines": ["Tab Telma 20mg 1-0-0", ...],
        "new_medicines": ["Tab Telma 40mg 1-0-0", ...]
    }
    """
    data = request.get_json() or {}
    old_list = data.get('old_medicines', [])
    new_list = data.get('new_medicines', [])

    if not old_list and not new_list:
        return jsonify({'error': 'Please provide old_medicines and/or new_medicines lists.'}), 400

    result = reconciliation_engine.reconcile(old_list, new_list)
    return jsonify({
        'status': 'success',
        'data': result
    })

@app.route('/api/history', methods=['GET'])
def api_history():
    history = get_reconciliation_history(limit=10)
    return jsonify({'status': 'success', 'history': history})

@app.route('/safety', methods=['GET', 'POST'])
def safety_view():
    result = None
    medicines_text = ""
    allergies_text = "Penicillin, Sulfa drugs"
    patient_age = 72

    if request.method == 'POST':
        medicines_text = request.form.get('medicines_input', '').strip()
        allergies_text = request.form.get('allergies_input', '').strip()
        try:
            patient_age = int(request.form.get('patient_age', 72))
        except ValueError:
            patient_age = 72

        meds_list = [line.strip() for line in medicines_text.splitlines() if line.strip()]
        if meds_list:
            result = safety_engine.evaluate_regimen(
                medicine_entries=meds_list,
                declared_allergies=allergies_text,
                patient_age=patient_age
            )

    return render_template(
        'safety.html',
        result=result,
        medicines_text=medicines_text,
        allergies_text=allergies_text,
        patient_age=patient_age
    )

@app.route('/api/safety', methods=['POST'])
def api_safety():
    """
    Programmatic REST API endpoint for safety & DDI checks.
    Accepts JSON:
    {
        "medicines": ["Tab Telma 40mg 1-0-0", ...],
        "declared_allergies": "Penicillin",
        "patient_age": 72
    }
    """
    data = request.get_json() or {}
    meds_list = data.get('medicines', [])
    allergies = data.get('declared_allergies', '')
    age = data.get('patient_age', 72)

    if not meds_list:
        return jsonify({'error': 'Please provide a non-empty medicines list.'}), 400

    result = safety_engine.evaluate_regimen(
        medicine_entries=meds_list,
        declared_allergies=allergies,
        patient_age=age
    )
    return jsonify({
        'status': 'success',
        'data': result
    })

@app.route('/schedule', methods=['GET', 'POST'])
def schedule_view():
    current_date_str = date.today().strftime('%Y-%m-%d')
    target_date_str = current_date_str
    medicines_text = "Tab Telma 40mg 1-0-0 (morning)\nTab Glycomet 500mg 1-0-1 after food\nTab Augmentin 625mg 1-0-1 for 5 days\nTab Atorva 10mg 0-0-1 night\nTab Dolo 650mg SOS"
    timetable = None

    if request.method == 'POST':
        medicines_text = request.form.get('medicines_input', '').strip()
        target_date_str = request.form.get('target_date', current_date_str).strip()

    try:
        target_dt = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        target_dt = date.today()
        target_date_str = current_date_str

    meds_list = [line.strip() for line in medicines_text.splitlines() if line.strip()]
    if meds_list:
        timetable = scheduler_engine.generate_daily_timetable(
            medicines=meds_list,
            target_date=target_dt,
            patient_id=1
        )

    return render_template(
        'schedule.html',
        timetable=timetable,
        medicines_text=medicines_text,
        target_date=target_date_str,
        current_date_str=current_date_str
    )

@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    """
    REST API endpoint for daily schedule generation.
    Accepts JSON:
    {
        "medicines": ["Tab Telma 40mg 1-0-0", ...],
        "target_date": "2026-09-08",
        "patient_id": 1
    }
    """
    data = request.get_json() or {}
    meds_list = data.get('medicines', [])
    target_date_str = data.get('target_date', date.today().strftime('%Y-%m-%d'))
    patient_id = data.get('patient_id', 1)

    if not meds_list:
        return jsonify({'error': 'Please provide a non-empty medicines list.'}), 400

    try:
        target_dt = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        target_dt = date.today()

    timetable = scheduler_engine.generate_daily_timetable(
        medicines=meds_list,
        target_date=target_dt,
        patient_id=patient_id
    )
    return jsonify({
        'status': 'success',
        'data': timetable
    })

@app.route('/api/adherence/log', methods=['POST'])
def api_adherence_log():
    """
    1-Click dose adherence logging endpoint.
    Accepts JSON:
    {
        "patient_id": 1,
        "medicine_name": "Telma",
        "slot_key": "morning",
        "scheduled_date": "2026-09-08",
        "status": "TAKEN" | "MISSED"
    }
    """
    data = request.get_json() or {}
    patient_id = data.get('patient_id', 1)
    medicine_name = data.get('medicine_name', '')
    slot_key = data.get('slot_key', 'morning')
    scheduled_date = data.get('scheduled_date', date.today().strftime('%Y-%m-%d'))
    status = data.get('status', 'TAKEN')

    if not medicine_name:
        return jsonify({'error': 'Medicine name is required.'}), 400

    log_id = scheduler_engine.record_dose_status(
        patient_id=patient_id,
        medicine_name=medicine_name,
        slot_key=slot_key,
        scheduled_date=scheduled_date,
        status=status
    )
    return jsonify({
        'status': 'success',
        'log_id': log_id,
        'medicine': medicine_name,
        'recorded_status': status
    })

@app.route('/api/adherence/stats', methods=['GET'])
def api_adherence_stats():
    patient_id = int(request.args.get('patient_id', 1))
    stats = get_adherence_rate(patient_id, days=7)
    return jsonify({'status': 'success', 'stats': stats})


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — Prescription OCR & Confirmation
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/ocr', methods=['GET'])
def ocr_view():
    """Render the OCR upload and confirmation page."""
    # Build a compact brand list for autocomplete in the template
    brand_catalog = sorted(set(
        info['brand_name']
        for info in ocr_engine.brand_catalog.values()
        if info.get('brand_name')
    ))
    return render_template(
        'ocr_confirm.html',
        samples=ocr_engine.get_sample_list(),
        tesseract_available=ocr_engine.tesseract_available,
        brand_catalog_json=json.dumps(brand_catalog),
    )


@app.route('/api/ocr/extract', methods=['POST'])
def api_ocr_extract():
    """
    Multipart POST — accepts an uploaded prescription image file.
    Runs OpenCV preprocessing + Tesseract OCR.
    Returns structured extraction JSON.
    """
    if not ocr_engine.tesseract_available:
        return jsonify({
            'success': False,
            'error': 'Tesseract OCR is not installed on this server. Please use a sample prescription instead.',
        }), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part in request.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'File type not allowed. Use PNG, JPG, JPEG, TIFF, or BMP.'}), 400

    filename = secure_filename(file.filename)
    save_path = UPLOAD_FOLDER / filename
    file.save(str(save_path))

    lines = ocr_engine.extract_text(str(save_path))
    medicines = ocr_engine.parse_lines(lines)

    return jsonify({
        'success': True,
        'image_url': f'/static/uploads/{filename}',
        'raw_lines': lines,
        'medicines': medicines,
        'ocr_mode': 'live',
        'tesseract_available': True,
    })


@app.route('/api/ocr/sample', methods=['POST'])
def api_ocr_sample():
    """
    POST JSON {"sample_id": "sample_cardiac_clinic"}.
    Returns pre-defined structured extraction for demo mode.
    """
    data = request.get_json() or {}
    sample_id = data.get('sample_id', '')

    if not sample_id:
        return jsonify({'success': False, 'error': 'sample_id is required.'}), 400

    result = ocr_engine.extract_from_sample(sample_id)
    if not result:
        return jsonify({'success': False, 'error': f'Unknown sample: {sample_id}'}), 404

    return jsonify({
        'success': True,
        'image_path': result.get('image_path', ''),
        'raw_lines': result.get('raw_lines', []),
        'medicines': result.get('medicines', []),
        'ocr_mode': result.get('ocr_mode', 'demo'),
        'patient_name': result.get('patient_name', ''),
        'clinic_name': result.get('clinic_name', ''),
        'date': result.get('date', ''),
    })


@app.route('/ocr/image')
def ocr_image_serve():
    """Serve prescription images from data/sample_prescriptions via URL path parameter."""
    path = request.args.get('path', '')
    try:
        p = Path(path).resolve()
        # Security: only serve files from within the project directory
        base = Path(__file__).parent.resolve()
        p.relative_to(base)
        if p.exists() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.tiff', '.bmp'}:
            return send_file(str(p), mimetype='image/png')
    except (ValueError, Exception):
        pass
    return 'Image not found', 404



# ══════════════════════════════════════════════════════════════════════════════
# MODULE 5 — Patient Safety Report Generator
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/report', methods=['GET', 'POST'])
def report_view():
    """Render report input form (GET) or generate and display report (POST)."""
    report = None
    medicines_text = ""
    old_medicines = ""
    declared_allergies = "Penicillin\nSulfa drugs"

    if request.method == 'POST':
        # ── Patient info ─────────────────────────────────────────────────────
        patient_info = {
            'name':       request.form.get('patient_name', 'Unknown').strip(),
            'age':        int(request.form.get('patient_age', 72) or 72),
            'sex':        request.form.get('patient_sex', 'N/A').strip(),
            'allergies':  request.form.get('allergies', '').strip(),
            'conditions': request.form.get('conditions', '').strip(),
            'patient_id': 'MED-001',
        }

        medicines_text   = request.form.get('medicines_input', '').strip()
        old_medicines    = request.form.get('old_medicines', '').strip()
        declared_allergies = request.form.get('declared_allergies', '').strip()

        meds_list     = [l.strip() for l in medicines_text.splitlines() if l.strip()]
        old_meds_list = [l.strip() for l in old_medicines.splitlines() if l.strip()]
        allergies_str = declared_allergies or patient_info['allergies']

        # ── Run all engines ──────────────────────────────────────────────────
        reconciliation_result = None
        if old_meds_list and meds_list:
            try:
                reconciliation_result = reconciliation_engine.reconcile(old_meds_list, meds_list)
            except Exception as e:
                app.logger.error(f"Reconciliation error in report: {e}")

        safety_result = None
        if meds_list:
            try:
                safety_result = safety_engine.evaluate_regimen(
                    medicine_entries=meds_list,
                    declared_allergies=allergies_str,
                    patient_age=patient_info['age']
                )
            except Exception as e:
                app.logger.error(f"Safety engine error in report: {e}")

        schedule_timetable = None
        if meds_list:
            try:
                schedule_timetable = scheduler_engine.generate_daily_timetable(
                    medicines=meds_list,
                    target_date=date.today(),
                    patient_id=1
                )
            except Exception as e:
                app.logger.error(f"Scheduler error in report: {e}")

        adherence_stats = None
        try:
            adherence_stats = get_adherence_rate(patient_id=1, days=7)
        except Exception:
            pass

        # ── Generate report ──────────────────────────────────────────────────
        report = report_generator.generate_report(
            patient_info=patient_info,
            reconciliation_result=reconciliation_result,
            safety_result=safety_result,
            schedule_timetable=schedule_timetable,
            adherence_stats=adherence_stats,
            medicines_list=meds_list,
            report_date=date.today(),
        )

    return render_template(
        'report.html',
        report=report,
        medicines_text=medicines_text,
        old_medicines=old_medicines,
        declared_allergies=declared_allergies,
    )


@app.route('/api/report/generate', methods=['POST'])
def api_report_generate():
    """
    REST API for report generation.
    Accepts JSON:
    {
        "patient_info": {"name": "...", "age": 72, "sex": "Male", ...},
        "medicines": ["Tab Telma 40mg OD", ...],
        "old_medicines": ["Tab Telma 20mg OD", ...],
        "declared_allergies": "Penicillin"
    }
    """
    data = request.get_json() or {}
    patient_info = data.get('patient_info', {'name': 'Unknown', 'age': 72, 'sex': 'N/A'})
    meds_list    = data.get('medicines', [])
    old_meds     = data.get('old_medicines', [])
    allergies    = data.get('declared_allergies', '')
    age          = patient_info.get('age', 72)

    reconciliation_result = None
    if old_meds and meds_list:
        try:
            reconciliation_result = reconciliation_engine.reconcile(old_meds, meds_list)
        except Exception:
            pass

    safety_result = None
    if meds_list:
        try:
            safety_result = safety_engine.evaluate_regimen(
                medicine_entries=meds_list,
                declared_allergies=allergies,
                patient_age=age
            )
        except Exception:
            pass

    schedule_timetable = None
    if meds_list:
        try:
            schedule_timetable = scheduler_engine.generate_daily_timetable(
                medicines=meds_list, target_date=date.today(), patient_id=1
            )
        except Exception:
            pass

    report = report_generator.generate_report(
        patient_info=patient_info,
        reconciliation_result=reconciliation_result,
        safety_result=safety_result,
        schedule_timetable=schedule_timetable,
        medicines_list=meds_list,
    )

    return jsonify({'status': 'success', 'report': report})


if __name__ == '__main__':
    # Local demo server running on port 5000
    app.run(host='127.0.0.1', port=5000, debug=True)
