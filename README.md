# 🎓 Classroom Companion — Telegram Bot

An AI-agent-powered Telegram bot that mediates between **Teachers** and **Students** for assignment management.

Built for the Super Intelli Machines Engineering Intern Assessment.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        TRANSPORT LAYER                        │
│  Telegram Bot (python-telegram-bot)  │  FastAPI Web Server   │
└────────────────────┬─────────────────┴───────────┬───────────┘
                     │                             │
┌────────────────────▼─────────────────────────────▼───────────┐
│                       AGENT LAYER (agents/)                   │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │Intent Agent │  │Teacher Agent │  │  Student Agent    │    │
│  │(classifies  │  │(parse assign,│  │(ack progress,     │    │
│  │ messages)   │  │ summarise,   │  │ detect completion,│    │
│  └─────────────┘  │ feedback)    │  │ deliver feedback) │    │
│                   └──────────────┘  └───────────────────┘    │
│  ┌──────────────────────┐  ┌──────────────────────────────┐  │
│  │  Reminder Agent      │  │    Summariser Agent          │  │
│  │(decides when/how to  │  │(generates class & completion │  │
│  │ send reminders,      │  │ status summaries for teacher)│  │
│  │ escalates near ddl)  │  └──────────────────────────────┘  │
│  └──────────────────────┘                                     │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              LLM Wrapper (agents/llm.py)                │  │
│  │  Provider-agnostic: Anthropic │ OpenAI │ Gemini         │  │
│  │  Switch via LLM_PROVIDER in .env — no code changes      │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│                    STORAGE LAYER (db/)                        │
│  SQLAlchemy ORM + SQLite (swap to Postgres via DATABASE_URL)  │
│  Tables: teachers, students, assignments, submissions         │
└──────────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│                   SCHEDULER (scheduler/)                      │
│  APScheduler — reminder check every 30 min, daily summary 9AM│
└──────────────────────────────────────────────────────────────┘
```

## Agent Design

| Agent | Role |
|---|---|
| **Intent Agent** | Classifies incoming messages: `assign`, `progress`, `completion`, `feedback`, `status_query`, `other` |
| **Teacher Agent** | Parses assignment NL instructions, generates status summaries, prompts/reformats feedback |
| **Student Agent** | Detects completion signals, acknowledges progress, generates assignment notifications |
| **Reminder Agent** | Decides whether to send a reminder based on deadline proximity + last-reminded time. Escalates frequency near deadline |
| **Summariser Agent** | Produces class-wide status summaries and completion notifications for teachers |

## Prompt Strategy

- **Intent classification**: One-shot JSON prompt with 6 intent categories. Temperature 0.1 for reliability.
- **Assignment parsing**: Extracts title, description, student name, deadline from free-form text. Temperature 0.1.
- **Reminder generation**: Tone varies with days-left context injected into the prompt (gentle → urgent → empathetic).
- **Progress acknowledgement**: Low temperature, warm but brief — avoids sycophancy.
- **Feedback reformatting**: Teacher's raw feedback rewritten to be student-appropriate without losing content.
- All prompts include explicit persona and output constraints. No prompt reveals system internals.

## Folder Structure

```
classroom-companion/
├── agents/
│   ├── llm.py               # Provider-agnostic LLM wrapper
│   ├── intent_agent.py      # Intent/routing agent
│   ├── teacher_agent.py     # Teacher conversation agent
│   ├── student_agent.py     # Student conversation agent
│   ├── reminder_agent.py    # Reminder logic + scheduling decisions
│   └── summariser_agent.py  # Status summary generation
├── bot/
│   └── handlers.py          # Telegram handlers (transport only)
├── api/
│   ├── routes.py            # FastAPI routes + web UI
│   └── templates/           # Jinja2 HTML templates
├── db/
│   ├── models.py            # SQLAlchemy models
│   └── crud.py              # CRUD operations
├── scheduler/
│   └── reminders.py         # APScheduler jobs
├── main.py                  # Entry point
├── config.py                # Config from env vars
├── requirements.txt
└── .env.example
```

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd classroom-companion
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your Telegram bot token and LLM API key
```

Get a Telegram bot token from [@BotFather](https://t.me/BotFather).

### 3. Run

```bash
python main.py
```

This starts:
- The Telegram bot (polling)
- Web UI at `http://localhost:8000`

### 4. Web UI

| URL | Who |
|---|---|
| `http://localhost:8000/` | Home — lists all teachers and students |
| `http://localhost:8000/teacher/<id>` | Teacher dashboard — all students, assignments, statuses, feedback |
| `http://localhost:8000/student/<telegram_id>` | Student dashboard — assignments, deadlines, progress, feedback |

## Switching LLM Provider

Edit `.env`:

```env
# Use Anthropic (default)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Or OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Or Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
```

No code changes needed. The `agents/llm.py` wrapper handles routing.

## Demo Flow

```
Teacher: /start → registers → gets invite link
Student: clicks invite link → linked to teacher
Teacher: "Assign Riya a 500-word essay on photosynthesis, due in 3 days"
  → Bot parses, creates assignment, notifies student
Student: receives assignment with deadline
Student: "done the intro paragraph" → progress update
  → Bot acknowledges, teacher receives summary
Student: "completed" → bot asks for submission
Student: sends text/photo/file
  → teacher notified, prompted for feedback
Teacher: types feedback
  → student receives formatted feedback
Web UI: reflects all state live (auto-refreshes every 30s)
```

## Known Limitations

- No production auth on web UI (by design per spec — share/magic link approach)
- Telegram polling (not webhook) — fine for demo, swap to webhook for production
- Single-assignment-at-a-time UX for students: uses most recent active assignment for context
- LLM calls are synchronous (blocking) — for production, wrap in `asyncio.to_thread`

## What I'd Build Next

- Webhook mode + deployment on Railway/Render
- Multi-assignment selection UI in Telegram (inline buttons)
- Voice note transcription via Whisper API
- Teacher can query: "How is Riya doing?" → LLM-generated per-student summary
- Async LLM calls to avoid blocking the event loop under load

## AI Collaboration Notes

Used Claude (claude-sonnet-4-6) for:
- Agent prompt design and iteration
- Jinja2 template structure
- SQLAlchemy model relationships
- Reminder escalation logic

Human-written and reviewed: all agent prompt strategies, data model, system architecture, reminder scheduling policy.
