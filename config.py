import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# LLM provider abstraction — swap by changing LLM_PROVIDER
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # "groq" (free) | "anthropic" | "openai" | "gemini"

# Groq (FREE — recommended)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# Other providers (paid)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./classroom.db")

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# Reminder intervals (hours)
REMINDER_DAILY_HOUR = int(os.getenv("REMINDER_DAILY_HOUR", "9"))  # 9 AM
REMINDER_ESCALATE_DAYS = int(os.getenv("REMINDER_ESCALATE_DAYS", "2"))  # escalate within 2 days of deadline
