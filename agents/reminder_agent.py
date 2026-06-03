"""
Reminder / Scheduler Agent
Decides WHEN and HOW to nudge a student. Reminders escalate near the deadline.
"""
from datetime import datetime, timedelta
from .llm import call_llm

REMINDER_SYSTEM = """You are a classroom assistant sending a reminder to a student about their assignment.
Write a friendly, personalised reminder. The tone should escalate based on urgency:
- More than 3 days left: gentle, encouraging
- 2-3 days left: friendly but more specific about deadline
- 1 day left: urgent but kind, emphasise deadline is tomorrow
- Past deadline: empathetic but firm, ask them to submit ASAP

Include the assignment title and deadline. Keep it to 2-3 sentences max.
Do not sound robotic or spammy."""


def should_send_reminder(submission) -> bool:
    """Determine if a reminder should be sent now."""
    if submission.status == "completed":
        return False

    deadline = submission.assignment.deadline
    now = datetime.utcnow()
    days_left = (deadline - now).days
    last_reminded = submission.last_reminded_at
    count = submission.reminder_count or 0

    # Never reminded — send first reminder
    if last_reminded is None:
        return True

    hours_since = (now - last_reminded).total_seconds() / 3600

    if days_left > 3:
        # Once per day is enough
        return hours_since >= 24
    elif days_left == 2 or days_left == 3:
        # Every 12 hours
        return hours_since >= 12
    elif days_left == 1:
        # Every 6 hours
        return hours_since >= 6
    else:
        # Overdue: every 4 hours, max 5 reminders after due
        return hours_since >= 4 and count < (5 + abs(days_left))


def generate_reminder(student_name: str, assignment_title: str,
                       deadline: datetime, reminder_count: int) -> str:
    days_left = (deadline - datetime.utcnow()).days
    context = f"""Student: {student_name}
Assignment: {assignment_title}
Deadline: {deadline.strftime('%A, %B %d %Y')}
Days remaining: {days_left if days_left >= 0 else f'{abs(days_left)} days OVERDUE'}
This is reminder #{reminder_count + 1}"""
    return call_llm(REMINDER_SYSTEM, context)
