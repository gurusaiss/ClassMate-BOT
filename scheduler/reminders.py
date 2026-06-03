"""
Reminder scheduler — runs reminder checks and sends proactive nudges.
Uses APScheduler; launched alongside the bot in main.py.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from db.models import SessionLocal
from db import crud
from agents import reminder_agent, summariser_agent
from datetime import datetime

logger = logging.getLogger(__name__)


async def check_and_send_reminders(bot: Bot):
    """Check all active submissions and send reminders as needed."""
    db = SessionLocal()
    try:
        active_submissions = crud.get_active_submissions(db)
        for submission in active_submissions:
            if not reminder_agent.should_send_reminder(submission):
                continue

            student = submission.student
            assignment = submission.assignment

            msg = reminder_agent.generate_reminder(
                student.name,
                assignment.title,
                assignment.deadline,
                submission.reminder_count or 0,
            )
            try:
                await bot.send_message(chat_id=student.telegram_id, text=msg)
                crud.update_reminder_timestamp(db, submission)
                logger.info(f"Sent reminder to {student.name} for {assignment.title}")
            except Exception as e:
                logger.warning(f"Failed to send reminder to {student.telegram_id}: {e}")
    finally:
        db.close()


async def send_daily_teacher_summary(bot: Bot):
    """Send proactive daily summary to all teachers."""
    db = SessionLocal()
    try:
        teachers = crud.get_all_teachers(db)
        for teacher in teachers:
            students = crud.get_students_by_teacher(db, teacher.id)
            students_data = []
            for s in students:
                for a in crud.get_assignments_for_student(db, s.telegram_id):
                    sub = a.submission
                    if sub and sub.status != "completed":
                        days_left = (a.deadline - datetime.utcnow()).days
                        students_data.append({
                            "name": s.name,
                            "assignment_title": a.title,
                            "status": sub.status,
                            "days_left": days_left,
                            "progress_notes": sub.progress_notes,
                        })

            if not students_data:
                continue

            summary = summariser_agent.generate_class_summary(students_data)
            try:
                await bot.send_message(
                    chat_id=teacher.telegram_id,
                    text=f"📊 Good morning! Daily class summary:\n\n{summary}"
                )
            except Exception as e:
                logger.warning(f"Failed to send summary to teacher {teacher.telegram_id}: {e}")
    finally:
        db.close()


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # Check reminders every 30 minutes
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        minutes=30,
        args=[bot],
        id="reminder_check",
    )

    # Daily teacher summary at 9 AM UTC
    scheduler.add_job(
        send_daily_teacher_summary,
        trigger="cron",
        hour=9,
        minute=0,
        args=[bot],
        id="daily_summary",
    )

    scheduler.start()
    logger.info("Scheduler started.")
    return scheduler
