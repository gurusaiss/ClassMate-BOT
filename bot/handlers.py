"""
Telegram bot handlers.
Transport layer only — all business logic goes through agents/*.
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ConversationHandler,
)
from db.models import SessionLocal
from db import crud
from agents import intent_agent, teacher_agent, student_agent, summariser_agent

logger = logging.getLogger(__name__)

# Conversation states
AWAITING_FEEDBACK = 1
AWAITING_SUBMISSION = 2

# In-memory state for pending feedback requests: {teacher_telegram_id: submission_id}
pending_feedback: dict[str, int] = {}
# Pending submission collection: {student_telegram_id: assignment_id}
pending_submission: dict[str, int] = {}


def _db():
    db = SessionLocal()
    return db


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user = update.effective_user
    telegram_id = str(user.id)

    db = _db()
    try:
        # If called with /start <invite_code>  → student joining
        if args:
            invite_code = args[0]
            teacher_for_code = crud.get_teacher_by_invite_code(db, invite_code)
            if not teacher_for_code:
                await update.message.reply_text("❌ Invalid invite code. Ask your teacher for a valid link.")
                return

            # BUG FIX: Block teachers from joining as their own student
            already_teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
            if already_teacher:
                await update.message.reply_text(
                    f"⚠️ You are already registered as a *teacher*, {already_teacher.name}.\n"
                    "Teachers cannot join as students.",
                    parse_mode="Markdown"
                )
                return

            existing = crud.get_student_by_telegram_id(db, telegram_id)
            if existing:
                await update.message.reply_text(
                    f"You're already linked to teacher {existing.teacher.name}. "
                    "Use the bot to report your progress."
                )
                return

            student = crud.create_student(
                db, telegram_id=telegram_id,
                name=user.full_name, username=user.username or "",
                teacher=teacher_for_code,
            )
            welcome = student_agent.generate_welcome_message(student.name, teacher_for_code.name)
            await update.message.reply_text(welcome)
            return

        # Check if already registered
        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        student = crud.get_student_by_telegram_id(db, telegram_id)

        if teacher:
            await update.message.reply_text(
                f"Welcome back, {teacher.name}! 👋\n\n"
                f"Your invite code: `{teacher.invite_code}`\n"
                f"Invite link: https://t.me/{context.bot.username}?start={teacher.invite_code}\n\n"
                "Commands:\n"
                "/assign — assign work to a student\n"
                "/status — get class status\n"
                "/students — list your students\n"
                "/invite — get your invite link",
                parse_mode="Markdown"
            )
        elif student:
            assignments = crud.get_assignments_for_student(db, telegram_id)
            active = [a for a in assignments if a.submission and a.submission.status != "completed"]
            await update.message.reply_text(
                f"Welcome back, {student.name}! 👋\n"
                f"You have {len(active)} active assignment(s).\n"
                "Just send me a message to update your progress!"
            )
        else:
            await update.message.reply_text(
                "👋 Welcome to Classroom Companion!\n\n"
                "Are you a *teacher* or a *student*?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("I'm a Teacher", callback_data="register_teacher")],
                    [InlineKeyboardButton("I'm a Student (I have an invite code)", callback_data="student_no_code")],
                ])
            )
    finally:
        db.close()


# ── Registration callbacks ────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    telegram_id = str(user.id)

    db = _db()
    try:
        if data == "register_teacher":
            existing = crud.get_teacher_by_telegram_id(db, telegram_id)
            if existing:
                await query.edit_message_text(f"You're already registered as a teacher, {existing.name}.")
                return
            teacher = crud.create_teacher(db, telegram_id, user.full_name, user.username or "")
            invite_link = f"https://t.me/{context.bot.username}?start={teacher.invite_code}"
            await query.edit_message_text(
                f"✅ Registered as teacher: *{teacher.name}*\n\n"
                f"Share this invite link with your students:\n`{invite_link}`\n\n"
                f"Or give them code: `{teacher.invite_code}`\n\n"
                "To assign work, just type:\n"
                "_Assign [student name] a [task], due in [X] days_",
                parse_mode="Markdown"
            )

        elif data == "student_no_code":
            await query.edit_message_text(
                "Ask your teacher for an invite link or code, then click the link or use:\n"
                "`/start <code>`",
                parse_mode="Markdown"
            )

        elif data.startswith("feedback_yes:"):
            submission_id = int(data.split(":")[1])
            pending_feedback[telegram_id] = submission_id
            await query.edit_message_text(
                "Please type your feedback for the student. Be as detailed as you like!"
            )

        elif data.startswith("feedback_no:"):
            await query.edit_message_text("No problem! You can send feedback later anytime.")

        elif data.startswith("submit_text:"):
            assignment_id = int(data.split(":")[1])
            pending_submission[telegram_id] = assignment_id
            await query.edit_message_text(
                "Please type your submission or send a photo/file now."
            )
    finally:
        db.close()


# ── /invite ───────────────────────────────────────────────────────────────────

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = _db()
    try:
        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        if not teacher:
            await update.message.reply_text("Only teachers have invite links. Use /start to register.")
            return
        link = f"https://t.me/{context.bot.username}?start={teacher.invite_code}"
        await update.message.reply_text(
            f"Your invite link:\n`{link}`\n\nCode: `{teacher.invite_code}`",
            parse_mode="Markdown"
        )
    finally:
        db.close()


# ── /students ─────────────────────────────────────────────────────────────────

async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = _db()
    try:
        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        if not teacher:
            await update.message.reply_text("Only teachers can use this command.")
            return
        students = crud.get_students_by_teacher(db, teacher.id)
        if not students:
            await update.message.reply_text("No students yet. Share your invite link to add students.")
            return
        lines = [f"👥 Your students ({len(students)}):"]
        for s in students:
            assignments = crud.get_assignments_for_student(db, s.telegram_id)
            active = sum(1 for a in assignments if a.submission and a.submission.status != "completed")
            lines.append(f"• {s.name} (@{s.username}) — {active} active assignment(s)")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


# ── /assign ───────────────────────────────────────────────────────────────────

async def assign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Tell me the assignment in natural language, e.g.:\n"
        "_Assign Riya a 500-word essay on photosynthesis, due in 3 days_",
        parse_mode="Markdown"
    )


# ── /status ───────────────────────────────────────────────────────────────────

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = _db()
    try:
        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        if not teacher:
            await update.message.reply_text("Only teachers can use this command.")
            return
        students = crud.get_students_by_teacher(db, teacher.id)
        if not students:
            await update.message.reply_text("No students yet.")
            return

        from datetime import datetime
        students_data = []
        for s in students:
            assignments = crud.get_assignments_for_student(db, s.telegram_id)
            for a in assignments:
                sub = a.submission
                if sub:
                    days_left = (a.deadline - datetime.utcnow()).days
                    students_data.append({
                        "name": s.name,
                        "assignment_title": a.title,
                        "status": sub.status,
                        "days_left": days_left,
                        "progress_notes": sub.progress_notes,
                    })

        await _send_teacher_status(update, db, teacher)
    finally:
        db.close()


# ── Main message handler ──────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)
    text = update.message.text or ""

    db = _db()
    try:
        # Check if teacher is in feedback-collection mode
        if telegram_id in pending_feedback:
            await _handle_teacher_feedback(update, context, db, telegram_id, text)
            return

        # Check if student is in submission-collection mode
        if telegram_id in pending_submission:
            await _handle_student_submission(update, context, db, telegram_id, text)
            return

        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        if teacher:
            await _handle_teacher_message(update, context, db, teacher, text)  # no file
            return

        student = crud.get_student_by_telegram_id(db, telegram_id)
        if student:
            await _handle_student_message(update, context, db, student, text)
            return

        await update.message.reply_text(
            "Please use /start to register first."
        )
    finally:
        db.close()


_ASSIGN_KEYWORDS = {
    "assign", "assignment", "task", "essay", "homework", "project", "due", "submit",
    "write", "complete", "finish", "prepare", "create", "make", "research",
    "deadline", "internship", "report", "presentation", "exercise", "work",
    "activity", "quiz", "test", "exam", "study", "read", "chapter", "question",
    "solve", "answer", "review", "practise", "practice", "draft", "submit",
}


def _looks_like_assignment(text: str) -> bool:
    """Fallback keyword check in case LLM misclassifies."""
    words = set(text.lower().replace(",", " ").replace(".", " ").split())
    return bool(words & _ASSIGN_KEYWORDS)


async def _handle_teacher_message(update, context, db, teacher, text,
                                   material_file_id="", material_file_type="", material_file_name=""):
    # ── Step 1: classify intent (with fallback if LLM fails) ──────────────────
    try:
        intent = intent_agent.classify_intent(text)
        intent_type = intent.get("intent", "other")
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}")
        intent_type = "other"

    # ── Step 2: keyword fallback — catches any assignment-flavoured message ────
    if intent_type == "other" and _looks_like_assignment(text):
        intent_type = "assign"

    # ── Step 3: route ──────────────────────────────────────────────────────────
    if intent_type == "assign":
        students = crud.get_students_by_teacher(db, teacher.id)
        if not students:
            await update.message.reply_text(
                "⚠️ You have no students yet. Share your invite link first:\n"
                "Use /invite to get your link.",
            )
            return

        # Parse the assignment — fallback gracefully if LLM fails
        try:
            parsed = teacher_agent.parse_assignment(text)
        except Exception as e:
            logger.warning(f"Assignment parsing failed: {e}")
            # Minimal fallback: use raw text as description, 3-day deadline
            from datetime import datetime, timedelta
            parsed = {
                "title": text[:60] + ("…" if len(text) > 60 else ""),
                "description": text,
                "student_name": None,
                "deadline": datetime.utcnow() + timedelta(days=3),
                "deadline_description": "3 days from now",
            }

        student_name_hint = (parsed.get("student_name") or "").lower().strip()

        # Find matching student by name hint
        matched = None
        if student_name_hint:
            for s in students:
                if student_name_hint in s.name.lower():
                    matched = s
                    break

        # If only ONE student, auto-assign without asking
        if not matched and len(students) == 1:
            matched = students[0]

        # Carry file material through
        parsed["material_file_id"]   = material_file_id
        parsed["material_file_type"] = material_file_type
        parsed["material_file_name"] = material_file_name

        if not matched:
            # Multiple students and no name match — show picker
            keyboard = [
                [InlineKeyboardButton(s.name, callback_data=f"assign_student|{s.telegram_id}")]
                for s in students
            ]
            context.user_data["pending_assignment"] = parsed
            file_note = f"\n📎 File attached: {material_file_name}" if material_file_id else ""
            await update.message.reply_text(
                f"📋 Assignment captured:\n*{parsed['title']}*\n"
                f"Deadline: {parsed['deadline'].strftime('%B %d, %Y')}{file_note}\n\n"
                "Which student should receive this?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        await _create_and_send_assignment(update, context, db, teacher, matched, parsed)

    elif intent_type == "status_query":
        await _send_teacher_status(update, db, teacher)

    elif intent_type == "student_query":
        # "How is Riya doing?" → per-student LLM summary
        students = crud.get_students_by_teacher(db, teacher.id)
        matched_student = None
        tl = text.lower()
        for s in students:
            if s.name.split()[0].lower() in tl or s.name.lower() in tl:
                matched_student = s
                break
        if not matched_student and students:
            matched_student = students[-1]  # fallback: most recent
        if matched_student:
            assignments = crud.get_assignments_for_student(db, matched_student.telegram_id)
            active = [a for a in assignments if a.submission]
            if active:
                a = active[-1]
                try:
                    reply = teacher_agent.answer_student_query(
                        teacher.name, matched_student.name,
                        a.title, a.submission.progress_notes or "", text
                    )
                except Exception as e:
                    logger.warning(f"student_query LLM failed: {e}")
                    reply = f"{matched_student.name} has {len(active)} assignment(s). Use /status for full summary."
                await update.message.reply_text(f"📊 About {matched_student.name}:\n\n{reply}")
            else:
                await update.message.reply_text(f"{matched_student.name} has no active assignments yet.")
        else:
            await update.message.reply_text("No students found. Use /students to see your class.")

    else:
        # ── Catch-all: teacher sent something we don't recognise ───────────────
        # Use LLM to generate a helpful contextual reply instead of a dead-end message
        try:
            from agents.llm import call_llm
            reply = call_llm(
                system=(
                    "You are a helpful classroom management assistant. "
                    "The teacher sent a message you couldn't classify. "
                    "Respond helpfully and briefly. If it looks like they want to assign work, "
                    "remind them they can just describe the task naturally. "
                    "If it's a question, answer it. Always stay on-topic for classroom management."
                ),
                user=f"Teacher message: {text}\n\nAvailable commands: assign work, check status, /students, /invite"
            )
            await update.message.reply_text(reply)
        except Exception as e:
            logger.warning(f"Catch-all LLM reply failed: {e}")
            await update.message.reply_text(
                "I'm not sure what you mean. Here's what you can do:\n\n"
                "📝 *Assign work* — just describe it naturally, e.g:\n"
                "_Complete Chapter 3 exercises, due in 2 days_\n\n"
                "📊 *Check status* — _How are my students doing?_\n\n"
                "🔗 */invite* — get your invite link\n"
                "👥 */students* — list your students",
                parse_mode="Markdown"
            )


async def _send_teacher_status(update, db, teacher):
    """Helper to send class status summary."""
    from datetime import datetime
    students = crud.get_students_by_teacher(db, teacher.id)
    students_data = []
    for s in students:
        for a in crud.get_assignments_for_student(db, s.telegram_id):
            sub = a.submission
            if sub:
                days_left = (a.deadline - datetime.utcnow()).days
                students_data.append({
                    "name": s.name,
                    "assignment_title": a.title,
                    "status": sub.status,
                    "days_left": days_left,
                    "progress_notes": sub.progress_notes,
                })
    try:
        summary = summariser_agent.generate_class_summary(students_data)
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        summary = "\n".join(
            f"• {d['name']}: {d['assignment_title']} — {d['status']}, {d['days_left']}d left"
            for d in students_data
        ) or "No active assignments."
    await update.message.reply_text(f"📊 Class Status:\n\n{summary}")


async def _handle_student_message(update, context, db, student, text):
    assignments = crud.get_assignments_for_student(db, student.telegram_id)
    active = [a for a in assignments if a.submission and a.submission.status != "completed"]

    if not active:
        await update.message.reply_text(
            "You have no active assignments right now. "
            "Your teacher will assign work soon!"
        )
        return

    # Use most recent active assignment
    assignment = active[-1]
    submission = assignment.submission

    intent = intent_agent.classify_intent(text)
    intent_type = intent.get("intent", "other")

    completion_check = student_agent.check_if_complete(text)
    if completion_check.get("is_complete") and completion_check.get("confidence", 0) > 0.7:
        intent_type = "completion"

    if intent_type == "completion":
        pending_submission[student.telegram_id] = assignment.id
        prompt = student_agent.request_submission(student.name, assignment.title)
        await update.message.reply_text(prompt)
    else:
        crud.update_submission_progress(db, submission, text, status="in_progress")
        ack = student_agent.acknowledge_progress(student.name, text, assignment.title)
        await update.message.reply_text(ack)

        # Notify teacher of progress
        teacher = student.teacher
        summary = teacher_agent.generate_status_summary(
            student.name, assignment.title, assignment.deadline,
            submission.status, submission.progress_notes
        )
        try:
            await context.bot.send_message(
                chat_id=teacher.telegram_id,
                text=f"📬 Update from {student.name}:\n\n{summary}"
            )
        except Exception as e:
            logger.warning(f"Could not notify teacher: {e}")


async def _handle_teacher_feedback(update, context, db, telegram_id, text):
    submission_id = pending_feedback.pop(telegram_id)
    from db.models import Submission
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        await update.message.reply_text("Submission not found.")
        return

    formatted = teacher_agent.reformat_feedback(text, submission.student.name)
    crud.save_feedback(db, submission, formatted)

    await update.message.reply_text("✅ Feedback saved and will be sent to the student!")

    # Send feedback to student
    delivery = student_agent.deliver_feedback(
        submission.student.name, submission.assignment.title, formatted
    )
    try:
        await context.bot.send_message(
            chat_id=submission.student.telegram_id,
            text=f"📝 Feedback from your teacher:\n\n{delivery}"
        )
    except Exception as e:
        logger.warning(f"Could not send feedback to student: {e}")


async def _handle_student_submission(update, context, db, telegram_id, text):
    assignment_id = pending_submission.pop(telegram_id)
    from db.models import Assignment
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        await update.message.reply_text("Assignment not found.")
        return

    submission = assignment.submission
    student = crud.get_student_by_telegram_id(db, telegram_id)
    file_id = ""
    file_type = ""

    # Extract file from any supported media type
    msg = update.message
    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
        text = msg.caption or "(photo submitted)"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "document"
        text = msg.caption or f"({msg.document.file_name or 'document'} submitted)"
    elif msg.audio:
        file_id = msg.audio.file_id
        file_type = "audio"
        text = msg.caption or "(audio submitted)"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
        text = msg.caption or "(video submitted)"
    elif msg.voice:
        file_id = msg.voice.file_id
        file_type = "voice"
        text = msg.caption or "(voice note submitted)"
    elif msg.video_note:
        file_id = msg.video_note.file_id
        file_type = "video"
        text = "(video note submitted)"

    crud.mark_submission_complete(db, submission, text=text, file_id=file_id, file_type=file_type)

    await update.message.reply_text(
        "🎉 Great work! Your submission has been sent to your teacher."
    )

    # Notify teacher
    teacher = assignment.teacher
    notification = summariser_agent.generate_completion_notification(
        teacher.name, student.name, assignment.title, text, bool(file_id)
    )
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Give Feedback", callback_data=f"feedback_yes:{submission.id}")],
            [InlineKeyboardButton("Later", callback_data=f"feedback_no:{submission.id}")],
        ])
        msg = await context.bot.send_message(
            chat_id=teacher.telegram_id,
            text=notification,
            reply_markup=keyboard
        )
        # If file was submitted, forward it
        if file_type == "photo":
            await context.bot.send_photo(chat_id=teacher.telegram_id, photo=file_id,
                                          caption=f"Submission from {student.name}")
        elif file_type == "document":
            await context.bot.send_document(chat_id=teacher.telegram_id, document=file_id,
                                             caption=f"Submission from {student.name}")
    except Exception as e:
        logger.warning(f"Could not notify teacher of submission: {e}")


def _extract_file_info(message) -> tuple[str, str, str]:
    """Extract (file_id, file_type, file_name) from any Telegram message."""
    if message.photo:
        return message.photo[-1].file_id, "photo", "photo.jpg"
    if message.document:
        return message.document.file_id, "document", (message.document.file_name or "document")
    if message.audio:
        return message.audio.file_id, "audio", (message.audio.file_name or "audio")
    if message.video:
        return message.video.file_id, "video", "video"
    if message.voice:
        return message.voice.file_id, "voice", "voice_note"
    if message.video_note:
        return message.video_note.file_id, "video", "video_note"
    return "", "", ""


async def _handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE, file_type: str):
    """Shared handler for all media types (photo, document, audio, video, voice, sticker)."""
    telegram_id = str(update.effective_user.id)
    db = _db()
    try:
        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        if teacher:
            # Teacher sent a file — treat caption as assignment instruction
            caption = update.message.caption or ""
            file_id, ftype, fname = _extract_file_info(update.message)

            if caption.strip():
                # Process caption as assignment + attach file as material
                await _handle_teacher_message(
                    update, context, db, teacher, caption,
                    material_file_id=file_id,
                    material_file_type=ftype,
                    material_file_name=fname,
                )
            else:
                await update.message.reply_text(
                    f"📎 {fname} received!\n\n"
                    "Add a caption to assign it, e.g.:\n"
                    "_Assign saiSS this assignment, due in 3 days_",
                    parse_mode="Markdown"
                )
            return

        student = crud.get_student_by_telegram_id(db, telegram_id)
        if not student:
            await update.message.reply_text(
                "Please register first. Ask your teacher for an invite link."
            )
            return

        if telegram_id in pending_submission:
            await _handle_student_submission(update, context, db, telegram_id, "")
            return

        assignments = crud.get_assignments_for_student(db, telegram_id)
        active = [a for a in assignments if a.submission and a.submission.status != "completed"]
        if active:
            pending_submission[telegram_id] = active[-1].id
            await _handle_student_submission(update, context, db, telegram_id, "")
        else:
            await update.message.reply_text("You have no active assignments to submit to right now.")
    finally:
        db.close()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_media(update, context, "photo")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_media(update, context, "document")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_media(update, context, "audio")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_media(update, context, "video")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_media(update, context, "voice")

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stickers — just acknowledge them warmly."""
    telegram_id = str(update.effective_user.id)
    db = _db()
    try:
        student = crud.get_student_by_telegram_id(db, telegram_id)
        if student:
            await update.message.reply_text("😊 Love the energy! Don't forget to update me on your assignment progress.")
    finally:
        db.close()


async def assign_to_student_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle teacher selecting a student for assignment."""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("assign_student|"):
        return

    # Safe split using | separator
    _, student_telegram_id = query.data.split("|", 1)
    telegram_id = str(query.from_user.id)

    db = _db()
    try:
        teacher = crud.get_teacher_by_telegram_id(db, telegram_id)
        student = crud.get_student_by_telegram_id(db, student_telegram_id)
        parsed = context.user_data.get("pending_assignment")

        if not teacher or not student or not parsed:
            await query.edit_message_text("Something went wrong. Please try again.")
            return

        await _create_and_send_assignment(update, context, db, teacher, student, parsed, via_callback=True)
    finally:
        db.close()


async def _create_and_send_assignment(update, context, db, teacher, student, parsed, via_callback=False):
    mat_file_id   = parsed.get("material_file_id", "")
    mat_file_type = parsed.get("material_file_type", "")
    mat_file_name = parsed.get("material_file_name", "")

    assignment = crud.create_assignment(
        db,
        teacher=teacher,
        student_telegram_id=student.telegram_id,
        title=parsed["title"],
        description=parsed["description"],
        deadline=parsed["deadline"],
        raw_instruction=parsed.get("raw_instruction", ""),
        material_file_id=mat_file_id,
        material_file_type=mat_file_type,
        material_file_name=mat_file_name,
    )

    file_note = f"\n📎 With file: {mat_file_name}" if mat_file_id else ""
    msg = (
        f"✅ Assignment created for *{student.name}*:\n"
        f"_{parsed['title']}_\n"
        f"Due: {parsed['deadline'].strftime('%B %d, %Y')}"
        f"{file_note}"
    )

    if via_callback:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

    # Notify student with text message
    notify_msg = student_agent.generate_assignment_message(
        student.name, parsed["title"], parsed["description"], parsed["deadline"]
    )
    try:
        await context.bot.send_message(chat_id=student.telegram_id, text=notify_msg)

        # Forward the assignment file to student if present
        if mat_file_id:
            caption = f"📎 Assignment material from {teacher.name}"
            if mat_file_type == "photo":
                await context.bot.send_photo(chat_id=student.telegram_id, photo=mat_file_id, caption=caption)
            elif mat_file_type == "document":
                await context.bot.send_document(chat_id=student.telegram_id, document=mat_file_id, caption=caption)
            elif mat_file_type == "audio":
                await context.bot.send_audio(chat_id=student.telegram_id, audio=mat_file_id, caption=caption)
            elif mat_file_type == "video":
                await context.bot.send_video(chat_id=student.telegram_id, video=mat_file_id, caption=caption)
            elif mat_file_type == "voice":
                await context.bot.send_voice(chat_id=student.telegram_id, voice=mat_file_id, caption=caption)

    except Exception as e:
        logger.warning(f"Could not notify student: {e}")


def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("invite", invite),
        CommandHandler("students", list_students),
        CommandHandler("assign", assign_command),
        CommandHandler("status", status_command),
        CallbackQueryHandler(assign_to_student_callback, pattern=r"^assign_student\|"),
        CallbackQueryHandler(button_callback),
        # All supported media types
        MessageHandler(filters.PHOTO, handle_photo),
        MessageHandler(filters.Document.ALL, handle_document),
        MessageHandler(filters.AUDIO, handle_audio),
        MessageHandler(filters.VIDEO, handle_video),
        MessageHandler(filters.VOICE, handle_voice),
        MessageHandler(filters.VIDEO_NOTE, handle_video),
        MessageHandler(filters.Sticker.ALL, handle_sticker),
        # Text last
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
    ]
