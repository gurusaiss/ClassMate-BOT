# 🎓 ClassMate — AI-Powered Classroom Companion

> **Super Intelli Machines — Engineering Intern Assessment**  
> A production-quality, multi-agent Telegram bot for classroom assignment management.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue)](https://core.telegram.org/bots)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![LLM](https://img.shields.io/badge/LLM-Groq%20%7C%20Anthropic%20%7C%20OpenAI-orange)](https://groq.com)

---

## 📋 Table of Contents
- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Agent Design](#agent-design)
- [Prompt Strategy](#prompt-strategy)
- [Setup & Run](#setup--run)
- [Web UI](#web-ui)
- [Live Demo Flow](#live-demo-flow)
- [Deliverables Checklist](#deliverables-checklist)
- [Known Limitations](#known-limitations)
- [What I'd Build Next](#what-id-build-next)

---

## What It Does

ClassMate is an **AI-agent-powered Telegram bot** that mediates between Teachers and Students for assignment management.

### Teacher can:
- Register and get a shareable invite link/code for students
- Assign work in **natural language** — just describe it: *"Assign Riya a 500-word essay on photosynthesis, due in 3 days"*
- Send a **PDF/file with a caption** — the file becomes assignment material, forwarded to the student
- Receive **proactive daily status summaries** of the whole class
- Ask **"How is Riya doing?"** and get an LLM-generated per-student summary
- Give feedback in natural language — bot reformats it for the student
- See all students, assignments, statuses on the **Teacher Web Dashboard**

### Student can:
- Join via teacher's invite link (one click — no setup)
- Receive assignment with deadline from the bot
- Get **smart escalating reminders** (daily → every 12h → every 6h → every 4h near deadline)
- Report progress in natural language: *"done 2 paragraphs"*, *"stuck on the intro"*
- Submit work as **text, photo, PDF, audio, video, or voice note**
- Receive teacher's feedback conversationally
- See all assignments, deadlines, and feedback on the **Student Web Dashboard**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          TRANSPORT LAYER                                │
│                                                                         │
│   Telegram Bot (python-telegram-bot v21)    FastAPI Web Server          │
│   bot/handlers.py  ─────────────────────   api/routes.py               │
└────────────────────────────┬────────────────────────┬───────────────────┘
                             │                        │
                             ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          AGENT LAYER  (agents/)                         │
│                                                                         │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────┐               │
│  │ Intent Agent │  │ Teacher Agent │  │  Student Agent │               │
│  │              │  │               │  │                │               │
│  │ Classifies   │  │ • Parse NL    │  │ • Detect done  │               │
│  │ every        │  │   assignment  │  │ • Ack progress │               │
│  │ message →    │  │ • Status      │  │ • Deliver      │               │
│  │ assign/      │  │   summary     │  │   feedback     │               │
│  │ progress/    │  │ • Student     │  │ • Welcome msg  │               │
│  │ completion/  │  │   query reply │  │ • Assignment   │               │
│  │ feedback/    │  │ • Reformat    │  │   notification │               │
│  │ status_query │  │   feedback    │  └────────────────┘               │
│  └──────────────┘  └───────────────┘                                   │
│                                                                         │
│  ┌────────────────────────┐   ┌────────────────────────────────────┐   │
│  │   Reminder Agent       │   │        Summariser Agent            │   │
│  │                        │   │                                    │   │
│  │ • Decides WHEN to send │   │ • Class-wide status report         │   │
│  │ • Escalates frequency  │   │ • Completion notification          │   │
│  │   as deadline nears    │   │ • Daily morning summary            │   │
│  └────────────────────────┘   └────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    LLM Wrapper  (agents/llm.py)                 │   │
│  │  Provider-agnostic: Groq (free) │ Anthropic │ OpenAI │ Gemini   │   │
│  │  Switch with 1 env var: LLM_PROVIDER=groq                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER  (db/)                             │
│  SQLAlchemy ORM + SQLite (swap → Postgres via DATABASE_URL env var)     │
│  Tables: teachers · students · assignments · submissions                │
│  Schema survives restarts. File attachments stored as Telegram file_id. │
└─────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SCHEDULER  (scheduler/)                            │
│  APScheduler AsyncIOScheduler                                           │
│  • Every 30 min: check all active submissions → send reminders          │
│  • 9 AM UTC daily: send class summary to all teachers                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Design

| Agent | Responsibility | Key LLM Task |
|---|---|---|
| **Intent Agent** | Routes every message to the right handler | Classifies: `assign` / `progress` / `completion` / `feedback` / `status_query` / `student_query` / `other` |
| **Teacher Agent** | Handles all teacher-side logic | Parses NL assignment → structured data; generates status summaries; reformats feedback |
| **Student Agent** | Handles all student-side logic | Detects completion signals; acknowledges progress; generates assignment/feedback messages |
| **Reminder Agent** | Decides when and how to remind | Generates personalised reminders with tone escalating by urgency |
| **Summariser Agent** | Produces class-wide updates | Generates daily class summaries and completion notifications |

**Agent separation:** All agents live in `agents/`. Bot handlers (`bot/handlers.py`) only do Telegram I/O and call agents. Web routes (`api/routes.py`) only do HTTP I/O and call DB/agents. Zero business logic in transport layers.

---

## Prompt Strategy

### Intent Classification
```
One-shot JSON prompt with 7 intent categories.
Temperature: 0.1 (high precision).
Keyword fallback: if LLM returns "other" but text contains
assignment-related keywords (assign, deadline, essay, task, etc.),
override to "assign". Never crashes — all LLM calls wrapped in try/except.
```

### Assignment Parsing
```
Extracts: title, description, student_name, deadline_days, deadline_description.
Includes today's date in prompt for relative deadline calculation.
Temperature: 0.1. Falls back to raw text as description if LLM fails.
```

### Reminder Generation
```
Injects days_left into prompt → tone changes automatically:
- >3 days: gentle, encouraging
- 2-3 days: friendly, deadline-specific
- 1 day: urgent but kind
- Overdue: empathetic but firm
Never spammy: frequency gated by last_reminded_at timestamp.
```

### Feedback Reformatting
```
Teacher's raw feedback → student-appropriate tone.
Content preserved, phrasing improved.
Student never sees a cold or harsh message.
```

### Progress Acknowledgement
```
Low temperature (0.3). Warm but brief.
Avoids sycophancy — not "Amazing job!" for every message.
```

---

## Setup & Run

### Prerequisites
- Python 3.11+
- Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Installation

```bash
# 1. Clone
git clone https://github.com/gurusaiss/ClassMate-BOT.git
cd ClassMate-BOT

# 2. Virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — fill in TELEGRAM_BOT_TOKEN and GROQ_API_KEY
```

### Environment Variables

```env
# Required
TELEGRAM_BOT_TOKEN=your_token_here

# LLM — Groq is FREE
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant

# Optional — switch to paid providers
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# Database (SQLite by default; swap for Postgres)
DATABASE_URL=sqlite:///./classroom.db

# Web server
WEB_HOST=0.0.0.0
WEB_PORT=8000
```

### Run

```bash
python main.py
```

This starts **both** simultaneously:
- Telegram bot (polling mode)
- Web UI at `http://localhost:8000`

### Run Tests

```bash
pytest tests/ -v
```

### Docker

```bash
docker build -t classmate .
docker run -p 8000:8000 --env-file .env classmate
```

---

## Web UI

| URL | Who | What |
|---|---|---|
| `http://localhost:8000/` | Anyone | Overview: stats, teacher list, student list, chart |
| `http://localhost:8000/teacher` | Teacher | All teachers with invite codes |
| `http://localhost:8000/teacher/{id}` | Teacher | Dashboard: analytics, filters, assignment table, chat threads, inline feedback |
| `http://localhost:8000/students` | Anyone | All students with filter/search |
| `http://localhost:8000/student/{telegram_id}` | Student | My assignments, chat thread, download files, see feedback |
| `http://localhost:8000/api/file/{file_id}` | Anyone | Download/view any Telegram file in browser |

### Features
- **Live Chat Threads** — WhatsApp/Telegram-style bubbles per assignment: assignment → progress updates → submission → feedback. Avatar initials, message tails, timestamps.
- **Inline Feedback** — Teacher clicks "Give Feedback" on dashboard → modal opens → feedback sent to student via Telegram automatically
- **File Download** — All submitted files and assignment PDFs have Download + View buttons
- **Analytics** — Donut chart with completion rate, stat cards for all statuses
- **Filters** — Filter assignments by status (pending/in_progress/completed/overdue) and search by student name
- **Auto-refresh** — Dashboards refresh every 30 seconds for live state

---

## Live Demo Flow

```
1. Teacher: /start → "I'm a Teacher" → registered, gets invite link
2. Student 1 & 2: click invite link → linked to teacher

3. Teacher types: "Assign saiSS a 500-word essay on photosynthesis, due in 3 days"
   → Bot parses NL → creates assignment → student receives notification

4. Teacher sends PDF + caption: "Assign saiSS this assignment, due in 2 days"
   → PDF stored as material → forwarded to student automatically

5. Student: "done the introduction paragraph"
   → Bot acknowledges → teacher receives progress summary

6. Bot sends reminder at deadline - 1 day (escalated urgency)

7. Student: "completed"
   → Bot asks for submission → student sends text/photo/file
   → Teacher notified with "Give Feedback" button

8. Teacher clicks "Give Feedback" on web dashboard → types feedback
   → Student receives it conversationally on Telegram

9. Teacher asks: "How is saiSS doing?"
   → Bot returns LLM-generated per-student summary

10. Web UI shows full chat thread, deadline bar, all file attachments
```

---

## Deliverables Checklist

| # | Deliverable | Status | Notes |
|---|---|---|---|
| 1 | Telegram Bot | ✅ Complete | Works e2e with 1 teacher + 2 students |
| 2 | Teacher Web UI | ✅ Complete | Dashboard with analytics, filters, inline feedback, chat threads |
| 3 | Student Web UI | ✅ Complete | Assignments, deadlines, chat thread, file downloads |
| 4 | Persistent Storage | ✅ Complete | SQLite via SQLAlchemy; schema survives restarts |
| 5 | Agent Orchestration | ✅ Complete | 5 agents in `agents/`, cleanly separated from transport and UI |
| 6 | README | ✅ Complete | This file |
| 7 | Live Demo Ready | ✅ Complete | Full flow documented above |

### Bonus Deliverables

| Bonus | Status |
|---|---|
| File/photo submissions | ✅ Photo, PDF, audio, video, voice note, video note |
| Teacher student query ("How is Riya doing?") | ✅ LLM-generated per-student summary |
| Tests (unit + agent-eval) | ✅ `tests/test_intent_agent.py` — 10 tests |
| Deployment config | ✅ `Dockerfile` + `render.yaml` |
| Full multi-agent implementation | ✅ 5 cooperating agents with separate orchestration |

---

## Known Limitations

1. **Telegram polling** (not webhook) — works fine for demo; swap to webhook for production scale
2. **Sync LLM calls** — agent calls block the event loop; for production, wrap in `asyncio.to_thread`
3. **No auth on Web UI** — magic link / shared URL approach (explicitly out of scope per spec)
4. **Single active assignment** per student per message — multi-assignment selection uses inline buttons
5. **SQLite** for demo — swap `DATABASE_URL` to Postgres for production

---

## What I'd Build Next

1. **Webhook mode** — replace polling with webhook for production (Render/Railway/Fly.io)
2. **Voice note transcription** — integrate Whisper API to transcribe student voice submissions
3. **Assignment rubric parsing** — extract marking criteria from uploaded PDFs using LLM
4. **Parent notifications** — extend bot to notify parents on submission/feedback
5. **Async LLM calls** — `asyncio.to_thread` for all agent calls to avoid blocking
6. **Multi-tenant** — proper teacher-student isolation for school-wide deployment

## What I'd Refactor

1. Extract a central `orchestrator.py` — instead of handlers calling agents directly, route through a single orchestrator with state machine
2. Add Pydantic models for all agent inputs/outputs — currently using plain dicts
3. Replace `context.user_data` for pending state with Redis for multi-instance support

## Where AI Helped vs. Hurt

**Helped:**
- Prompt design iteration — rapidly tested and refined intent classification prompts
- Jinja2 template structure — generated solid starting points for complex templates
- SQLAlchemy relationship setup — suggested the `back_populates` pattern correctly

**Hurt / Required Human Correction:**
- Initial reminder logic was too aggressive (AI suggested hourly reminders for all deadlines) — manually designed the tiered escalation policy
- Agent separation — AI wanted to put business logic in handlers; enforced the separation manually
- File proxy endpoint — AI initially suggested serving files directly from disk; redirecting to Telegram CDN is better

---

## Project Structure

```
ClassMate-BOT/
├── agents/                    # Agent orchestration (pure business logic)
│   ├── llm.py                 # Provider-agnostic LLM wrapper
│   ├── intent_agent.py        # Intent classification
│   ├── teacher_agent.py       # Teacher conversation logic
│   ├── student_agent.py       # Student conversation logic
│   ├── reminder_agent.py      # Reminder scheduling decisions
│   └── summariser_agent.py    # Status summary generation
├── bot/                       # Telegram transport layer only
│   ├── handlers.py            # Message handlers → delegates to agents
│   └── bot_instance.py        # Singleton for web↔bot communication
├── api/                       # Web UI + REST API
│   ├── routes.py              # FastAPI routes
│   └── templates/             # Jinja2 HTML templates
│       ├── base.html          # Base layout + CSS
│       ├── home.html          # Overview dashboard
│       ├── teacher_list.html  # All teachers
│       ├── teacher_dashboard.html  # Teacher detail view
│       ├── student_list.html  # All students
│       └── student_dashboard.html  # Student detail view
├── db/                        # Database layer
│   ├── models.py              # SQLAlchemy models
│   └── crud.py                # CRUD operations
├── scheduler/                 # Background jobs
│   └── reminders.py           # APScheduler reminder + summary jobs
├── tests/                     # Unit tests
│   └── test_intent_agent.py   # Intent + reminder agent tests
├── main.py                    # Entry point (bot + web server)
├── config.py                  # Environment config
├── requirements.txt           # Dependencies
├── Dockerfile                 # Container deployment
├── render.yaml                # Render.com deployment
└── .env.example               # Environment template
```

---

*Built by [@gurusaiss](https://github.com/gurusaiss) for Super Intelli Machines Engineering Intern Assessment.*
