#!/usr/bin/env python3
"""
Tests for lead outreach automation.
Uses mocks - no real API calls or emails sent during tests.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(".env.test")

import main


class TestOpenRouterChat(unittest.TestCase):
    """Test OpenRouter chat function with mocked requests."""

    @patch("main.requests.post")
    def test_chat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello response"}}]
        }
        mock_post.return_value = mock_response

        result = main.chat("System prompt", "User prompt", temperature=0.7)
        self.assertEqual(result, "Hello response")

    @patch("main.requests.post")
    def test_chat_rate_limit(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("429")
        mock_post.return_value = mock_response

        result = main.chat("System prompt", "User prompt", max_retries=1)
        self.assertIsNone(result)

    @patch("main.requests.post")
    def test_chat_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("500 Error")
        mock_post.return_value = mock_response

        result = main.chat("System prompt", "User prompt", max_retries=1)
        self.assertIsNone(result)


class TestDatabase(unittest.TestCase):
    """Test SQLite database operations."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        main.DB_PATH = self.db_path
        main.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_add_and_get_lead(self):
        data = {
            "lead_number": 1,
            "business_name": "Test Corp",
            "business_category": "cleaning",
            "city_state": "Portland, OR",
            "owner_contact_name": "John Doe",
            "public_business_email": "john@testcorp.com",
            "email_source_url": "https://example.com",
            "business_phone": "503-555-0123",
            "website_status": "NO WEBSITE",
            "website_evidence": "No website found in search",
            "google_rating": 4.5,
            "google_review_count": 45,
            "google_business_profile_url": "https://g.page/testcorp",
            "recent_activity_date": "2026-10-01",
            "recent_activity_source_url": "https://facebook.com/testcorp",
            "personalization_fact": "They offer eco-friendly cleaning",
            "personalization_source_url": "https://testcorp.com/about",
            "qualification_status": "qualified",
            "confidence_level": "high",
            "email_subject": "A website idea for Test Corp",
            "email_body": "Hi Test Corp team,...",
        }
        lead_id = main.add_lead_record(data)
        self.assertIsNotNone(lead_id)

        leads = main.get_draft_leads(10)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["business_name"], "Test Corp")
        self.assertEqual(leads[0]["public_business_email"], "john@testcorp.com")
        self.assertEqual(leads[0]["sending_status"], "draft")

    def test_mark_sent(self):
        data = {
            "lead_number": 1,
            "business_name": "Test Corp",
            "business_category": "cleaning",
            "city_state": "Portland, OR",
            "owner_contact_name": "John Doe",
            "public_business_email": "john@testcorp.com",
            "email_source_url": "https://example.com",
            "business_phone": "503-555-0123",
            "website_status": "NO WEBSITE",
            "website_evidence": "No website found",
            "google_rating": 4.5,
            "google_review_count": 45,
            "google_business_profile_url": "https://g.page/testcorp",
            "recent_activity_date": "2026-10-01",
            "recent_activity_source_url": "https://facebook.com/testcorp",
            "personalization_fact": "Eco-friendly cleaning",
            "personalization_source_url": "https://testcorp.com",
            "qualification_status": "qualified",
            "confidence_level": "high",
            "email_subject": "Test subject",
            "email_body": "Test body",
        }
        lead_id = main.add_lead_record(data)
        main.mark_sent(lead_id)

        leads = main.get_draft_leads(10)
        self.assertEqual(len(leads), 0)

    def test_email_exists(self):
        data = {
            "lead_number": 1,
            "business_name": "Test Corp",
            "business_category": "cleaning",
            "city_state": "Portland, OR",
            "owner_contact_name": "John Doe",
            "public_business_email": "john@testcorp.com",
            "email_source_url": "https://example.com",
            "business_phone": "503-555-0123",
            "website_status": "NO WEBSITE",
            "website_evidence": "No website found",
            "google_rating": 4.5,
            "google_review_count": 45,
            "google_business_profile_url": "https://g.page/testcorp",
            "recent_activity_date": "2026-10-01",
            "recent_activity_source_url": "https://facebook.com/testcorp",
            "personalization_fact": "Eco-friendly cleaning",
            "personalization_source_url": "https://testcorp.com",
            "qualification_status": "qualified",
            "confidence_level": "high",
            "email_subject": "Test subject",
            "email_body": "Test body",
        }
        main.add_lead_record(data)
        self.assertTrue(main.email_exists("john@testcorp.com"))
        self.assertFalse(main.email_exists("nonexistent@test.com"))

    def test_blacklist(self):
        main.add_to_blacklist("blocked@test.com", "Blocked Biz", "Spam complainer")
        self.assertTrue(main.is_blacklisted("blocked@test.com"))
        self.assertFalse(main.is_blacklisted("ok@test.com"))

    def test_whitelist(self):
        data = {
            "lead_number": 1,
            "business_name": "Whitelisted Biz",
            "business_category": "cleaning",
            "city_state": "Portland, OR",
            "owner_contact_name": "Jane Doe",
            "public_business_email": "jane@whitelist.com",
            "email_source_url": "https://example.com",
            "business_phone": "503-555-0123",
            "website_status": "NO WEBSITE",
            "website_evidence": "No website found",
            "google_rating": 4.5,
            "google_review_count": 45,
            "google_business_profile_url": "https://g.page/testcorp",
            "recent_activity_date": "2026-10-01",
            "recent_activity_source_url": "https://facebook.com/testcorp",
            "personalization_fact": "Eco-friendly cleaning",
            "personalization_source_url": "https://testcorp.com",
            "qualification_status": "qualified",
            "confidence_level": "high",
            "email_subject": "Test subject",
            "email_body": "Test body",
            "priority": 5,
        }
        main.add_to_whitelist(data)
        wl = main.get_whitelist_leads(10)
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["business_name"], "Whitelisted Biz")
        self.assertEqual(wl[0]["priority"], 5)

    def test_move_whitelist_to_leads(self):
        data = {
            "lead_number": 1,
            "business_name": "Move Test",
            "business_category": "cleaning",
            "city_state": "Portland, OR",
            "owner_contact_name": "Jane Doe",
            "public_business_email": "move@test.com",
            "email_source_url": "https://example.com",
            "business_phone": "503-555-0123",
            "website_status": "NO WEBSITE",
            "website_evidence": "No website found",
            "google_rating": 4.5,
            "google_review_count": 45,
            "google_business_profile_url": "https://g.page/testcorp",
            "recent_activity_date": "2026-10-01",
            "recent_activity_source_url": "https://facebook.com/testcorp",
            "personalization_fact": "Eco-friendly cleaning",
            "personalization_source_url": "https://testcorp.com",
            "qualification_status": "qualified",
            "confidence_level": "high",
            "email_subject": "Test subject",
            "email_body": "Test body",
            "priority": 1,
        }
        main.add_to_whitelist(data)
        wl = main.get_whitelist_leads(10)
        wl_id = wl[0]["id"]
        new_id = main.move_whitelist_to_leads(wl_id)
        self.assertIsNotNone(new_id)
        # Whitelist should now be empty
        wl2 = main.get_whitelist_leads(10)
        self.assertEqual(len(wl2), 0)
        # Lead should be in leads table as draft
        leads = main.get_draft_leads(10)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["business_name"], "Move Test")

    def test_search_leads(self):
        data = {
            "lead_number": 1,
            "business_name": "Rose City Handyman",
            "business_category": "handyman",
            "city_state": "Portland, OR",
            "owner_contact_name": "John Doe",
            "public_business_email": "rose@cityhandyman.com",
            "email_source_url": "https://example.com",
            "business_phone": "503-555-0123",
            "website_status": "NO WEBSITE",
            "website_evidence": "No website found",
            "google_rating": 4.5,
            "google_review_count": 45,
            "google_business_profile_url": "https://g.page/testcorp",
            "recent_activity_date": "2026-10-01",
            "recent_activity_source_url": "https://facebook.com/testcorp",
            "personalization_fact": "Handyman services",
            "personalization_source_url": "https://testcorp.com",
            "qualification_status": "qualified",
            "confidence_level": "high",
            "email_subject": "Test subject",
            "email_body": "Test body",
        }
        main.add_lead_record(data)
        results = main.search_leads("Rose City")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["business_name"], "Rose City Handyman")

    def test_get_stats(self):
        stats = main.get_stats()
        self.assertIn("sent", stats)
        self.assertIn("draft", stats)
        self.assertIn("whitelist", stats)
        self.assertIn("blacklist", stats)
        self.assertIn("sent_today", stats)


class TestSendEmail(unittest.TestCase):
    """Test email sending with mocked SMTP."""

    @patch("main.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        result = main.send_email("test@example.com", "Hello", "<p>Body</p>")
        self.assertTrue(result)
        mock_smtp.assert_called_once_with(main.SMTP_HOST, main.SMTP_PORT)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(main.SMTP_USER, main.SMTP_PASS)
        mock_server.quit.assert_called_once()

    @patch("main.smtplib.SMTP")
    def test_send_email_failure(self, mock_smtp):
        mock_server = MagicMock()
        mock_server.login.side_effect = Exception("Auth failed")
        mock_smtp.return_value = mock_server

        result = main.send_email("test@example.com", "Hello", "<p>Body</p>")
        self.assertFalse(result)


class TestClassifyReply(unittest.TestCase):
    """Test reply classification."""

    def test_interested(self):
        self.assertEqual(main.classify_reply("I'm interested in your services"), "Interested")
        self.assertEqual(main.classify_reply("Yes, please tell me more"), "Interested")

    def test_not_interested(self):
        self.assertEqual(main.classify_reply("Not interested, thanks"), "Not interested")
        self.assertEqual(main.classify_reply("Stop emailing me"), "Not interested")

    def test_out_of_office(self):
        self.assertEqual(main.classify_reply("I am out of office"), "Out of office")
        self.assertEqual(main.classify_reply("OOO until Monday"), "Out of office")

    def test_other(self):
        self.assertEqual(main.classify_reply("Hello there"), "Other")


class TestConfig(unittest.TestCase):
    """Test that required config is present."""

    def test_openrouter_key_set(self):
        self.assertIsNotNone(main.OPENROUTER_API_KEY)
        self.assertTrue(main.OPENROUTER_API_KEY.startswith("sk-or-"))

    def test_smtp_configured(self):
        self.assertIsNotNone(main.SMTP_USER)
        self.assertIsNotNone(main.SMTP_PASS)

    def test_from_email_set(self):
        self.assertIsNotNone(main.FROM_EMAIL)

    def test_search_key_set(self):
        self.assertIsNotNone(main.SEARCH_API_KEY)


if __name__ == "__main__":
    unittest.main()
