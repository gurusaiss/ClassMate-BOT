from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    Boolean, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    name = Column(String)
    invite_code = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    students = relationship("Student", back_populates="teacher")
    assignments = relationship("Assignment", back_populates="teacher")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    name = Column(String)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    teacher = relationship("Teacher", back_populates="students")
    submissions = relationship("Submission", back_populates="student")

    @property
    def assignments(self):
        return [s.assignment for s in self.submissions]


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    student_telegram_id = Column(String, ForeignKey("students.telegram_id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    raw_instruction = Column(Text)           # original teacher message
    deadline = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Assignment material file (teacher attached a PDF/doc/photo with the assignment)
    material_file_id   = Column(String)      # Telegram file_id
    material_file_type = Column(String)      # "photo" | "document" | "audio" | "video"
    material_file_name = Column(String)      # original filename

    teacher = relationship("Teacher", back_populates="assignments")
    submission = relationship("Submission", back_populates="assignment", uselist=False)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(String, default="pending")   # pending | in_progress | completed
    progress_notes = Column(Text, default="")    # accumulated progress messages
    submission_text = Column(Text)
    file_id = Column(String)                     # Telegram file_id for photo/document
    file_type = Column(String)                   # "photo" | "document" | None
    submitted_at = Column(DateTime)
    feedback = Column(Text)
    feedback_at = Column(DateTime)
    last_reminded_at = Column(DateTime)
    reminder_count = Column(Integer, default=0)

    assignment = relationship("Assignment", back_populates="submission")
    student = relationship("Student", back_populates="submissions")


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
