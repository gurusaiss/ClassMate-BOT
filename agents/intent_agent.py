"""
Intent / Routing Agent
Classifies incoming messages: assignment | progress | completion | feedback | question | other
"""
from .llm import call_llm_json

SYSTEM = """You are an intent classifier for a classroom management bot.
Classify the user message into one of these intents:
- "assign": teacher wants to assign work to a student
- "progress": student reporting progress (e.g. "done 2 paragraphs", "stuck on intro")
- "completion": student marking work as done/completed/finished
- "feedback": teacher providing feedback on submitted work
- "status_query": teacher asking about ALL students' general status
- "student_query": teacher asking about a SPECIFIC student ("how is Riya doing?", "what has John submitted?")
- "other": anything else (greetings, unclear, unrelated)

Return JSON: {"intent": "<intent>", "confidence": 0.0-1.0}"""


def classify_intent(message: str) -> dict:
    """Returns {'intent': str, 'confidence': float}"""
    return call_llm_json(SYSTEM, f"Message: {message}")
