"""
Summariser Agent
Produces status updates the teacher receives proactively.
"""
from datetime import datetime
from .llm import call_llm

SUMMARY_SYSTEM = """You are a classroom assistant producing a status report for a teacher.
Given a list of students and their assignment statuses, write a concise, scannable summary.
Format as bullet points. Include: student name, assignment, status, days until deadline.
Flag any overdue or at-risk students. Be factual and brief."""

PROACTIVE_UPDATE_SYSTEM = """You are a classroom assistant sending the teacher a proactive daily update.
The teacher asked to receive summaries of their students' progress.
Write a brief, informative message (no more than 5-6 lines) summarising the current state.
Highlight: who has completed work, who needs attention, any upcoming deadlines."""


def generate_class_summary(students_data: list[dict]) -> str:
    """
    students_data: list of {name, assignment_title, status, days_left, progress_notes}
    """
    if not students_data:
        return "No active students or assignments at the moment."

    lines = []
    for s in students_data:
        days = s.get("days_left", 0)
        deadline_str = f"{days} days left" if days >= 0 else f"{abs(days)} days OVERDUE"
        lines.append(
            f"- {s['name']}: {s['assignment_title']} | {s['status']} | {deadline_str}"
            + (f" | Last update: {s['progress_notes'][-100:]}" if s.get('progress_notes') else "")
        )

    context = "Student statuses:\n" + "\n".join(lines)
    return call_llm(PROACTIVE_UPDATE_SYSTEM, context)


def generate_completion_notification(teacher_name: str, student_name: str,
                                      assignment_title: str, submission_text: str,
                                      has_file: bool) -> str:
    """Notify teacher that a student has submitted."""
    system = "You are a classroom assistant. Notify the teacher that a student has completed an assignment. Be brief (2-3 sentences). Ask if they'd like to provide feedback."
    context = f"""Teacher: {teacher_name}
Student: {student_name}
Assignment: {assignment_title}
Submission: {submission_text[:300] if submission_text else '(no text)'}
Has file/photo: {has_file}"""
    return call_llm(system, context)
