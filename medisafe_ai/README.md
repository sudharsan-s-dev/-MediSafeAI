# MediSafe AI: Medication Safety, Reconciliation and Adherence System
**Author:** Sudharsan S  
**Programme:** B.Sc. Artificial Intelligence and Data Science  
**Institution:** VET Institute of Arts and Science College, Coimbatore  
**Academic Year:** 2026–2027  

---

## 📌 Project Overview
MediSafe AI is an academic prototype designed to enhance medication safety for elderly patients taking multiple concurrent medications (polypharmacy).

### 🛡️ Decision Support Disclaimer
MediSafe AI is designed strictly as a clinical decision-support and adherence tool for patients and caregivers. It **never** replaces professional medical judgment, diagnosis, or the counsel of a licensed doctor or pharmacist.

---

## 🏗️ Completed Modules

### Module 1: Medication Reconciliation Engine
- **Active Ingredient Resolution**: Uses `data/brand_generic_db.json` with token parsing and `difflib` fuzzy matching to resolve commercial brand names (e.g. *Dolo 650*, *Calpol*, *Crocin*) to standard active ingredients (*Paracetamol*).
- **5-Category Reconciliation**: `SAME`, `CHANGED`, `DISCONTINUED`, `NEW`, and `DUPLICATE`.

### Module 2: Safety & Interaction Checks
- **Curated Geriatric Drug-Drug Interactions (DDI)**: `data/drug_interactions.json` covering 30+ high-impact pairs (Triple Whammy Acute Kidney Injury, Warfarin + Antiplatelet bleeding, Statin + Macrolide rhabdomyolysis, Sedative + Opioid fall risks).
- **Declared Allergy Matching**: Screens against user-declared allergies across brand names, active ingredients, and drug class hierarchies (e.g. *Penicillin* allergy flags *Augmentin* / *Amoxicillin*).
- **Geriatric Daily Dosage Limits**: Flags cumulative active ingredient intake exceeding elderly safety guidelines (e.g. Paracetamol > 3,000 mg/day).

### Module 3: Medication Scheduler & Reminders
- **Meal-Anchored 5-Slot Pillbox**: Organizes daily doses around anchor events:
  - 🌅 Morning (08:00 AM • Breakfast)
  - ☀️ Afternoon (01:00 PM • Lunch)
  - 🌇 Evening (05:00 PM • Snack/Tea)
  - 🌙 Night (08:30 PM • Dinner/Bedtime)
  - 🚨 As-Needed (SOS / PRN)
- **Acute vs. Chronic Course Expiration**: Differentiates ongoing maintenance medications from fixed-duration courses (e.g., *Augmentin for 5 days*), displaying a prominent *"Course Completed — Do not continue"* badge once the course has elapsed.
- **In-Browser Reminders**: Uses the HTML5 Web Notification API and Web Audio API synthesizer chime to deliver local alerts without paid cloud SMS infrastructure. Includes a *"Simulate Morning Reminder"* button for viva demonstration.
- **1-Click Adherence Tracking**: Real-time `✅ Taken` / `❌ Missed` buttons recording events in local SQLite (`adherence_logs` table) and computing a 7-day adherence rate percentage.

---

## 🧪 Running Standalone Tests
To run all 24 automated unit and integration tests across Modules 1, 2, and 3:
```powershell
py -m unittest discover tests -v
```

---

## 🚀 Running the Web Application
To start the interactive web application:
```powershell
py app.py
```
Then open your web browser at:
- **Module 1 (Reconciliation):** `http://127.0.0.1:5000/reconcile`
- **Module 2 (Safety Checks):** `http://127.0.0.1:5000/safety`
- **Module 3 (Scheduler & Reminders):** `http://127.0.0.1:5000/schedule`
