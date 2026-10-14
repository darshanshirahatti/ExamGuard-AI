ExamGuard AI — Full-Stack Mini Project
A runnable educational prototype with a responsive web frontend, FastAPI backend, SQLite persistence, student/admin demo logins, exam flow, webcam preview, event review, and CSV export.
AI limitation: This starter does not include a trained CNN/LSTM model. Monitoring events created by the demo button are simulated and clearly labelled. They are not model predictions or proof of cheating. Camera preview is opt-in and remains in the browser; this app does not record or upload video.
Run on Windows
Extract this ZIP to `D:\WebText-AI`.
Open PowerShell:
```powershell
cd D:\WebText-AI
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```
Open `http://127.0.0.1:8000`.
Demo accounts:
Student: `student@examguard.local` / `StudentDemo123!`
Admin: `admin@examguard.local` / `AdminDemo123!`
API docs: `http://127.0.0.1:8000/docs`
Structure
```text
ExamGuard-AI/
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes, auth, SQLite persistence
│   └── analyzer.py      # Demo analyzer interface for future DL integration
├── frontend/
│   ├── index.html       # Pages and layout
│   ├── styles.css       # Responsive UI
│   └── app.js           # Frontend state, API calls, exam flow, webcam preview
├── requirements.txt
├── .env.example
└── README.md
```
Features
Student and administrator demo access
Student dashboard, practice exam, timer, multiple-choice questions
Optional webcam preview with permission request and stop button
Simulated monitoring events and event timeline
Admin event review (review/dismiss with note)
Session history, basic search, CSV export
SQLite database created automatically on first run
Future Deep Learning integration
Replace the demo analyzer with a validated Python model/service using OpenCV, MediaPipe and (if appropriate) a temporal CNN-LSTM. The current demo analyzer does not inspect webcam pixels. Evaluate false positives and recall on consented data. All cues should be reviewed by a human; do not automate penalties from model output.
Security
Newly registered accounts use PBKDF2-SHA256 password hashes; legacy seeded demo passwords are upgraded to hashes on first successful login. Authentication remains a lightweight educational bearer-token implementation. Do not deploy publicly without HTTPS, rate limiting, token expiry/rotation, secure reset emails, audit logs, CSRF review where applicable, and a security assessment.
Camera refresh fix (2026-10-10)
The exam question renderer replaces the contents of the exam container on each answer/navigation. The camera video element must not live inside that container.
`frontend/app.js` now keeps one hidden video element outside the rerendered exam, reuses the existing stream, and requests 640x480 video at a target of 15 FPS (maximum 20 FPS).
The camera image is not shown during the exam. Camera processing is not stopped just to hide the preview.
Run `node --check frontend/app.js` to check JavaScript syntax. Camera permission behaviour still needs to be verified in the target browser.
Admin, registration, and assessment review updates
This update adds public student registration (admin role cannot be selected publicly), duplicate-email prevention, password confirmation in the UI, password hashing for new accounts, legacy demo-password migration on first login, local-demo password reset, student activation controls, exam/question management, analytics, CSV/PDF event reports, admin profile settings, and per-session score analysis.
New admin pages
Student management: search students and activate/deactivate accounts. Deactivation revokes existing login tokens.
Exam & question setting: create/edit exam metadata and add/edit/delete MCQs with correct-answer keys.
Review events: annotate, review, or dismiss monitoring cues; cues are not proof of misconduct.
Reports & analytics: basic usage metrics and CSV/PDF event export.
Admin profile & settings: change administrator display name and optionally password.
Score analysis: calculate score from answer keys and show transparent rule-based learning suggestions.
Important prototype limitations
The score guidance is a transparent rule-based baseline, not a trained or validated AI model or predictive probability.
Monitoring events remain simulated in this prototype. Do not treat them as proof of cheating or use them for automatic penalties.
Forgot-password currently uses a local-demo reset token because no email provider is configured. Set `EXAMGUARD_DEMO_RESET=0` to disable returning the token from the API and configure a real email delivery service before production use.
Demo accounts are seeded only when the database has no users: `student@examguard.local` / `StudentDemo123!` and `admin@examguard.local` / `AdminDemo123!`. Change these before any shared or production deployment.
This is an educational prototype; review authentication, rate limiting, CSRF protections, audit logging, and secret management before production deployment.
Admin question authoring assistant and score analysis
In the administrator workspace, open Exam & question setting to manually add or edit questions as before, or use Question Authoring Agent to generate editable topic-based MCQ drafts. Select a draft to populate the normal question form, verify the options and answer key, and then save it. Drafts are not published automatically.
Open Reports & analytics for overall submitted-session average, score distribution, per-exam average/highest/lowest scores, and question-level correct rates. Only submitted sessions with configured answer keys are included in scored aggregates.
AI status: the current question authoring helper is an offline template-based assistant; it does not call an external LLM. The score analyzer calculates scores from configured answer keys and provides descriptive statistics; it is not a trained future-score prediction model. Review all question drafts and low-correct-rate questions before using them in a live exam.