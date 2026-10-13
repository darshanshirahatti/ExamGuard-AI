# ExamGuard AI — Full-Stack Mini Project

A runnable educational prototype with a responsive web frontend, FastAPI backend, SQLite persistence, student/admin demo logins, exam flow, webcam preview, event review, and CSV export.

**AI limitation:** This starter does not include a trained CNN/LSTM model. Monitoring events created by the demo button are simulated and clearly labelled. They are not model predictions or proof of cheating. Camera preview is opt-in and remains in the browser; this app does not record or upload video.

## Run on Windows

1. Extract this ZIP to `D:\WebText-AI`.
2. Open PowerShell:

```powershell
cd D:\WebText-AI
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

3. Open `http://127.0.0.1:8000`.

Demo accounts:
- Student: `student@examguard.local` / `StudentDemo123!`
- Admin: `admin@examguard.local` / `AdminDemo123!`

API docs: `http://127.0.0.1:8000/docs`

## Structure

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

## Features
- Student and administrator demo access
- Student dashboard, practice exam, timer, multiple-choice questions
- Optional webcam preview with permission request and stop button
- Simulated monitoring events and event timeline
- Admin event review (review/dismiss with note)
- Session history, basic search, CSV export
- SQLite database created automatically on first run

## Future Deep Learning integration
Replace the demo analyzer with a validated Python model/service using OpenCV, MediaPipe and (if appropriate) a temporal CNN-LSTM. The current demo analyzer does not inspect webcam pixels. Evaluate false positives and recall on consented data. All cues should be reviewed by a human; do not automate penalties from model output.

## Security
This is a local educational prototype. Demo passwords are plain text and tokens are simple. Do not deploy publicly without proper password hashing, secure sessions, HTTPS, strict authorization, rate limiting, audit logs and security testing.
