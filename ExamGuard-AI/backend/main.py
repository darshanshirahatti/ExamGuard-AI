#part 1 main.py
import os, sqlite3, secrets, csv, io, json, hashlib, hmac, base64, textwrap, logging
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import csv
import io
from fastapi.responses import Response
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)



ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DB_PATH = os.getenv("EXAMGUARD_DB_PATH", str(ROOT / "examguard.db"))

app = FastAPI(title="ExamGuard AI", version="1.0.0")
logger = logging.getLogger("uvicorn.error")
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        );

        CREATE TABLE IF NOT EXISTS password_resets(
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            expires_at TEXT,
            used INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exams(
            id INTEGER PRIMARY KEY,
            title TEXT,
            description TEXT,
            duration INTEGER
        );

        CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY,
            exam_id INTEGER,
            prompt TEXT,
            options TEXT,
            position INTEGER
        );

        CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY,
            student_id INTEGER,
            exam_id INTEGER,
            status TEXT,
            started_at TEXT,
            submitted_at TEXT,
            answers TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY,
            session_id INTEGER,
            category TEXT,
            severity TEXT,
            description TEXT,
            source TEXT,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tokens(
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS assessment_sections (
            id INTEGER PRIMARY KEY,
            exam_id INTEGER NOT NULL,
            section_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            duration_minutes INTEGER,
            instructions TEXT DEFAULT '',
            position INTEGER NOT NULL,
            FOREIGN KEY (exam_id) REFERENCES exams(id),
            UNIQUE (exam_id, section_number)
        );

        CREATE TABLE IF NOT EXISTS question_sections (
            question_id INTEGER PRIMARY KEY,
            section_id INTEGER NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id),
            FOREIGN KEY (section_id) REFERENCES assessment_sections(id)
        );
        """)

        # Additive migrations preserve existing database records.
        user_cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}

        if "is_active" not in user_cols:
            c.execute(
                "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )

        if "created_at" not in user_cols:
            c.execute(
                "ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''"
            )

        question_cols = {
            r[1] for r in c.execute("PRAGMA table_info(questions)")
        }

        if "correct_answer" not in question_cols:
            c.execute(
                "ALTER TABLE questions ADD COLUMN correct_answer TEXT DEFAULT ''"
            )

        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.executemany(
                """
                INSERT INTO users(
                    id, name, email, password, role, is_active, created_at
                )
                VALUES(?,?,?,?,?,1,?)
                """,
                [
                    (
                        1, "Aarav Student",
                        "student@examguard.local",
                        "StudentDemo123!", "student", now()
                    ),
                    (
                        2, "Exam Administrator",
                        "admin@examguard.local",
                        "AdminDemo123!", "admin", now()
                    )
                ]
            )
        
        exam_cols = {
            row[1] for row in c.execute("PRAGMA table_info(exams)")
        }
        if "test_id" not in exam_cols:
            c.execute("ALTER TABLE exams ADD COLUMN test_id TEXT")

        if "published" not in exam_cols:
            c.execute(
                "ALTER TABLE exams ADD COLUMN published INTEGER NOT NULL DEFAULT 0"
            )

        if "section_count" not in exam_cols:
            c.execute(
                "ALTER TABLE exams ADD COLUMN section_count INTEGER NOT NULL DEFAULT 1"
            )

        # Assign IDs to existing assessments without replacing existing records.
        existing = c.execute(
            "SELECT id FROM exams WHERE test_id IS NULL OR test_id = ''"
        ).fetchall()

        for row in existing:
            c.execute(
                "UPDATE exams SET test_id = ? WHERE id = ?",
                (f"EXG-{row['id']:05d}", row["id"])
            )

        

        if c.execute("SELECT COUNT(*) FROM exams").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO exams VALUES(1,?,?,20)",
                (
                    "Deep Learning Fundamentals",
                    "Practice assessment covering neural-network concepts."
                )
            )

            questions = [
                (
                    "Which layer commonly applies a non-linear activation?",
                    [
                        "Dense layer with activation",
                        "Input file",
                        "Database index",
                        "HTTP route"
                    ]
                ),
                (
                    "What is an epoch in model training?",
                    [
                        "One full pass over training data",
                        "A CSS rule",
                        "A database backup",
                        "A browser tab"
                    ]
                ),
                (
                    "Which metric is useful when false positives matter?",
                    [
                        "Precision",
                        "File size",
                        "Screen width",
                        "Latency only"
                    ]
                ),
                (
                    "What does overfitting mean?",
                    [
                        "Good training performance but poor generalization",
                        "No model parameters",
                        "Server offline",
                        "Always balanced data"
                    ]
                ),
                (
                    "Why keep a validation set?",
                    [
                        "Assess model choices on held-out data",
                        "Store passwords",
                        "Render icons",
                        "Replace training data"
                    ]
                )
            ]

            c.executemany(
                """
                INSERT INTO questions(exam_id,prompt,options,position)
                VALUES(1,?,?,?)
                """,
                [
                    (prompt, json.dumps(options), i + 1)
                    for i, (prompt, options) in enumerate(questions)
                ]
            )

        # Correct answers for the demo exam.
        answer_map = {
            "Which layer commonly applies a non-linear activation?":
                "Dense layer with activation",
            "What is an epoch in model training?":
                "One full pass over training data",
            "Which metric is useful when false positives matter?":
                "Precision",
            "What does overfitting mean?":
                "Good training performance but poor generalization",
            "Why keep a validation set?":
                "Assess model choices on held-out data"
        }

        for prompt, answer in answer_map.items():
            c.execute(
                """
                UPDATE questions
                SET correct_answer=?
                WHERE prompt=?
                  AND (correct_answer IS NULL OR correct_answer='')
                """,
                (answer, prompt)
            )

        c.execute(
            """
            UPDATE users
            SET created_at=?
            WHERE created_at IS NULL OR created_at=''
            """,
            (now(),)
        )

        c.commit()


@app.on_event("startup")
def startup():
    init_db()


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in.")

    with db() as c:
        row = c.execute(
            """
            SELECT u.id,u.name,u.email,u.role
            FROM tokens t
            JOIN users u ON u.id=t.user_id
            WHERE t.token=? AND u.is_active=1
            """,
            (authorization[7:].strip(),)
        ).fetchone()

    if not row:
        raise HTTPException(401, "Session expired. Sign in again.")

    return dict(row)


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")
    return user


class Login(BaseModel):
    email: str
    password: str


class Register(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class ForgotPassword(BaseModel):
    email: str


class ResetPassword(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class UserStatus(BaseModel):
    is_active: bool


class ExamInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=1000)
    duration_minutes: int = Field(ge=1, le=360)


class QuestionInput(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_answer: str = Field(min_length=1, max_length=500)
    position: int = Field(default=1, ge=1, le=500)


class AgentQuestionRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=160)
    difficulty: str = Field(
        default="medium",
        pattern="^(easy|medium|hard)$"
    )
    count: int = Field(default=5, ge=1, le=10)


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str | None = Field(
        default=None, min_length=8, max_length=128
    )

class StudentProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    current_password: str = Field(min_length=1, max_length=128)

class StartSession(BaseModel):
    # Accept field names from different frontend versions.
    exam_id: int | None = None
    examId: int | None = None
    id: int | None = None

    def resolved_exam_id(self) -> int:
        value = self.exam_id
        if value is None:
            value = self.examId
        if value is None:
            value = self.id

        if value is None or value < 1:
            raise HTTPException(
                status_code=400,
                detail="A valid exam_id is required to start an assessment."
            )

        return value

class Answer(BaseModel):
    question_id: int
    answer: str


class Submit(BaseModel):
    answers: list[Answer] = Field(default_factory=list)


class NewEvent(BaseModel):
    category: str
    severity: str = "low"
    description: str
    source: str = "demo"


class Review(BaseModel):
    status: str
    note: str = ""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, 180_000
    )
    return "pbkdf2_sha256$180000$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt, digest = stored.split("$", 3)
            got = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                base64.urlsafe_b64decode(salt),
                int(rounds)
            )
            return hmac.compare_digest(
                base64.urlsafe_b64encode(got).decode(),
                digest
            )
        except Exception:
            return False

    # Legacy demo accounts are upgraded to a hash after successful login.
    return hmac.compare_digest(password, stored)


def public_user(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"]
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


# Directly-openable student assessment URLs. Both paths serve the same SPA;
# the frontend resolves the stable test ID after the student signs in.
@app.get("/assessment/{test_id}", response_class=HTMLResponse)
@app.get("/examguard-ai/assessment/{test_id}", response_class=HTMLResponse)
def assessment_page(test_id: str):
    clean_id = test_id.strip().upper()
    if not clean_id or len(clean_id) > 40:
        raise HTTPException(404, "Assessment link is invalid.")
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "educational-demo"}


@app.post("/api/auth/register")
def register(body: Register):
    name = body.name.strip()
    email = body.email.strip().lower()

    if not name or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Enter a valid name and email address.")

    if len(body.password) < 8:
        raise HTTPException(400, "Password must contain at least 8 characters.")

    with db() as c:
        if c.execute(
            "SELECT 1 FROM users WHERE lower(email)=?", (email,)
        ).fetchone():
            raise HTTPException(
                409, "An account with this email already exists."
            )

        cur = c.execute(
            """
            INSERT INTO users(name,email,password,role,is_active,created_at)
            VALUES(?,?,?,'student',1,?)
            """,
            (name, email, hash_password(body.password), now())
        )
        uid = cur.lastrowid
        c.commit()

    return {
        "ok": True,
        "message": "Student account created. You can now sign in.",
        "user_id": uid,
        "role": "student"
    }


@app.post("/api/auth/login")
def login(body: Login):
    with db() as c:
        row = c.execute(
            "SELECT * FROM users WHERE lower(email)=lower(?)",
            (body.email.strip(),)
        ).fetchone()

        if not row or not verify_password(body.password, row["password"]):
            raise HTTPException(401, "Invalid email or password.")

        if not row["is_active"]:
            raise HTTPException(
                403, "This account is inactive. Contact an administrator."
            )

        if not row["password"].startswith("pbkdf2_sha256$"):
            c.execute(
                "UPDATE users SET password=? WHERE id=?",
                (hash_password(body.password), row["id"])
            )

        token = secrets.token_urlsafe(32)
        c.execute(
            "INSERT INTO tokens VALUES(?,?,?)",
            (token, row["id"], now())
        )
        c.commit()

        return {"token": token, "user": public_user(row)}


@app.post("/api/auth/forgot-password")
def forgot_password(body: ForgotPassword):
    email = body.email.strip().lower()

    with db() as c:
        row = c.execute(
            "SELECT id FROM users WHERE lower(email)=? AND is_active=1",
            (email,)
        ).fetchone()

        # Local demo only: expose a one-time reset token for testing.
        if row:
            token = secrets.token_urlsafe(24)
            from datetime import timedelta

            expiry = (
                datetime.now(timezone.utc) + timedelta(minutes=20)
            ).isoformat(timespec="seconds")

            c.execute(
                """
                INSERT INTO password_resets(token,user_id,expires_at,used)
                VALUES(?,?,?,0)
                """,
                (token, row["id"], expiry)
            )
            c.commit()

            if os.getenv("EXAMGUARD_DEMO_RESET", "1").lower() in (
                "1", "true", "yes"
            ):
                return {
                    "message": "If the account exists, a reset token is ready for local demo use.",
                    "demo_reset_token": token
                }

    return {
        "message": "If an active account exists, password reset instructions will be provided."
    }


@app.post("/api/auth/reset-password")
def reset_password(body: ResetPassword):
    with db() as c:
        row = c.execute(
            "SELECT * FROM password_resets WHERE token=? AND used=0",
            (body.token.strip(),)
        ).fetchone()

        if not row or row["expires_at"] < now():
            raise HTTPException(
                400, "Reset token is invalid or expired. Request a new one."
            )

        c.execute(
            "UPDATE users SET password=? WHERE id=?",
            (hash_password(body.password), row["user_id"])
        )
        c.execute(
            "UPDATE password_resets SET used=1 WHERE token=?",
            (body.token.strip(),)
        )
        c.execute("DELETE FROM tokens WHERE user_id=?", (row["user_id"],))
        c.commit()

    return {
        "ok": True,
        "message": "Password reset successfully. Sign in with your new password."
    }


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/exams")
def exams(user=Depends(current_user)):
    with db() as c:
        return [
            dict(r)
            for r in c.execute(
                """
                SELECT id,title,description,duration AS duration_minutes
                FROM exams
                """
            )
        ]
        #part 2 begin
@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        with db() as c:
            c.execute("DELETE FROM tokens WHERE token=?", (token,))
            c.commit()
    return {"ok": True}


# ---------------------------------------------------------
# ADMIN: STUDENT MANAGEMENT
# ---------------------------------------------------------

@app.get("/api/admin/students")
def admin_students(user=Depends(admin)):
    with db() as c:
        rows = c.execute("""
            SELECT id,name,email,role,is_active,created_at
            FROM users
            ORDER BY id DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.patch("/api/admin/students/{student_id}/status")
def update_student_status(
    student_id: int,
    body: UserStatus,
    user=Depends(admin)
):
    with db() as c:
        student = c.execute(
            "SELECT id,role FROM users WHERE id=?",
            (student_id,)
        ).fetchone()

        if not student:
            raise HTTPException(404, "User not found.")

        if student["role"] == "admin":
            raise HTTPException(
                400, "Administrator accounts cannot be disabled here."
            )

        c.execute(
            "UPDATE users SET is_active=? WHERE id=?",
            (int(body.is_active), student_id)
        )

        if not body.is_active:
            c.execute(
                "DELETE FROM tokens WHERE user_id=?",
                (student_id,)
            )

        c.commit()

    return {"ok": True, "is_active": body.is_active}


# ---------------------------------------------------------
# ADMIN: EXAM MANAGEMENT
# ---------------------------------------------------------

@app.post("/api/admin/exams")
def create_exam(body: ExamInput, user=Depends(admin)):
    with db() as c:
        cur = c.execute(
            """
            INSERT INTO exams(title,description,duration)
            VALUES(?,?,?)
            """,
            (
                body.title.strip(),
                body.description.strip(),
                body.duration_minutes
            )
        )
        exam_id = cur.lastrowid
        c.commit()

    return {"ok": True, "exam_id": exam_id}


@app.put("/api/admin/exams/{exam_id}")
def update_exam(
    exam_id: int,
    body: ExamInput,
    user=Depends(admin)
):
    with db() as c:
        cur = c.execute(
            """
            UPDATE exams
            SET title=?,description=?,duration=?
            WHERE id=?
            """,
            (
                body.title.strip(),
                body.description.strip(),
                body.duration_minutes,
                exam_id
            )
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Exam not found.")
        c.commit()

    return {"ok": True}


# ---------------------------------------------------------
# ADMIN: SHARE ASSESSMENT LINK
# ---------------------------------------------------------

@app.get("/api/admin/exams/{exam_id}/share-link")
def get_assessment_share_link(
    exam_id: int,
    request: Request,
    user=Depends(admin)
):
    with db() as c:
        exam = c.execute(
            "SELECT id, test_id, title, duration FROM exams WHERE id=?",
            (exam_id,)
        ).fetchone()

    if not exam:
        raise HTTPException(404, "Assessment not found.")

    test_id = (exam["test_id"] or f"EXG-{exam['id']:05d}").strip().upper()
    # Set EXAMGUARD_PUBLIC_URL to the public origin when deployed.
    base_url = (
        os.getenv("EXAMGUARD_PUBLIC_URL", "").strip().rstrip("/")
        or str(request.base_url).rstrip("/")
    )
    share_url = f"{base_url}/examguard-ai/assessment/{test_id}"

    return {
        "ok": True,
        "application_name": "ExamGuard AI",
        "exam_id": exam["id"],
        "test_id": test_id,
        "title": exam["title"],
        "duration_minutes": exam["duration"],
        "share_url": share_url,
        "message": (
            f"ExamGuard AI assessment: {exam['title']} ({test_id}). "
            f"Duration: {exam['duration']} minutes. "
            "Open the link and sign in with your student account."
        )
    }


@app.get("/api/assessment/by-test-id/{test_id}")
def assessment_by_test_id(test_id: str, user=Depends(current_user)):
    """Resolve a shared test ID after student authentication."""
    if user["role"] != "student":
        raise HTTPException(403, "Sign in with a student account to take this assessment.")
    with db() as c:
        exam = c.execute(
            "SELECT id, test_id, title, description, duration AS duration_minutes "
            "FROM exams WHERE upper(test_id)=upper(?)",
            (test_id.strip(),)
        ).fetchone()
    if not exam:
        raise HTTPException(404, "This assessment link is invalid or the exam no longer exists.")
    return dict(exam)

@app.get("/api/admin/exams/{exam_id}/questions")
def admin_questions(exam_id: int, user=Depends(admin)):
    with db() as c:
        exam = c.execute(
            "SELECT id FROM exams WHERE id=?",
            (exam_id,)
        ).fetchone()

        if not exam:
            raise HTTPException(404, "Exam not found.")

        rows = c.execute("""
            SELECT id,exam_id,prompt,options,correct_answer,position
            FROM questions
            WHERE exam_id=?
            ORDER BY position,id
        """, (exam_id,)).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        try:
            item["options"] = json.loads(item["options"] or "[]")
        except (ValueError, TypeError):
            item["options"] = []
        result.append(item)

    return result


@app.post("/api/admin/exams/{exam_id}/questions")
def create_question(
    exam_id: int,
    body: QuestionInput,
    user=Depends(admin)
):
    options = [x.strip() for x in body.options]

    if len(options) < 2 or any(not x for x in options):
        raise HTTPException(400, "Provide at least two non-empty options.")

    if len(set(options)) != len(options):
        raise HTTPException(400, "Question options must be unique.")

    if body.correct_answer.strip() not in options:
        raise HTTPException(
            400, "Correct answer must match one of the provided options."
        )

    with db() as c:
        if not c.execute(
            "SELECT 1 FROM exams WHERE id=?",
            (exam_id,)
        ).fetchone():
            raise HTTPException(404, "Exam not found.")

        cur = c.execute("""
            INSERT INTO questions(
                exam_id,prompt,options,position,correct_answer
            )
            VALUES(?,?,?,?,?)
        """, (
            exam_id,
            body.prompt.strip(),
            json.dumps(options),
            body.position,
            body.correct_answer.strip()
        ))
        question_id = cur.lastrowid
        c.commit()

    return {"ok": True, "question_id": question_id}


@app.put("/api/admin/questions/{question_id}")
def update_question(
    question_id: int,
    body: QuestionInput,
    user=Depends(admin)
):
    options = [x.strip() for x in body.options]

    if len(options) < 2 or any(not x for x in options):
        raise HTTPException(400, "Provide at least two non-empty options.")

    if len(set(options)) != len(options):
        raise HTTPException(400, "Question options must be unique.")

    if body.correct_answer.strip() not in options:
        raise HTTPException(
            400, "Correct answer must match one of the provided options."
        )

    with db() as c:
        cur = c.execute("""
            UPDATE questions
            SET prompt=?,options=?,correct_answer=?,position=?
            WHERE id=?
        """, (
            body.prompt.strip(),
            json.dumps(options),
            body.correct_answer.strip(),
            body.position,
            question_id
        ))

        if cur.rowcount == 0:
            raise HTTPException(404, "Question not found.")

        c.commit()

    return {"ok": True}


@app.delete("/api/admin/questions/{question_id}")
def delete_question(question_id: int, user=Depends(admin)):
    with db() as c:
        cur = c.execute(
            "DELETE FROM questions WHERE id=?",
            (question_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Question not found.")
        c.commit()

    return {"ok": True}


# ---------------------------------------------------------
# STUDENT: EXAM SESSION
# ---------------------------------------------------------

@app.post("/api/sessions")
def start_session(payload: dict, user=Depends(current_user)):
    exam_id = payload.get("exam_id")

    if not exam_id:
        raise HTTPException(status_code=400, detail="exam_id is required")

    with db() as c:
        exam_row = c.execute(
            """
            SELECT id, title, description, duration
            FROM exams
            WHERE id = ?
            """,
            (exam_id,)
        ).fetchone()

        if not exam_row:
            raise HTTPException(status_code=404, detail="Exam not found")

        question_rows = c.execute(
            """
            SELECT id, prompt, options, position
            FROM questions
            WHERE exam_id = ?
            ORDER BY position, id
            """,
            (exam_id,)
        ).fetchall()

        question_count = len(question_rows)

        cur = c.execute(
            """
            INSERT INTO sessions (
                student_id, exam_id, status, started_at, answers
            )
            VALUES (?, ?, 'in_progress', ?, '[]')
            """,
            (user["id"], exam_id, now())
        )

        # IMPORTANT: assign the session ID before using it.
        session_id = cur.lastrowid
        c.commit()

    exam_data = {
        "id": exam_row["id"],
        "title": exam_row["title"],
        "description": exam_row["description"],
        "duration_minutes": exam_row["duration"],
        "questions": [
            {
                "id": q["id"],
                "prompt": q["prompt"],
                "options": json.loads(q["options"] or "[]")
            }
            for q in question_rows
        ]
    }

    return {
        "id": session_id,
        "session_id": session_id,
        "status": "in_progress",
        "exam": exam_data,
        "question_count": question_count
    }
@app.get("/api/sessions/{session_id}/questions")
def session_questions(
    session_id: int,
    user=Depends(current_user)
    ):
    with db() as c:
        session = c.execute(
            "SELECT * FROM sessions WHERE id=?",
            (session_id,)
        ).fetchone()

        if not session:
            raise HTTPException(404, "Session not found.")

        if user["role"] != "admin" and session["student_id"] != user["id"]:
            raise HTTPException(403, "This session does not belong to you.")

        rows = c.execute("""
            SELECT id,prompt,options,position
            FROM questions
            WHERE exam_id=?
            ORDER BY position,id
        """, (session["exam_id"],)).fetchall()

    questions = []
    for row in rows:
        item = dict(row)
        try:
            item["options"] = json.loads(item["options"] or "[]")
        except (ValueError, TypeError):
            item["options"] = []
        questions.append(item)

    return {
        "session_id": session_id,
        "status": session["status"],
        "questions": questions
    }


@app.post("/api/sessions/{session_id}/submit")
def submit_session(
    session_id: int,
    body: Submit,
    user=Depends(current_user)
):
    if user["role"] != "student":
        raise HTTPException(403, "Only students can submit an exam.")

    with db() as c:
        session = c.execute(
            "SELECT * FROM sessions WHERE id=?",
            (session_id,)
        ).fetchone()

        if not session:
            raise HTTPException(404, "Session not found.")

        if session["student_id"] != user["id"]:
            raise HTTPException(403, "This session does not belong to you.")

        if session["status"] != "in_progress":
            raise HTTPException(409, "This exam has already been submitted.")

        valid_ids = {
            row["id"] for row in c.execute(
                "SELECT id FROM questions WHERE exam_id=?",
                (session["exam_id"],)
            ).fetchall()
        }

        answers = []
        seen = set()

        for answer in body.answers:
            if answer.question_id not in valid_ids:
                raise HTTPException(
                    400, "A submitted question does not belong to this exam."
                )
            if answer.question_id in seen:
                raise HTTPException(
                    400, "Duplicate answer for a question."
                )
            seen.add(answer.question_id)
            answers.append({
                "question_id": answer.question_id,
                "answer": answer.answer.strip()
            })

        c.execute("""
            UPDATE sessions
            SET answers=?,status='submitted',submitted_at=?
            WHERE id=?
        """, (json.dumps(answers), now(), session_id))

        c.commit()

    return {"ok": True, "status": "submitted"}


# ---------------------------------------------------------
# MONITORING EVENTS
# ---------------------------------------------------------

@app.post("/api/sessions/{session_id}/events")
def create_event(
    session_id: int,
    body: NewEvent,
    user=Depends(current_user)
):
    with db() as c:
        session = c.execute(
            "SELECT * FROM sessions WHERE id=?",
            (session_id,)
        ).fetchone()

        if not session:
            raise HTTPException(404, "Session not found.")

        if user["role"] != "admin" and session["student_id"] != user["id"]:
            raise HTTPException(403, "This session does not belong to you.")

        cur = c.execute("""
            INSERT INTO events(
                session_id,category,severity,description,source,status,note,created_at
            )
            VALUES(?,?,?,?,?,'pending','',?)
        """, (
            session_id,
            body.category[:80],
            body.severity[:20],
            body.description[:1000],
            body.source[:80],
            now()
        ))
        event_id = cur.lastrowid
        c.commit()

    return {"ok": True, "event_id": event_id}


@app.get("/api/admin/events")
def admin_events(user=Depends(admin)):
    with db() as c:
        rows = c.execute("""
            SELECT e.*,s.student_id,s.exam_id,u.name AS student_name,
                   u.email AS student_email
            FROM events e
            JOIN sessions s ON s.id=e.session_id
            JOIN users u ON u.id=s.student_id
            ORDER BY e.id DESC
        """).fetchall()

    return [dict(r) for r in rows]


@app.patch("/api/admin/events/{event_id}/review")
def review_event(
    event_id: int,
    body: Review,
    user=Depends(admin)
):
    allowed = {"pending", "reviewed", "dismissed", "flagged"}

    if body.status not in allowed:
        raise HTTPException(
            400, "Status must be pending, reviewed, dismissed, or flagged."
        )

    with db() as c:
        cur = c.execute("""
            UPDATE events SET status=?,note=?
            WHERE id=?
        """, (body.status, body.note[:1000], event_id))

        if cur.rowcount == 0:
            raise HTTPException(404, "Event not found.")

        c.commit()

    return {"ok": True}
#part 3 begin

# ---------------------------------------------------------
# SCORE CALCULATION HELPERS
# ---------------------------------------------------------

def parse_answers(raw):
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return {
                int(item["question_id"]): str(item.get("answer", "")).strip()
                for item in data
                if isinstance(item, dict) and "question_id" in item
            }
    except (ValueError, TypeError, KeyError):
        pass
    return {}


def calculate_session_score(c, session):
    questions = c.execute("""
        SELECT id,correct_answer
        FROM questions
        WHERE exam_id=?
        ORDER BY position,id
    """, (session["exam_id"],)).fetchall()

    answers = parse_answers(session["answers"])
    total = len(questions)
    correct = 0
    available = 0

    for question in questions:
        key = (question["correct_answer"] or "").strip()
        if key:
            available += 1
            submitted = answers.get(question["id"], "")
            if hmac.compare_digest(submitted.casefold(), key.casefold()):
                correct += 1

    # Score percentage is calculated only against questions with answer keys.
    percent = round(100 * correct / available, 2) if available else None

    return {
        "total_questions": total,
        "graded_questions": available,
        "answered_questions": len(answers),
        "correct_answers": correct,
        "score_percent": percent
    }


def build_exam_report(c, exam_id, top_n=10):
    exam = c.execute(
        "SELECT * FROM exams WHERE id=?",
        (exam_id,)
    ).fetchone()

    if not exam:
        raise HTTPException(404, "Exam not found.")

    rows = c.execute("""
        SELECT s.*,u.name AS student_name,u.email AS student_email
        FROM sessions s
        JOIN users u ON u.id=s.student_id
        WHERE s.exam_id=? AND s.status='submitted'
        ORDER BY s.submitted_at ASC,s.id ASC
    """, (exam_id,)).fetchall()

    results = []

    for session in rows:
        score = calculate_session_score(c, session)

        # Unanswerable/ungraded sessions are not ranked.
        if score["score_percent"] is None:
            continue

        results.append({
            "session_id": session["id"],
            "student_id": session["student_id"],
            "student_name": session["student_name"],
            "student_email": session["student_email"],
            "submitted_at": session["submitted_at"],
            **score
        })

    results.sort(
        key=lambda x: (
            -x["score_percent"],
            -x["correct_answers"],
            x["submitted_at"] or "",
            x["session_id"]
        )
    )

    for rank, item in enumerate(results, start=1):
        item["rank"] = rank

    percentages = [r["score_percent"] for r in results]
    overall_average = (
        round(sum(percentages) / len(percentages), 2)
        if percentages else None
    )

    distribution = {
        "0-39": sum(0 <= x < 40 for x in percentages),
        "40-59": sum(40 <= x < 60 for x in percentages),
        "60-79": sum(60 <= x < 80 for x in percentages),
        "80-100": sum(80 <= x <= 100 for x in percentages)
    }

    return {
        "exam": {
            "id": exam["id"],
            "title": exam["title"],
            "description": exam["description"],
            "duration_minutes": exam["duration"]
        },
        "submitted_count": len(rows),
        "graded_count": len(results),
        "average_score": overall_average,
        "highest_score": max(percentages) if percentages else None,
        "lowest_score": min(percentages) if percentages else None,
        "distribution": distribution,
        "top_n": top_n,
        "results": results[:top_n]
    }


# ---------------------------------------------------------
# ADMIN: OVERALL ANALYTICS AND EXAM SCORE ANALYSIS
# ---------------------------------------------------------

@app.get("/api/admin/analytics")
def admin_analytics(user=Depends(admin)):
    with db() as c:
        students = c.execute("""
            SELECT COUNT(*) FROM users WHERE role='student'
        """).fetchone()[0]

        active_students = c.execute("""
            SELECT COUNT(*) FROM users
            WHERE role='student' AND is_active=1
        """).fetchone()[0]

        exams = c.execute(
            "SELECT COUNT(*) FROM exams"
        ).fetchone()[0]

        sessions = c.execute("""
            SELECT COUNT(*) FROM sessions WHERE status='submitted'
        """).fetchone()[0]

        pending_events = c.execute("""
            SELECT COUNT(*) FROM events WHERE status='pending'
        """).fetchone()[0]

        exam_rows = c.execute(
            "SELECT id,title FROM exams ORDER BY id"
        ).fetchall()

        exam_summary = []

        for exam in exam_rows:
            report = build_exam_report(c, exam["id"], top_n=1)
            exam_summary.append({
                "exam_id": exam["id"],
                "title": exam["title"],
                "submitted_count": report["submitted_count"],
                "graded_count": report["graded_count"],
                "average_score": report["average_score"],
                "highest_score": report["highest_score"]
            })

    return {
        "students": students,
        "active_students": active_students,
        "exams": exams,
        "submitted_sessions": sessions,
        "pending_events": pending_events,
        "exam_summary": exam_summary
    }


@app.get("/api/admin/exams/{exam_id}/score-analysis")
def exam_score_analysis(
    exam_id: int,
    top_n: int = 10,
    user=Depends(admin)
):
    if not 1 <= top_n <= 60:
        raise HTTPException(
            400, "top_n must be between 1 and 60."
        )

    with db() as c:
        report = build_exam_report(c, exam_id, top_n)

    # Baseline estimate based on earlier submitted scores for the same student
    # and exam. This is not a trained prediction model.
    with db() as c:
        for result in report["results"]:
            previous = c.execute("""
                SELECT answers
                FROM sessions
                WHERE student_id=? AND exam_id=?
                  AND status='submitted' AND id<>?
                ORDER BY submitted_at,id
            """, (
                result["student_id"],
                exam_id,
                result["session_id"]
            )).fetchall()

            prior_scores = []

            for old in previous:
                old_score = calculate_session_score(c, {
                    "exam_id": exam_id,
                    "answers": old["answers"]
                })

                if old_score["score_percent"] is not None:
                    prior_scores.append(old_score["score_percent"])

            result["previous_attempts"] = len(prior_scores)
            result["baseline_next_score_estimate"] = (
                round(sum(prior_scores) / len(prior_scores), 2)
                if prior_scores else None
            )

    report["analysis_note"] = (
        "Scores are calculated using configured answer keys. "
        "The next-score estimate is a historical-average baseline, "
        "not a trained AI prediction. Only submitted, gradable sessions "
        "are ranked."
    )

    return report


# ---------------------------------------------------------
# CSV EXPORT
# ---------------------------------------------------------

@app.get("/api/admin/exams/{exam_id}/score-analysis.csv")
def export_scores_csv(
    exam_id: int,
    top_n: int = 10,
    user=Depends(admin)
):
    if not 1 <= top_n <= 60:
        raise HTTPException(400, "top_n must be between 1 and 60.")

    with db() as c:
        report = build_exam_report(c, exam_id, top_n)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Rank", "Student Name", "Email", "Session ID",
        "Submitted At", "Score Percent", "Correct Answers",
        "Graded Questions", "Answered Questions",
        "Previous Attempts", "Baseline Next Score Estimate"
    ])

    with db() as c:
        for row in report["results"]:
            old_sessions = c.execute("""
                SELECT answers FROM sessions
                WHERE student_id=? AND exam_id=?
                  AND status='submitted' AND id<>?
            """, (
                row["student_id"], exam_id, row["session_id"]
            )).fetchall()

            previous_scores = []

            for old in old_sessions:
                score = calculate_session_score(c, {
                    "exam_id": exam_id,
                    "answers": old["answers"]
                })
                if score["score_percent"] is not None:
                    previous_scores.append(score["score_percent"])

            estimate = (
                round(sum(previous_scores) / len(previous_scores), 2)
                if previous_scores else ""
            )

            writer.writerow([
                row["rank"],
                row["student_name"],
                row["student_email"],
                row["session_id"],
                row["submitted_at"],
                row["score_percent"],
                row["correct_answers"],
                row["graded_questions"],
                row["answered_questions"],
                len(previous_scores),
                estimate
            ])

    content = "\ufeff" + output.getvalue()
    filename = f"exam-{exam_id}-top-{top_n}-scores.csv"

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ---------------------------------------------------------
# PDF EXPORT
# ---------------------------------------------------------

@app.get("/api/admin/exams/{exam_id}/score-analysis.pdf")
def export_scores_pdf(
    exam_id: int,
    top_n: int = 10,
    user=Depends(admin)
):
    if not 1 <= top_n <= 60:
        raise HTTPException(400, "top_n must be between 1 and 60.")

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )
    except ImportError:
        raise HTTPException(
            500, "PDF dependency missing. Run: pip install reportlab"
        )

    with db() as c:
        report = build_exam_report(c, exam_id, top_n)

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph("ExamGuard AI — Score Analysis Report", styles["Title"]),
        Spacer(1, 5 * mm),
        Paragraph(
            f"Exam: {report['exam']['title']}",
            styles["Heading2"]
        ),
        Paragraph(
            f"Submitted sessions: {report['submitted_count']} | "
            f"Gradable sessions: {report['graded_count']} | "
            f"Ranking limit: Top {top_n}",
            styles["Normal"]
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            f"Average: {report['average_score'] if report['average_score'] is not None else 'N/A'}% | "
            f"Highest: {report['highest_score'] if report['highest_score'] is not None else 'N/A'}% | "
            f"Lowest: {report['lowest_score'] if report['lowest_score'] is not None else 'N/A'}%",
            styles["Normal"]
        ),
        Spacer(1, 5 * mm)
    ]

    data = [[
        "Rank", "Student", "Email", "Session",
        "Score %", "Correct", "Graded", "Submitted"
    ]]

    for row in report["results"]:
        data.append([
            str(row["rank"]),
            Paragraph(str(row["student_name"]), styles["BodyText"]),
            Paragraph(str(row["student_email"]), styles["BodyText"]),
            str(row["session_id"]),
            f"{row['score_percent']:.2f}",
            str(row["correct_answers"]),
            str(row["graded_questions"]),
            str(row["submitted_at"] or "")
        ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[15*mm, 36*mm, 48*mm, 18*mm, 20*mm, 18*mm, 18*mm, 42*mm]
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23365b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8deea")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f3f6fb")
        ]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)
    ]))

    story.append(table)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "Note: Rankings use configured answer keys. Historical-average "
        "estimates are baseline statistics, not validated AI predictions. "
        "Monitoring cues are not proof of cheating.",
        styles["Italic"]
    ))

    document.build(story)
    buffer.seek(0)

    filename = f"exam-{exam_id}-top-{top_n}-scores.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ---------------------------------------------------------
# GEMINI: QUESTION AUTHORING AGENT
# ---------------------------------------------------------

@app.get("/api/admin/agent/gemini-status")
def gemini_status(user=Depends(admin)):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    if not key:
        return {
            "configured": False,
            "model": model,
            "message": "GEMINI_API_KEY is missing from the backend .env file."
        }

    try:
        import google.genai  # noqa: F401
    except ImportError:
        return {
            "configured": True,
            "sdk_installed": False,
            "model": model,
            "message": "Install the SDK: pip install google-genai"
        }

    return {
        "configured": True,
        "sdk_installed": True,
        "model": model,
        "message": "Configuration found. Use Test API to verify live access."
    }


@app.post("/api/admin/agent/gemini-test")
def gemini_test(user=Depends(admin)):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    if not key:
        raise HTTPException(
            400, "GEMINI_API_KEY is missing from the backend .env file."
        )

    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: ExamGuard Gemini connection OK"
        )
        text = (response.text or "").strip()

        if not text:
            raise RuntimeError("Gemini returned an empty response.")

        return {
            "ok": True,
            "model": model,
            "message": text
        }

    except Exception as exc:
        # Do not return credentials or the full request configuration.
        logger.exception("Gemini connectivity test failed")
        raise HTTPException(
            502,
            "Gemini request failed. Check API key, model availability, "
            "network access and quota. Details: "
            + str(exc)[:350]
        )


def extract_json(text):
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        raise ValueError("Model did not return a JSON object.")

    return json.loads(text[start:end + 1])



@app.post("/api/admin/agents/question-drafts")
@app.post("/api/admin/agent/generate-questions")
def generate_questions(
    body: AgentQuestionRequest,
    user=Depends(admin)
):

    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    if not key:
        raise HTTPException(
            400,
            "Gemini is not configured. Add GEMINI_API_KEY to backend .env."
        )

    try:
        from google import genai

        client = genai.Client(api_key=key)

        prompt = f"""
You are an educational multiple-choice question author.

Create exactly {body.count} MCQ drafts about this topic:
{body.topic}

Difficulty: {body.difficulty}

Return ONLY valid JSON in this schema:
{{
  "questions": [
    {{
      "prompt": "Question text",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Exact text of one option",
      "explanation": "Short explanation"
    }}
  ]
}}

Requirements:
- Exactly {body.count} questions.
- Four distinct options per question.
- Exactly one unambiguous correct answer.
- The correct_answer must exactly match one option.
- Do not include markdown fences.
- Do not create questions outside the specified topic.
- Keep explanations factual and concise.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt
        )

        parsed = extract_json(response.text or "")
        drafts = parsed.get("questions", [])

        if not isinstance(drafts, list) or len(drafts) != body.count:
            raise ValueError(
                f"Expected exactly {body.count} questions."
            )

        validated = []

        for item in drafts:
            if not isinstance(item, dict):
                raise ValueError("A question draft is not an object.")

            prompt_text = str(item.get("prompt", "")).strip()
            options = item.get("options")
            correct = str(item.get("correct_answer", "")).strip()
            explanation = str(item.get("explanation", "")).strip()

            if (
                not prompt_text
                or not isinstance(options, list)
                or len(options) != 4
            ):
                raise ValueError("A question has invalid fields.")

            options = [str(option).strip() for option in options]

            if (
                any(not option for option in options)
                or len(set(options)) != 4
                or correct not in options
            ):
                raise ValueError(
                    "Question options or correct answer are invalid."
                )

            validated.append({
                "prompt": prompt_text,
                "options": options,
                "correct_answer": correct,
                "explanation": explanation
            })

        return {
            "ok": True,
            "provider": "Google Gemini",
            "model": model,
            "topic": body.topic,
            "difficulty": body.difficulty,
            "questions": validated,
            "message": (
                "Drafts generated. Review and verify every answer "
                "before adding questions to an exam."
            )
        }

    
    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Gemini question generation failed")
        error_text = str(exc)

        if "503" in error_text or "UNAVAILABLE" in error_text:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Gemini is temporarily busy. Your existing questions "
                    "are safe. Please wait briefly and retry generation."
                )
            )

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Gemini API quota or rate limit reached. "
                    "Check your Google AI Studio quota and retry later."
                )
            )

        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini question generation failed. Check model access, "
                "API configuration, quota, and the server log."
            )
        )


# ---------------------------------------------------------
# ADMIN PROFILE AND SETTINGS
# ---------------------------------------------------------
@app.get("/api/admin/profile")
def get_admin_profile(user=Depends(admin)):
    with db() as c:
        row = c.execute(
            "SELECT id, name, email, role FROM users WHERE id=?",
            (user["id"],)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Administrator profile not found.")

    return dict(row)
@app.put("/api/admin/profile")
def update_admin_profile(
    body: ProfileUpdate,
    user=Depends(admin)
):
    name = body.name.strip()
    email = body.email.strip().lower()
    if len(name) < 2:
        raise HTTPException(400, "Display name must contain at least 2 characters.")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1] or any(ch.isspace() for ch in email):
        raise HTTPException(400, "Enter a valid email address.")

    with db() as c:
        row = c.execute(
            "SELECT * FROM users WHERE id=? AND role='admin'",
            (user["id"],)
        ).fetchone()

        if not row or not verify_password(
            body.current_password, row["password"]
        ):
            raise HTTPException(400, "Current password is incorrect.")

        existing = c.execute(
            "SELECT id FROM users WHERE lower(email)=? AND id<>?",
            (email, user["id"])
        ).fetchone()
        if existing:
            raise HTTPException(409, "That email is already used by another account.")

        email_changed = email != row["email"].strip().lower()
        password_changed = bool(body.new_password)
        password = hash_password(body.new_password) if password_changed else row["password"]

        c.execute(
            "UPDATE users SET name=?, email=?, password=? WHERE id=? AND role='admin'",
            (name, email, password, user["id"])
        )

        # Credential changes invalidate every active token for this admin.
        if email_changed or password_changed:
            c.execute("DELETE FROM tokens WHERE user_id=?", (user["id"],))

        c.commit()

    return {
        "ok": True,
        "message": (
            "Credentials updated. Please sign in again with your new email and password."
            if email_changed or password_changed
            else "Profile updated successfully."
        ),
        "reauth_required": bool(email_changed or password_changed),
        "user": {"id": user["id"], "name": name, "email": email, "role": "admin"}
    }

@app.get("/api/admin/session-history")
def admin_session_history(user=Depends(admin)):
    with db() as c:
        rows = c.execute("""
            SELECT s.id,s.student_id,s.exam_id,s.status,s.started_at,
                   s.submitted_at,u.name AS student_name,
                   u.email AS student_email,e.title AS exam_title
            FROM sessions s
            JOIN users u ON u.id=s.student_id
            JOIN exams e ON e.id=s.exam_id
            ORDER BY s.id DESC
        """).fetchall()

    result = []

    with db() as c:
        for row in rows:
            item = dict(row)
            item.update(calculate_session_score(c, row))
            result.append(item)

    return result


@app.get("/api/admin/sessions")
def admin_sessions(user=Depends(admin)):
    """Return all exam sessions for the administrator dashboard."""
    with db() as c:
        rows = c.execute("""
            SELECT
                s.id,
                s.id AS session_id,
                s.student_id,
                s.exam_id,
                s.status,
                s.started_at,
                s.submitted_at,
                s.answers,
                u.name AS student_name,
                u.email AS student_email,
                e.title AS exam_title
            FROM sessions AS s
            LEFT JOIN users AS u ON u.id = s.student_id
            LEFT JOIN exams AS e ON e.id = s.exam_id
            ORDER BY s.id DESC
        """).fetchall()

        results = []

        for row in rows:
            item = dict(row)

            score = calculate_session_score(c, {
                "exam_id": item["exam_id"],
                "answers": item["answers"] or "[]"
            })

            item.update(score)
            item.pop("answers", None)
            results.append(item)

    return results


@app.get("/api/admin/score-analysis")
def overall_score_analysis(user=Depends(admin)):
    """Aggregate answer-key scores across submitted sessions."""
    with db() as c:
        sessions = c.execute("""
            SELECT s.id, s.exam_id, s.answers, s.status,
                   e.title AS exam_title,
                   u.name AS student_name
            FROM sessions s
            JOIN exams e ON e.id = s.exam_id
            JOIN users u ON u.id = s.student_id
            WHERE s.status = 'submitted'
            ORDER BY s.submitted_at DESC
        """).fetchall()

        exams = c.execute(
            "SELECT id, title FROM exams ORDER BY title"
        ).fetchall()

        question_rows = c.execute("""
            SELECT id, exam_id, prompt, correct_answer
            FROM questions
            ORDER BY exam_id, position, id
        """).fetchall()

    qs_by_exam = {}
    for row in question_rows:
        q = dict(row)
        qs_by_exam.setdefault(q["exam_id"], []).append(q)

    scored_rows = []
    question_stats = {
        q["id"]: {
            "question_id": q["id"],
            "exam_id": q["exam_id"],
            "prompt": q["prompt"],
            "attempts": 0,
            "correct": 0
        }
        for q in (dict(row) for row in question_rows)
    }

    for sess_row in sessions:
        sess = dict(sess_row)
        questions = [
            q for q in qs_by_exam.get(sess["exam_id"], [])
            if q["correct_answer"]
        ]

        if not questions:
            continue

        try:
            raw_answers = json.loads(sess["answers"] or "[]")
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Invalid answers JSON for session %s",
                sess["id"]
            )
            raw_answers = []

        if not isinstance(raw_answers, list):
            raw_answers = []

        answers = {}
        for answer in raw_answers:
            if isinstance(answer, dict) and "question_id" in answer:
                answers[answer["question_id"]] = str(
                    answer.get("answer", "")
                )

        correct = 0
        for q in questions:
            answer = answers.get(q["id"], "")
            if answer:
                question_stats[q["id"]]["attempts"] += 1
                if answer == q["correct_answer"]:
                    correct += 1
                    question_stats[q["id"]]["correct"] += 1

        scored_rows.append({
            "session_id": sess["id"],
            "exam_id": sess["exam_id"],
            "exam_title": sess["exam_title"],
            "student_name": sess["student_name"],
            "score_percent": round(
                correct * 100 / len(questions), 1
            ),
            "correct": correct,
            "scored_questions": len(questions)
        })

    scores = [row["score_percent"] for row in scored_rows]

    distribution = {
        "0-39": sum(score < 40 for score in scores),
        "40-59": sum(40 <= score < 60 for score in scores),
        "60-79": sum(60 <= score < 80 for score in scores),
        "80-100": sum(score >= 80 for score in scores)
    }

    per_exam = []
    for exam_row in exams:
        exam = dict(exam_row)
        rows = [
            row for row in scored_rows
            if row["exam_id"] == exam["id"]
        ]
        exam_scores = [row["score_percent"] for row in rows]

        per_exam.append({
            "exam_id": exam["id"],
            "exam_title": exam["title"],
            "submitted_scored_sessions": len(rows),
            "average_score": (
                round(sum(exam_scores) / len(exam_scores), 1)
                if exam_scores else None
            ),
            "highest_score": max(exam_scores) if exam_scores else None,
            "lowest_score": min(exam_scores) if exam_scores else None
        })

    question_insights = []
    for stat in question_stats.values():
        stat["correct_rate"] = (
            round(stat["correct"] * 100 / stat["attempts"], 1)
            if stat["attempts"] else None
        )
        question_insights.append(stat)

    question_insights.sort(
        key=lambda item: (
            item["correct_rate"]
            if item["correct_rate"] is not None else 101,
            item["attempts"]
        )
    )

    logger.info(
        "Score analysis completed: %s scored submissions",
        len(scored_rows)
    )

    return {
        "submitted_scored_sessions": len(scored_rows),
        "overall_average_score": (
            round(sum(scores) / len(scores), 1)
            if scores else None
        ),
        "distribution": distribution,
        "by_exam": per_exam,
        "question_insights": question_insights[:20],
        "recent_scores": scored_rows[:50],
        "analysis_type": "descriptive answer-key analysis",
        "disclaimer": (
            "Scores are calculated from configured answer keys for "
            "submitted sessions only. This is descriptive analysis, "
            "not a trained AI prediction model. Low correct rates may "
            "indicate difficult or ambiguous questions and require "
            "educator review."
        )
    }


@app.get("/api/admin/sessions/{session_id}/analysis")
def analyze_admin_session(
    session_id: int,
    user=Depends(admin)
):
    """Return a transparent, answer-key-based session analysis."""

    with db() as c:
        row = c.execute("""
            SELECT
                s.id,
                s.exam_id,
                s.student_id,
                s.status,
                s.started_at,
                s.submitted_at,
                s.answers,
                u.name AS student_name,
                u.email AS student_email,
                e.title AS exam_title
            FROM sessions s
            JOIN users u ON u.id = s.student_id
            JOIN exams e ON e.id = s.exam_id
            WHERE s.id = ?
        """, (session_id,)).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Session not found."
            )

        session = dict(row)

        # Reuse the existing scoring helper in this backend.
        score = calculate_session_score(c, session)

        event_rows = c.execute("""
            SELECT severity, category, description
            FROM events
            WHERE session_id = ?
        """, (session_id,)).fetchall()

    score_percent = score["score_percent"]
    answered = score["answered_questions"]
    question_count = score["total_questions"]
    graded_questions = score["graded_questions"]
    correct = score["correct_answers"]

    if score_percent is None:
        score_outlook = "Not available"
        strengths = []
        recommendations = [
            "Add correct answer keys to the exam questions before "
            "calculating a score.",
            "Review the submitted answers after grading is available."
        ]
    else:
        score_outlook = (
            "Strong performance" if score_percent >= 80
            else "Developing performance" if score_percent >= 60
            else "Needs further review"
        )

        strengths = (
            ["Demonstrated strong performance on graded questions."]
            if score_percent >= 80 else []
        )

        recommendations = []
        if score_percent < 60:
            recommendations.append(
                "Review the relevant concepts and incorrect answers."
            )
        if answered < question_count:
            recommendations.append(
                "Review unanswered questions and exam completion."
            )
        if not recommendations:
            recommendations.append(
                "Continue practicing and review the detailed results."
            )

    high_severity = sum(
        1 for event in event_rows
        if str(event["severity"] or "").lower() == "high"
    )

    return {
        "session_id": session["id"],
        "student_name": session["student_name"],
        "student_email": session["student_email"],
        "exam_title": session["exam_title"],
        "status": session["status"],
        "answered": answered,
        "question_count": question_count,
        "scored_question_count": graded_questions,
        "correct": correct,
        "score_percent": score_percent,
        "score_outlook": score_outlook,
        "review_cue_count": len(event_rows),
        "high_severity_cues": high_severity,
        "strengths": strengths,
        "recommendations": recommendations,
        "model": "Transparent answer-key scoring baseline",
        "disclaimer": (
            "This is descriptive answer-key analysis, not a trained "
            "AI prediction. Monitoring cues require human review and "
            "are not proof of misconduct."
        )
    }

@app.get("/api/reports/events.csv")
def export_events_csv(user=Depends(admin)):
    """Export monitoring events to a downloadable CSV file."""

    with db() as c:
        rows = c.execute("""
            SELECT
                e.id,
                e.session_id,
                u.name AS student_name,
                e.category,
                e.severity,
                e.description,
                e.source,
                e.status,
                e.note,
                e.created_at
            FROM events AS e
            LEFT JOIN sessions AS s ON s.id = e.session_id
            LEFT JOIN users AS u ON u.id = s.student_id
            ORDER BY e.created_at DESC
        """).fetchall()

    columns = [
        "id", "session_id", "student_name", "category",
        "severity", "description", "source", "status",
        "note", "created_at"
    ]

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows([dict(row) for row in rows])

    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    output.close()

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                'attachment; filename="examguard-events.csv"'
        },
    )
@app.get("/api/reports/events.pdf")
def export_events_pdf(user=Depends(admin)):
    """Generate a downloadable PDF of monitoring event history."""

    with db() as c:
        rows = c.execute("""
            SELECT
                e.id,
                e.session_id,
                u.name AS student_name,
                e.category,
                e.severity,
                e.description,
                e.status,
                e.created_at
            FROM events AS e
            LEFT JOIN sessions AS s ON s.id = e.session_id
            LEFT JOIN users AS u ON u.id = s.student_id
            ORDER BY e.created_at DESC
        """).fetchall()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph("ExamGuard AI — Monitoring Events Report",
                  styles["Title"]),
        Paragraph(
            "Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Total events: " + str(len(rows)), styles["Normal"]),
        Spacer(1, 4 * mm),
    ]

    headers = [
        "ID", "Session", "Student", "Category",
        "Severity", "Description", "Status", "Created"
    ]
    data = [headers]

    for row in rows:
        values = [
            row["id"],
            row["session_id"],
            row["student_name"] or "Unknown",
            row["category"] or "",
            row["severity"] or "",
            row["description"] or "",
            row["status"] or "",
            row["created_at"] or "",
        ]
        data.append([
            Paragraph(str(value), styles["BodyText"])
            for value in values
        ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[
            10 * mm, 15 * mm, 30 * mm, 27 * mm,
            18 * mm, 80 * mm, 20 * mm, 35 * mm
        ],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23395d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f1f5f9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(table)
    document.build(story)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                'attachment; filename="examguard-events.pdf"'
        },
    )



# ---------------------------------------------------------
# BATCH SUBMITTED-SCORE REVIEW AGENT + FILTERED EXPORTS
# ---------------------------------------------------------
def build_batch_score_review(c):
    """Analyze every submitted session with a configured answer key.

    This is a transparent rule-based review agent, not an LLM or a
    trained predictive model. In-progress sessions are never queried.
    """
    rows = c.execute("""
        SELECT s.id AS session_id, s.student_id, s.exam_id, s.status,
               s.started_at, s.submitted_at, s.answers,
               u.name AS student_name, u.email AS student_email,
               e.title AS exam_title
        FROM sessions AS s
        JOIN users AS u ON u.id = s.student_id
        JOIN exams AS e ON e.id = s.exam_id
        WHERE lower(s.status) = 'submitted'
        ORDER BY s.submitted_at DESC, s.id DESC
    """).fetchall()

    reviewed = []
    skipped_no_key = 0
    for raw in rows:
        session = dict(raw)
        score = calculate_session_score(c, session)
        if score["score_percent"] is None:
            skipped_no_key += 1
            continue

        pct = score["score_percent"]
        if pct >= 80:
            outlook = "Strong performance"
            strengths = ["High accuracy on questions with configured answer keys."]
            recommendations = ["Maintain performance with mixed-topic practice.",
                               "Review missed questions to close remaining gaps."]
        elif pct >= 60:
            outlook = "Developing performance"
            strengths = ["Demonstrated understanding of some assessed concepts."]
            recommendations = ["Review incorrect answers against the course material.",
                               "Practice the lowest-performing topics before the next assessment."]
        else:
            outlook = "Needs further review"
            strengths = (["Some assessed questions were answered correctly."]
                         if score["correct_answers"] else [])
            recommendations = ["Revisit the core concepts covered by this exam.",
                               "Work through practice questions and review each incorrect answer."]

        reviewed.append({
            "session_id": session["session_id"],
            "student_id": session["student_id"],
            "student_name": session["student_name"],
            "student_email": session["student_email"],
            "exam_id": session["exam_id"],
            "exam_title": session["exam_title"],
            "status": "submitted",
            "started_at": session["started_at"],
            "submitted_at": session["submitted_at"],
            "score_percent": pct,
            "correct_answers": score["correct_answers"],
            "graded_questions": score["graded_questions"],
            "answered_questions": score["answered_questions"],
            "total_questions": score["total_questions"],
            "score_outlook": outlook,
            "strengths": strengths,
            "recommendations": recommendations,
            "review_agent": "ExamGuard rule-based score review agent"
        })

    reviewed.sort(key=lambda x: (-x["score_percent"], x["student_name"].casefold()))
    scores = [x["score_percent"] for x in reviewed]
    return {
        "reviewed_count": len(reviewed),
        "submitted_count": len(rows),
        "skipped_without_answer_key": skipped_no_key,
        "in_progress_excluded": True,
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "highest_score": max(scores) if scores else None,
        "lowest_score": min(scores) if scores else None,
        "students": reviewed,
        "agent": "ExamGuard rule-based score review agent",
        "disclaimer": ("Scores are calculated from configured answer keys for submitted exams only. "
                       "The agent generates transparent rule-based feedback; it is not a trained AI model. "
                       "In-progress exams are excluded. Educators should verify results before making decisions.")
    }


@app.get("/api/admin/score-analysis/batch-review")
def batch_score_review(user=Depends(admin)):
    """Review all submitted, scoreable assessments in one request."""
    with db() as c:
        return build_batch_score_review(c)


@app.get("/api/reports/score-review.csv")
def export_batch_score_review_csv(user=Depends(admin)):
    """Download only score-reviewed submitted exams; never in-progress sessions."""
    with db() as c:
        report = build_batch_score_review(c)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Session ID", "Student ID", "Student Name", "Student Email",
                     "Exam", "Status", "Submitted At", "Score Percent",
                     "Correct Answers", "Graded Questions", "Answered Questions",
                     "Total Questions", "Score Outlook", "Strengths", "Recommendations",
                     "Review Agent"])
    for row in report["students"]:
        writer.writerow([row["session_id"], row["student_id"], row["student_name"],
                         row["student_email"], row["exam_title"], row["status"],
                         row["submitted_at"] or "", row["score_percent"],
                         row["correct_answers"], row["graded_questions"],
                         row["answered_questions"], row["total_questions"],
                         row["score_outlook"], " | ".join(row["strengths"]),
                         " | ".join(row["recommendations"]), row["review_agent"]])
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                     headers={"Content-Disposition": 'attachment; filename="examguard-submitted-score-review.csv"'})


@app.get("/api/reports/score-review.pdf")
def export_batch_score_review_pdf(user=Depends(admin)):
    """Download a PDF containing only submitted sessions with calculated scores."""
    from xml.sax.saxutils import escape
    with db() as c:
        report = build_batch_score_review(c)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=10*mm, leftMargin=10*mm,
                            topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph("ExamGuard AI — Batch Submitted Score Review", styles["Title"]),
             Spacer(1, 3*mm),
             Paragraph(escape(f"Reviewed scored submissions: {report['reviewed_count']} | "
                              f"Submitted sessions: {report['submitted_count']} | "
                              f"Skipped (no answer key): {report['skipped_without_answer_key']}"), styles["Normal"]),
             Paragraph(escape(report["disclaimer"]), styles["BodyText"]), Spacer(1, 5*mm)]
    data = [["Student", "Email", "Exam", "Score", "Correct/Graded", "Outlook", "Submitted"]]
    for row in report["students"]:
        data.append([
            Paragraph(escape(str(row["student_name"] or "")), styles["BodyText"]),
            Paragraph(escape(str(row["student_email"] or "")), styles["BodyText"]),
            Paragraph(escape(str(row["exam_title"] or "")), styles["BodyText"]),
            f"{row['score_percent']:.1f}%",
            f"{row['correct_answers']}/{row['graded_questions']}",
            Paragraph(escape(row["score_outlook"]), styles["BodyText"]),
            Paragraph(escape(str(row["submitted_at"] or "")), styles["BodyText"]),
        ])
    if len(data) == 1:
        data.append([Paragraph("No submitted exams with configured answer keys were available.", styles["BodyText"]), "", "", "", "", "", ""])
    table = Table(data, repeatRows=1, colWidths=[30*mm, 43*mm, 42*mm, 18*mm, 25*mm, 32*mm, 42*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#23395d")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(table)
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="examguard-submitted-score-review.pdf"'})

# ---------------------------------------------------------
# STUDENT: SESSION HISTORY
# ---------------------------------------------------------

@app.get("/api/sessions/mine")
def my_sessions(user=Depends(current_user)):
    """Return session history belonging only to the logged-in student."""

    if user["role"] != "student":
        raise HTTPException(
            status_code=403,
            detail="Student access required."
        )

    with db() as c:
        rows = c.execute("""
            SELECT
                s.id,
                s.student_id,
                s.exam_id,
                s.status,
                s.started_at,
                s.submitted_at,
                e.title AS exam_title,
                (
                    SELECT COUNT(*)
                    FROM events ev
                    WHERE ev.session_id = s.id
                ) AS event_count
            FROM sessions s
            LEFT JOIN exams e ON e.id = s.exam_id
            WHERE s.student_id = ?
            ORDER BY s.id DESC
        """, (user["id"],)).fetchall()

    return [dict(row) for row in rows]

@app.put("/api/profile")
def update_profile(
    payload: dict,
    user=Depends(current_user)
):
    name = payload.get("name", "").strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name is required"
        )

    with db() as c:
        c.execute(
            "UPDATE users SET name = ? WHERE id = ?",
            (name, user["id"])
        )
        c.commit()

        updated_user = c.execute(
            "SELECT id, name, email FROM users WHERE id = ?",
            (user["id"],)
        ).fetchone()

    return dict(updated_user)

@app.put("/api/profile")
def update_profile(
    body: StudentProfileUpdate,
    user=Depends(current_user)
):
    if user["role"] != "student":
        raise HTTPException(
            status_code=403,
            detail="Student profile access only."
        )

    name = body.name.strip()
    email = body.email.strip().lower()

    if (
        "@" not in email
        or "." not in email.rsplit("@", 1)[-1]
        or any(ch.isspace() for ch in email)
    ):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address."
        )

    with db() as c:
        row = c.execute(
            "SELECT * FROM users WHERE id=? AND role='student'",
            (user["id"],)
        ).fetchone()

        if not row or not verify_password(
            body.current_password, row["password"]
        ):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect."
            )

        existing = c.execute(
            "SELECT id FROM users WHERE lower(email)=? AND id<>?",
            (email, user["id"])
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="That email is already used by another account."
            )

        c.execute(
            "UPDATE users SET name=?, email=? WHERE id=? AND role='student'",
            (name, email, user["id"])
        )
        c.commit()

    return {
        "ok": True,
        "message": "Student profile updated successfully.",
        "user": {
            "id": user["id"],
            "name": name,
            "email": email,
            "role": "student"
        }
    }


    # Keep scoring logic consistent with the existing uploaded
    # overall_score_analysis() implementation.
    # Do not replace the existing implementation if it is present.
# End of backend/main.py