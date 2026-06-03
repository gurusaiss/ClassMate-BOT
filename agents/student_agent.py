"""
Student Agent
Handles: acknowledging progress updates, parsing completion signals, forwarding submissions.
"""
from datetime import datetime
from .llm import call_llm, call_llm_json

ACKNOWLEDGE_SYSTEM = """You are a friendly classroom assistant talking to a student.
Acknowledge their progress update warmly and encouragingly.
Keep it short (1-2 sentences). Don't be overly effusive."""

COMPLETION_PARSE_SYSTEM = """Determine if the student's message means they have COMPLETED their assignment.
Words like "done", "finished", "completed", "submitted", "ready" strongly indicate completion.
Return JSON: {"is_complete": true/false, "confidence": 0.0-1.0}"""

WELCOME_SYSTEM = """You are a friendly classroom assistant.
Welcome a new student warmly and let them know they've been linked to their teacher.
Include: their teacher's name, that they'll receive assignment details soon, and that they can
report progress at any time. Keep it to 3-4 sentences."""

ASSIGNMENT_NOTIFY_SYSTEM = """You are a friendly classroom assistant delivering an assignment to a student.
Write an engaging, clear message that includes: the assignment title, full description,
and deadline. Encourage them and tell them they can send progress updates anytime.
Do not add extra information. Tone: warm, clear, motivating."""

FEEDBACK_DELIVERY_SYSTEM = """You are a classroom assistant delivering teacher feedback to a student.
Present the feedback conversationally and encouragingly. If the feedback is positive, celebrate it.
If it has suggestions, frame them constructively."""


def check_if_complete(message: str) -> dict:
    """Returns {'is_complete': bool, 'confidence': float}"""
    return call_llm_json(COMPLETION_PARSE_SYSTEM, f"Student message: {message}")


def acknowledge_progress(student_name: str, progress_message: str,
                          assignment_title: str) -> str:
    """Generate acknowledgement for progress update."""
    context = f"Student: {student_name}\nAssignment: {assignment_title}\nUpdate: {progress_message}"
    return call_llm(ACKNOWLEDGE_SYSTEM, context)


def generate_welcome_message(student_name: str, teacher_name: str) -> str:
    context = f"Student name: {student_name}\nTeacher name: {teacher_name}"
    return call_llm(WELCOME_SYSTEM, context)


def generate_assignment_message(student_name: str, title: str, description: str,
                                 deadline: datetime) -> str:
    days_left = (deadline - datetime.utcnow()).days
    context = f"""Student: {student_name}
Assignment title: {title}
Description: {description}
Deadline: {deadline.strftime('%A, %B %d %Y')} ({days_left} days from now)"""
    return call_llm(ASSIGNMENT_NOTIFY_SYSTEM, context)


def deliver_feedback(student_name: str, assignment_title: str, feedback: str) -> str:
    context = f"Student: {student_name}\nAssignment: {assignment_title}\nFeedback: {feedback}"
    return call_llm(FEEDBACK_DELIVERY_SYSTEM, context)


def request_submission(student_name: str, assignment_title: str) -> str:
    """Ask student to submit their work."""
    system = "You are a classroom assistant. Ask the student to submit their work for the assignment. They can send text, a photo, or a file. Keep it friendly and brief (2 sentences)."
    return call_llm(system, f"Student: {student_name}, Assignment: {assignment_title}")
