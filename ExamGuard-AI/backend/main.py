import os, sqlite3, secrets, csv, io, json
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("EXAMGUARD_DB_PATH", str(ROOT / "examguard.db"))
app = FastAPI(title="ExamGuard AI", version="1.0.0")
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
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT);
        CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, title TEXT, description TEXT, duration INTEGER);
        CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, exam_id INTEGER, prompt TEXT, options TEXT, position INTEGER);
        CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, student_id INTEGER, exam_id INTEGER, status TEXT, started_at TEXT, submitted_at TEXT, answers TEXT DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, session_id INTEGER, category TEXT, severity TEXT, description TEXT, source TEXT, status TEXT DEFAULT 'pending', note TEXT DEFAULT '', created_at TEXT);
        CREATE TABLE IF NOT EXISTS tokens(token TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT);
        """)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.executemany("INSERT INTO users VALUES(?,?,?,?,?)", [
                (1,"Aarav Student","student@examguard.local","StudentDemo123!","student"),
                (2,"Exam Administrator","admin@examguard.local","AdminDemo123!","admin")])
        if c.execute("SELECT COUNT(*) FROM exams").fetchone()[0] == 0:
            c.execute("INSERT INTO exams VALUES(1,?,?,20)", ("Deep Learning Fundamentals","Practice assessment covering neural-network concepts."))
            questions = [
                ("Which layer commonly applies a non-linear activation?", ["Dense layer with activation","Input file","Database index","HTTP route"]),
                ("What is an epoch in model training?", ["One full pass over training data","A CSS rule","A database backup","A browser tab"]),
                ("Which metric is useful when false positives matter?", ["Precision","File size","Screen width","Latency only"]),
                ("What does overfitting mean?", ["Good training performance but poor generalization","No model parameters","Server offline","Always balanced data"]),
                ("Why keep a validation set?", ["Assess model choices on held-out data","Store passwords","Render icons","Replace training data"])
            ]
            c.executemany("INSERT INTO questions(exam_id,prompt,options,position) VALUES(1,?,?,?)",
                          [(p,json.dumps(o),i+1) for i,(p,o) in enumerate(questions)])
        c.commit()

@app.on_event("startup")
def startup():
    init_db()

def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401,"Please sign in.")
    with db() as c:
        row = c.execute("SELECT u.id,u.name,u.email,u.role FROM tokens t JOIN users u ON u.id=t.user_id WHERE t.token=?",
                        (authorization[7:].strip(),)).fetchone()
    if not row:
        raise HTTPException(401,"Session expired. Sign in again.")
    return dict(row)

def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403,"Administrator access required.")
    return user

class Login(BaseModel):
    email: str
    password: str
class StartSession(BaseModel):
    exam_id: int
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

@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"status":"ok","mode":"educational-demo"}

@app.post("/api/auth/login")
def login(body: Login):
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND password=?",
                        (body.email.strip(),body.password)).fetchone()
        if not row:
            raise HTTPException(401,"Invalid demo credentials.")
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO tokens VALUES(?,?,?)",(token,row["id"],now()))
        c.commit()
        return {"token":token,"user":{"id":row["id"],"name":row["name"],"email":row["email"],"role":row["role"]}}

@app.get("/api/me")
def me(user=Depends(current_user)):
    return user

@app.get("/api/exams")
def exams(user=Depends(current_user)):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT id,title,description,duration AS duration_minutes FROM exams")]

@app.get("/api/exams/{exam_id}")
def exam(exam_id: int, user=Depends(current_user)):
    with db() as c:
        e = c.execute("SELECT id,title,description,duration AS duration_minutes FROM exams WHERE id=?",(exam_id,)).fetchone()
        if not e: raise HTTPException(404,"Exam not found.")
        qs = c.execute("SELECT id,prompt,options,position FROM questions WHERE exam_id=? ORDER BY position",(exam_id,)).fetchall()
        result = dict(e); result["questions"] = [{"id":q["id"],"prompt":q["prompt"],"options":json.loads(q["options"]),"position":q["position"]} for q in qs]
        return result

@app.post("/api/sessions")
def start_session(body: StartSession, user=Depends(current_user)):
    if user["role"] != "student": raise HTTPException(403,"Only students can start exams.")
    with db() as c:
        e = c.execute("SELECT id FROM exams WHERE id=?",(body.exam_id,)).fetchone()
        if not e: raise HTTPException(404,"Exam not found.")
        cur = c.execute("INSERT INTO sessions(student_id,exam_id,status,started_at) VALUES(?,?,'in_progress',?)",(user["id"],body.exam_id,now()))
        sid = cur.lastrowid; c.commit()
    return {"id":sid,"status":"in_progress","exam":get_exam_data(body.exam_id)}

def get_exam_data(exam_id):
    with db() as c:
        e=c.execute("SELECT id,title,description,duration AS duration_minutes FROM exams WHERE id=?",(exam_id,)).fetchone()
        qs=c.execute("SELECT id,prompt,options,position FROM questions WHERE exam_id=? ORDER BY position",(exam_id,)).fetchall()
        d=dict(e); d["questions"]=[{"id":q["id"],"prompt":q["prompt"],"options":json.loads(q["options"]),"position":q["position"]} for q in qs]
        return d

def sessions_for(user, all_sessions=False):
    sql="""SELECT s.id,s.student_id,s.exam_id,s.status,s.started_at,s.submitted_at,u.name AS student_name,e.title AS exam_title,
    (SELECT COUNT(*) FROM events v WHERE v.session_id=s.id) AS event_count
    FROM sessions s JOIN users u ON u.id=s.student_id JOIN exams e ON e.id=s.exam_id"""
    args=()
    if not all_sessions:
        sql+=" WHERE s.student_id=?"; args=(user["id"],)
    sql+=" ORDER BY s.started_at DESC"
    with db() as c: return [dict(r) for r in c.execute(sql,args)]

@app.get("/api/sessions/mine")
def my_sessions(user=Depends(current_user)):
    return sessions_for(user)

@app.post("/api/sessions/{sid}/submit")
def submit(sid: int, body: Submit, user=Depends(current_user)):
    with db() as c:
        s=c.execute("SELECT student_id FROM sessions WHERE id=?",(sid,)).fetchone()
        if not s: raise HTTPException(404,"Session not found.")
        if user["role"]!="admin" and s["student_id"]!=user["id"]: raise HTTPException(403,"Not your session.")
        c.execute("UPDATE sessions SET status='submitted',submitted_at=?,answers=? WHERE id=?",(now(),json.dumps([a.model_dump() for a in body.answers]),sid)); c.commit()
    return {"ok":True,"status":"submitted","message":"Exam submitted. Review cues are not proof of misconduct."}

@app.post("/api/sessions/{sid}/events")
def create_event(sid: int, body: NewEvent, user=Depends(current_user)):
    with db() as c:
        s=c.execute("SELECT student_id FROM sessions WHERE id=?",(sid,)).fetchone()
        if not s: raise HTTPException(404,"Session not found.")
        if user["role"]!="admin" and s["student_id"]!=user["id"]: raise HTTPException(403,"Not your session.")
        cur=c.execute("INSERT INTO events(session_id,category,severity,description,source,status,note,created_at) VALUES(?,?,?,?,?,'pending','',?)",
                      (sid,body.category,body.severity,body.description,body.source,now())); c.commit()
        return {"ok":True,"id":cur.lastrowid}

def event_data():
    with db() as c:
        sql="""SELECT v.*,u.name AS student_name FROM events v JOIN sessions s ON s.id=v.session_id JOIN users u ON u.id=s.student_id ORDER BY v.created_at DESC"""
        return [dict(r) for r in c.execute(sql)]

@app.get("/api/admin/sessions")
def admin_sessions(user=Depends(admin)):
    return sessions_for(user,True)

@app.get("/api/admin/events")
def admin_events(user=Depends(admin)):
    return event_data()

@app.patch("/api/admin/events/{event_id}")
def review_event(event_id: int, body: Review, user=Depends(admin)):
    if body.status not in ("pending","reviewed","dismissed"): raise HTTPException(400,"Invalid status.")
    with db() as c:
        cur=c.execute("UPDATE events SET status=?,note=? WHERE id=?",(body.status,body.note.strip(),event_id)); c.commit()
        if cur.rowcount==0: raise HTTPException(404,"Event not found.")
    return {"ok":True,"status":body.status}

@app.get("/api/reports/events.csv")
def report(user=Depends(admin)):
    rows=event_data(); out=io.StringIO()
    fields=["id","session_id","student_name","category","severity","description","source","status","note","created_at"]
    writer=csv.DictWriter(out,fieldnames=fields); writer.writeheader()
    for r in rows: writer.writerow({k:r.get(k,"") for k in fields})
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=examguard-events.csv"})
