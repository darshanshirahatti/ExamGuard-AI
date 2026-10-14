# ExamGuard AI update — changed files and install notes

## Changed files
- `backend/main.py` — additive database migrations; student registration and duplicate-email checks; password hashing and local reset flow; account status controls; exam and MCQ CRUD; score analysis; analytics; profile settings; PDF/CSV reports.
- `frontend/index.html` — centered sign-in/register interface and new admin navigation/pages.
- `frontend/app.js` — authentication flows and admin UI for students, exams/questions, event review, reports, profile settings, and session score analysis. Existing exam permission/fullscreen flow is retained.
- `frontend/styles.css` — responsive auth forms, admin forms, question bank, report and analysis styles.
- `requirements.txt` — adds ReportLab for PDF exports.
- `README.md` — documents features, limitations, and setup.

## Install into an existing Windows checkout
1. Back up `D:\WebText-AI\examguard.db` before updating.
2. Extract this ZIP to a temporary folder.
3. Copy the updated `backend\main.py`, the complete `frontend\` folder, `requirements.txt`, and `README.md` into `D:\WebText-AI\`, replacing those files. Copy `UPGRADE_NOTES.md` too if desired.
4. Do **not** replace or delete your existing `examguard.db`. On startup, the backend applies additive SQLite migrations to add account status, timestamps, answer keys, and reset-token storage.
5. In PowerShell:

```powershell
cd D:\WebText-AI
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

6. Open `http://127.0.0.1:8000` and press `Ctrl+F5`.

## Demo accounts
- Student: `student@examguard.local` / `StudentDemo123!`
- Admin: `admin@examguard.local` / `AdminDemo123!`

These seeded accounts are only created when the database has no users. If your existing database has users, the existing credentials remain. Newly registered public accounts always receive the `student` role; there is no public admin registration.

## Reset-password note
No email service is configured. Local demo mode returns a one-time reset token in the API response so the UI can complete the workflow. Set environment variable `EXAMGUARD_DEMO_RESET=0` to stop returning that token; configure a trusted email provider before production deployment.

## Score analysis note
The administrator can open a session's **Score analysis**. It calculates the score from the stored answer key and provides a transparent performance outlook. It is not a trained AI model or a validated future-score prediction. Existing monitoring cues are simulated and must never be treated as proof of cheating or used for automatic penalties.
