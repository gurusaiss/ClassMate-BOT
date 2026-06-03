import secrets
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from .models import Teacher, Student, Assignment, Submission


# ── Teachers ──────────────────────────────────────────────────────────────────

def get_teacher_by_telegram_id(db: Session, telegram_id: str) -> Optional[Teacher]:
    return db.query(Teacher).filter(Teacher.telegram_id == telegram_id).first()


def get_teacher_by_invite_code(db: Session, invite_code: str) -> Optional[Teacher]:
    return db.query(Teacher).filter(Teacher.invite_code == invite_code).first()


def create_teacher(db: Session, telegram_id: str, name: str, username: str = "") -> Teacher:
    teacher = Teacher(
        telegram_id=telegram_id,
        name=name,
        username=username,
        invite_code=secrets.token_urlsafe(8),
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


def get_all_teachers(db: Session) -> list[Teacher]:
    return db.query(Teacher).all()


# ── Students ──────────────────────────────────────────────────────────────────

def get_student_by_telegram_id(db: Session, telegram_id: str) -> Optional[Student]:
    return db.query(Student).filter(Student.telegram_id == telegram_id).first()


def create_student(db: Session, telegram_id: str, name: str, username: str, teacher: Teacher) -> Student:
    student = Student(
        telegram_id=telegram_id,
        name=name,
        username=username,
        teacher_id=teacher.id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def get_students_by_teacher(db: Session, teacher_id: int) -> list[Student]:
    return db.query(Student).filter(Student.teacher_id == teacher_id).all()


# ── Assignments ───────────────────────────────────────────────────────────────

def create_assignment(
    db: Session,
    teacher: Teacher,
    student_telegram_id: str,
    title: str,
    description: str,
    deadline: datetime,
    raw_instruction: str = "",
    material_file_id: str = "",
    material_file_type: str = "",
    material_file_name: str = "",
) -> Assignment:
    assignment = Assignment(
        teacher_id=teacher.id,
        student_telegram_id=student_telegram_id,
        title=title,
        description=description,
        deadline=deadline,
        raw_instruction=raw_instruction,
        material_file_id=material_file_id,
        material_file_type=material_file_type,
        material_file_name=material_file_name,
    )
    db.add(assignment)
    db.flush()

    student = get_student_by_telegram_id(db, student_telegram_id)
    submission = Submission(
        assignment_id=assignment.id,
        student_id=student.id,
        status="pending",
    )
    db.add(submission)
    db.commit()
    db.refresh(assignment)
    return assignment


def get_assignments_for_student(db: Session, student_telegram_id: str) -> list[Assignment]:
    return db.query(Assignment).filter(
        Assignment.student_telegram_id == student_telegram_id
    ).all()


def get_active_submissions(db: Session) -> list[Submission]:
    return db.query(Submission).filter(
        Submission.status.in_(["pending", "in_progress"])
    ).all()


def get_submission_by_assignment(db: Session, assignment_id: int) -> Optional[Submission]:
    return db.query(Submission).filter(Submission.assignment_id == assignment_id).first()


# ── Submissions ───────────────────────────────────────────────────────────────

def update_submission_progress(db: Session, submission: Submission, note: str, status: str = "in_progress"):
    existing = submission.progress_notes or ""
    submission.progress_notes = (existing + f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {note}").strip()
    submission.status = status
    db.commit()
    db.refresh(submission)
    return submission


def mark_submission_complete(
    db: Session,
    submission: Submission,
    text: str = "",
    file_id: str = "",
    file_type: str = "",
):
    submission.status = "completed"
    submission.submission_text = text
    submission.file_id = file_id
    submission.file_type = file_type
    submission.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(submission)
    return submission


def save_feedback(db: Session, submission: Submission, feedback: str):
    submission.feedback = feedback
    submission.feedback_at = datetime.utcnow()
    db.commit()
    db.refresh(submission)
    return submission


def update_reminder_timestamp(db: Session, submission: Submission):
    submission.last_reminded_at = datetime.utcnow()
    submission.reminder_count = (submission.reminder_count or 0) + 1
    db.commit()
