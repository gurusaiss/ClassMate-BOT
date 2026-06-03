"""
Teacher Agent
Handles: parsing assignment instructions, generating status summaries, collecting feedback.
"""
from datetime import datetime, timedelta
from .llm import call_llm, call_llm_json

PARSE_SYSTEM = """You are a teacher assistant that parses assignment instructions.
Extract assignment details from the teacher's natural language instruction.

Return JSON:
{
  "title": "short title (5-10 words)",
  "description": "full assignment description for the student",
  "student_name": "student name or null if not specified",
  "deadline_days": integer (days from now, default 3 if not specified),
  "deadline_description": "human-readable deadline description"
}

If the teacher says "due in 3 days", deadline_days=3.
If they say "due tomorrow", deadline_days=1.
If they say "due Friday" or a specific date, estimate days from today.
"""

SUMMARY_SYSTEM = """You are a teacher assistant that produces concise student status summaries.
Given a student's assignment and progress notes, write a 2-3 sentence summary
that tells the teacher how the student is doing. Be factual, warm, and actionable."""

FEEDBACK_PROMPT_SYSTEM = """You are a teacher assistant. The teacher has received a student submission.
Acknowledge the submission warmly and ask the teacher for their feedback in natural language.
Keep it brief (2-3 sentences)."""

FEEDBACK_PARSE_SYSTEM = """You are a teacher assistant. The teacher wrote feedback for a student.
Rewrite it in an encouraging, constructive tone suitable for a student. Preserve all the content.
Keep it concise (3-5 sentences max)."""


def parse_assignment(instruction: str, today: datetime = None) -> dict:
    """Parse teacher's natural language assignment into structured data."""
    today = today or datetime.utcnow()
    result = call_llm_json(
        PARSE_SYSTEM,
        f"Today is {today.strftime('%A, %B %d %Y')}.\nTeacher instruction: {instruction}"
    )
    days = int(result.get("deadline_days", 3))
    result["deadline"] = today + timedelta(days=days)
    return result


def generate_status_summary(student_name: str, assignment_title: str,
                              deadline: datetime, status: str, progress_notes: str) -> str:
    """Generate a status summary for the teacher."""
    days_left = (deadline - datetime.utcnow()).days
    context = f"""Student: {student_name}
Assignment: {assignment_title}
Deadline: {deadline.strftime('%B %d, %Y')} ({days_left} days {'remaining' if days_left >= 0 else 'overdue'})
Status: {status}
Progress notes: {progress_notes or 'No updates yet'}"""
    return call_llm(SUMMARY_SYSTEM, context)


def prompt_for_feedback(student_name: str, assignment_title: str, submission_text: str) -> str:
    """Ask teacher to provide feedback."""
    context = f"""Student {student_name} submitted: {assignment_title}
Submission: {submission_text[:500] if submission_text else '(file/photo submitted)'}"""
    return call_llm(FEEDBACK_PROMPT_SYSTEM, context)


def reformat_feedback(raw_feedback: str, student_name: str) -> str:
    """Reformat teacher's raw feedback for student consumption."""
    return call_llm(
        FEEDBACK_PARSE_SYSTEM,
        f"Student name: {student_name}\nTeacher feedback: {raw_feedback}"
    )


def answer_student_query(teacher_name: str, student_name: str,
                          assignment_title: str, progress_notes: str, query: str) -> str:
    """Answer teacher's query about a specific student."""
    system = "You are a classroom assistant. Answer the teacher's question about a student concisely and helpfully."
    context = f"""Teacher: {teacher_name}
Student: {student_name}
Assignment: {assignment_title}
Progress notes: {progress_notes or 'No updates'}
Teacher question: {query}"""
    return call_llm(system, context)
