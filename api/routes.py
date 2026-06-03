"""
FastAPI routes — Teacher Web UI, Student Web UI, File Proxy, Inline Actions.
"""
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx
import config
from db.models import SessionLocal
from db import crud

app = FastAPI(title="ClassMate")
templates = Jinja2Templates(directory="api/templates")

def format_deadline(dt: datetime) -> str:
    if not dt:
        return "N/A"
    days = (dt - datetime.utcnow()).days
    suffix = f" ({days}d left)" if days >= 0 else f" ({abs(days)}d overdue)"
    return dt.strftime("%b %d, %Y") + suffix

templates.env.filters["deadline"] = format_deadline


# ── Home ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = SessionLocal()
    try:
        from db.models import Teacher, Student, Assignment, Submission
        teachers  = db.query(Teacher).all()
        students  = db.query(Student).all()
        total_a   = db.query(Assignment).count()
        completed = db.query(Submission).filter(Submission.status == "completed").count()
        pending   = db.query(Submission).filter(Submission.status.in_(["pending","in_progress"])).count()
        return templates.TemplateResponse("home.html", {
            "request": request,
            "teachers": teachers,
            "students": students,
            "total_assignments": total_a,
            "completed": completed,
            "pending": pending,
        })
    finally:
        db.close()


# ── Teacher UI ────────────────────────────────────────────────────────────────

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_list(request: Request):
    db = SessionLocal()
    try:
        from db.models import Teacher
        teachers = db.query(Teacher).all()
        return templates.TemplateResponse("teacher_list.html", {
            "request": request, "teachers": teachers,
        })
    finally:
        db.close()


@app.get("/teacher/{teacher_id}", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, teacher_id: int,
                             status_filter: str = Query(default="all"),
                             student_filter: str = Query(default="")):
    db = SessionLocal()
    try:
        from db.models import Teacher
        teacher = db.query(Teacher).filter_by(id=teacher_id).first()
        if not teacher:
            raise HTTPException(404, "Teacher not found")

        students = crud.get_students_by_teacher(db, teacher_id)
        student_data = []
        for s in students:
            if student_filter and student_filter.lower() not in s.name.lower():
                continue
            assignments = crud.get_assignments_for_student(db, s.telegram_id)
            filtered = []
            for a in assignments:
                sub = a.submission
                if status_filter != "all":
                    if status_filter == "overdue":
                        if not sub or sub.status == "completed" or (a.deadline - datetime.utcnow()).days >= 0:
                            continue
                    elif sub and sub.status != status_filter:
                        continue
                filtered.append({"assignment": a, "submission": sub})
            student_data.append({"student": s, "assignments": filtered, "all_assignments": assignments})

        # Analytics data
        now = datetime.utcnow()
        analytics = _build_teacher_analytics(students, now)

        return templates.TemplateResponse("teacher_dashboard.html", {
            "request": request,
            "teacher": teacher,
            "student_data": student_data,
            "now": now,
            "status_filter": status_filter,
            "student_filter": student_filter,
            "analytics": analytics,
        })
    finally:
        db.close()


def _build_teacher_analytics(students, now):
    total = pending = in_progress = completed = overdue = 0
    for s in students:
        for sub in s.submissions:
            total += 1
            st = sub.status
            if st == "completed":
                completed += 1
            elif st == "in_progress":
                in_progress += 1
            else:
                # check if overdue
                if sub.assignment and (sub.assignment.deadline - now).days < 0:
                    overdue += 1
                else:
                    pending += 1
    return {
        "total": total, "pending": pending,
        "in_progress": in_progress, "completed": completed, "overdue": overdue,
        "students": len(students),
    }


# ── Students UI ───────────────────────────────────────────────────────────────

@app.get("/students", response_class=HTMLResponse)
async def student_list(request: Request, teacher: int = Query(default=None),
                        search: str = Query(default="")):
    db = SessionLocal()
    try:
        from db.models import Student, Teacher
        if teacher:
            students = crud.get_students_by_teacher(db, teacher)
            filter_teacher = db.query(Teacher).filter_by(id=teacher).first()
        else:
            students = db.query(Student).all()
            filter_teacher = None
        if search:
            students = [s for s in students if search.lower() in s.name.lower()]
        return templates.TemplateResponse("student_list.html", {
            "request": request,
            "students": students,
            "filter_teacher": filter_teacher,
            "search": search,
        })
    finally:
        db.close()


@app.get("/student/{telegram_id}", response_class=HTMLResponse)
async def student_dashboard(request: Request, telegram_id: str,
                             status_filter: str = Query(default="all")):
    db = SessionLocal()
    try:
        student = crud.get_student_by_telegram_id(db, telegram_id)
        if not student:
            raise HTTPException(404, "Student not found")

        assignments = crud.get_assignments_for_student(db, telegram_id)
        now = datetime.utcnow()
        assignment_data = []
        for a in assignments:
            sub = a.submission
            if status_filter != "all":
                if status_filter == "overdue":
                    if not sub or sub.status == "completed" or (a.deadline - now).days >= 0:
                        continue
                elif sub and sub.status != status_filter:
                    continue
            assignment_data.append({"assignment": a, "submission": sub})

        return templates.TemplateResponse("student_dashboard.html", {
            "request": request,
            "student": student,
            "assignment_data": assignment_data,
            "all_assignments": assignments,
            "now": now,
            "status_filter": status_filter,
        })
    finally:
        db.close()


# ── Inline Feedback (Teacher → Student via Web UI) ────────────────────────────

@app.post("/api/feedback/{submission_id}")
async def post_feedback(submission_id: int, feedback: str = Form(...)):
    db = SessionLocal()
    try:
        from db.models import Submission
        sub = db.query(Submission).filter_by(id=submission_id).first()
        if not sub:
            raise HTTPException(404, "Submission not found")
        from agents.teacher_agent import reformat_feedback
        formatted = reformat_feedback(feedback, sub.student.name)
        crud.save_feedback(db, sub, formatted)

        # Try to send via Telegram bot (best-effort — safe across threads)
        try:
            from bot.bot_instance import get_bot
            import asyncio, threading
            bot = get_bot()
            if bot:
                from agents.student_agent import deliver_feedback
                msg = deliver_feedback(sub.student.name, sub.assignment.title, formatted)

                async def _send():
                    await bot.send_message(
                        chat_id=sub.student.telegram_id,
                        text=f"📝 Feedback from your teacher:\n\n{msg}"
                    )

                # Spin up a fresh event loop in a background thread — avoids
                # "no running event loop" errors when called from a sync context
                def _run():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_send())
                    loop.close()

                threading.Thread(target=_run, daemon=True).start()
        except Exception:
            pass  # Telegram send is best-effort from web

        return {"ok": True, "feedback": formatted}
    finally:
        db.close()


# ── File Proxy (serve Telegram files for download/view) ──────────────────────

@app.get("/api/file/{file_id:path}")
async def proxy_file(file_id: str, download: bool = Query(default=False)):
    """Proxy Telegram file for in-browser view or download."""
    token = config.TELEGRAM_BOT_TOKEN
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id}
        )
        data = r.json()
        if not data.get("ok"):
            raise HTTPException(404, "File not found on Telegram")
        file_path = data["result"]["file_path"]
        file_url  = f"https://api.telegram.org/file/bot{token}/{file_path}"
    return RedirectResponse(url=file_url, status_code=302)


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.get("/api/teacher/{teacher_id}/students")
async def api_teacher_students(teacher_id: int):
    db = SessionLocal()
    try:
        students = crud.get_students_by_teacher(db, teacher_id)
        return [
            {
                "id": s.id, "name": s.name, "username": s.username,
                "assignments": [
                    {
                        "id": a.id, "title": a.title,
                        "deadline": a.deadline.isoformat(),
                        "status": a.submission.status if a.submission else "unknown",
                        "progress_notes": a.submission.progress_notes if a.submission else "",
                        "feedback": a.submission.feedback if a.submission else None,
                    }
                    for a in crud.get_assignments_for_student(db, s.telegram_id)
                ]
            }
            for s in students
        ]
    finally:
        db.close()

@app.get("/api/student/{telegram_id}/assignments")
async def api_student_assignments(telegram_id: str):
    db = SessionLocal()
    try:
        student = crud.get_student_by_telegram_id(db, telegram_id)
        if not student:
            raise HTTPException(404)
        return [
            {
                "id": a.id, "title": a.title, "description": a.description,
                "deadline": a.deadline.isoformat(),
                "status": a.submission.status if a.submission else "unknown",
                "feedback": a.submission.feedback if a.submission else None,
                "submitted_at": a.submission.submitted_at.isoformat() if a.submission and a.submission.submitted_at else None,
            }
            for a in crud.get_assignments_for_student(db, telegram_id)
        ]
    finally:
        db.close()

@app.get("/api/analytics")
async def api_analytics():
    db = SessionLocal()
    try:
        from db.models import Teacher, Student, Assignment, Submission
        return {
            "teachers":    db.query(Teacher).count(),
            "students":    db.query(Student).count(),
            "assignments": db.query(Assignment).count(),
            "completed":   db.query(Submission).filter_by(status="completed").count(),
            "pending":     db.query(Submission).filter(Submission.status.in_(["pending","in_progress"])).count(),
        }
    finally:
        db.close()
