"""
Unit tests for the Intent Agent.
Tests both the LLM-based classifier and the keyword fallback.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch


# ── Tests for keyword fallback (no LLM needed) ──────────────────────────────

from bot.handlers import _looks_like_assignment

class TestKeywordFallback:
    def test_assign_keyword(self):
        assert _looks_like_assignment("Assign Riya a 500-word essay")

    def test_assignment_keyword(self):
        assert _looks_like_assignment("This is your pre-Internship Assignment with deadline 06-06-2026")

    def test_deadline_keyword(self):
        assert _looks_like_assignment("Complete the report with deadline tomorrow")

    def test_task_keyword(self):
        assert _looks_like_assignment("Please complete this task by Friday")

    def test_essay_keyword(self):
        assert _looks_like_assignment("Write a 500-word essay on climate change")

    def test_homework_keyword(self):
        assert _looks_like_assignment("Submit your homework by 5pm")

    def test_unrelated_text(self):
        assert not _looks_like_assignment("Hello how are you?")

    def test_greeting_no_match(self):
        assert not _looks_like_assignment("Good morning!")

    def test_punctuation_stripped(self):
        assert _looks_like_assignment("essay, due tomorrow.")


# ── Tests for Intent Agent (mocked LLM) ─────────────────────────────────────

class TestIntentAgent:
    def _mock_llm(self, response: dict):
        import json
        return patch("agents.llm.call_llm", return_value=json.dumps(response))

    def test_assign_intent(self):
        with self._mock_llm({"intent": "assign", "confidence": 0.95}):
            from agents.intent_agent import classify_intent
            result = classify_intent("Assign John a math worksheet due tomorrow")
            assert result["intent"] == "assign"
            assert result["confidence"] > 0.5

    def test_progress_intent(self):
        with self._mock_llm({"intent": "progress", "confidence": 0.9}):
            from agents.intent_agent import classify_intent
            result = classify_intent("I've done 2 paragraphs so far")
            assert result["intent"] == "progress"

    def test_completion_intent(self):
        with self._mock_llm({"intent": "completion", "confidence": 0.97}):
            from agents.intent_agent import classify_intent
            result = classify_intent("I've finished the assignment, it's completed!")
            assert result["intent"] == "completion"

    def test_status_query_intent(self):
        with self._mock_llm({"intent": "status_query", "confidence": 0.88}):
            from agents.intent_agent import classify_intent
            result = classify_intent("How are my students doing this week?")
            assert result["intent"] == "status_query"

    def test_fallback_on_llm_error(self):
        """If LLM raises an exception, handlers should catch it gracefully."""
        with patch("agents.llm.call_llm", side_effect=Exception("API error")):
            with pytest.raises(Exception):
                from agents.intent_agent import classify_intent
                classify_intent("some text")  # This will raise — caller wraps in try/except


# ── Tests for Reminder Agent ─────────────────────────────────────────────────

class TestReminderAgent:
    def _make_submission(self, days_left, status="pending", last_reminded=None, count=0):
        from datetime import datetime, timedelta
        from unittest.mock import MagicMock
        sub = MagicMock()
        sub.status = status
        sub.assignment.deadline = datetime.utcnow() + timedelta(days=days_left)
        sub.last_reminded_at = last_reminded
        sub.reminder_count = count
        return sub

    def test_no_reminder_for_completed(self):
        from agents.reminder_agent import should_send_reminder
        sub = self._make_submission(5, status="completed")
        assert not should_send_reminder(sub)

    def test_first_reminder_always_sent(self):
        from agents.reminder_agent import should_send_reminder
        sub = self._make_submission(5, last_reminded=None)
        assert should_send_reminder(sub)

    def test_no_reminder_if_recently_reminded(self):
        from agents.reminder_agent import should_send_reminder
        from datetime import datetime, timedelta
        sub = self._make_submission(5, last_reminded=datetime.utcnow() - timedelta(hours=1))
        assert not should_send_reminder(sub)

    def test_reminder_after_24h_when_far(self):
        from agents.reminder_agent import should_send_reminder
        from datetime import datetime, timedelta
        sub = self._make_submission(10, last_reminded=datetime.utcnow() - timedelta(hours=25))
        assert should_send_reminder(sub)

    def test_escalation_near_deadline(self):
        from agents.reminder_agent import should_send_reminder
        from datetime import datetime, timedelta
        # 1 day left — should send after 6 hours
        sub = self._make_submission(1, last_reminded=datetime.utcnow() - timedelta(hours=7))
        assert should_send_reminder(sub)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
