#!/usr/bin/env python3
"""
Unit tests for Andrei's Web Dev Client Acquisition.
Uses mocks — no real API calls or emails sent during tests.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../src")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.test"))

import main
from src import db
from src import writer
from src import classifier
from src import discovery
from src import sender


class TestOpenRouterChat(unittest.TestCase):
    """Test OpenRouter chat function with mocked requests."""

    @patch("src.writer.requests.post")
    def test_chat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello response"}}]
        }
        mock_post.return_value = mock_response

        result = writer.chat(
            "System prompt", "User prompt", "test-key", temperature=0.7
        )
        self.assertEqual(result, "Hello response")

    @patch("src.writer.requests.post")
    def test_chat_rate_limit(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("429")
        mock_post.return_value = mock_response

        result = writer.chat(
            "System prompt", "User prompt", "test-key", max_retries=1
        )
        self.assertIsNone(result)

    @patch("src.writer.requests.post")
    def test_chat_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("500 Error")
        mock_post.return_value = mock_response

        result = writer.chat(
            "System prompt", "User prompt", "test-key", max_retries=1
        )
        self.assertIsNone(result)


class TestDatabase(unittest.TestCase):
    """Test SQLite database operations."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        db.DB_PATH = self.db_path
        db.init_db(self.db_path)

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
        lead_id = db.add_lead_record(data, db_path=self.db_path)
        self.assertIsNotNone(lead_id)

        leads = db.get_draft_leads(10, db_path=self.db_path)
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
        lead_id = db.add_lead_record(data, db_path=self.db_path)
        db.mark_sent(lead_id, "leads", self.db_path)

        leads = db.get_draft_leads(10, db_path=self.db_path)
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
        db.add_lead_record(data, db_path=self.db_path)
        self.assertTrue(db.email_exists("john@testcorp.com", "leads", self.db_path))
        self.assertFalse(db.email_exists("nonexistent@test.com", "leads", self.db_path))

    def test_blacklist(self):
        db.add_to_blacklist("blocked@test.com", "Blocked Biz", "Spam complainer", self.db_path)
        self.assertTrue(db.is_blacklisted("blocked@test.com", self.db_path))
        self.assertFalse(db.is_blacklisted("ok@test.com", self.db_path))

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
        db.add_to_whitelist(data, self.db_path)
        wl = db.get_whitelist_leads(10, self.db_path)
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
        db.add_to_whitelist(data, self.db_path)
        wl = db.get_whitelist_leads(10, self.db_path)
        wl_id = wl[0]["id"]
        new_id = db.move_whitelist_to_leads(wl_id, self.db_path)
        self.assertIsNotNone(new_id)
        wl2 = db.get_whitelist_leads(10, self.db_path)
        self.assertEqual(len(wl2), 0)
        leads = db.get_draft_leads(10, db_path=self.db_path)
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
        db.add_lead_record(data, db_path=self.db_path)
        results = db.search_leads("Rose City", db_path=self.db_path)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["business_name"], "Rose City Handyman")

    def test_get_stats(self):
        stats = db.get_stats(self.db_path)
        self.assertIn("sent", stats)
        self.assertIn("draft", stats)
        self.assertIn("whitelist", stats)
        self.assertIn("blacklist", stats)
        self.assertIn("sent_today", stats)


class TestSendEmail(unittest.TestCase):
    """Test email sending with mocked SMTP."""

    @patch("src.sender.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        result = sender.send_email(
            "test@example.com", "Hello", "<p>Body</p>",
            "smtp.gmail.com", 587, "user@gmail.com", "pass",
            "Test User", "user@gmail.com",
        )
        self.assertTrue(result)
        mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@gmail.com", "pass")
        mock_server.quit.assert_called_once()

    @patch("src.sender.smtplib.SMTP")
    def test_send_email_failure(self, mock_smtp):
        mock_server = MagicMock()
        mock_server.login.side_effect = Exception("Auth failed")
        mock_smtp.return_value = mock_server

        result = sender.send_email(
            "test@example.com", "Hello", "<p>Body</p>",
            "smtp.gmail.com", 587, "user@gmail.com", "pass",
            "Test User", "user@gmail.com",
        )
        self.assertFalse(result)


class TestClassifier(unittest.TestCase):
    """Test reply classification."""

    def test_interested(self):
        self.assertEqual(
            classifier.classify_reply("I'm interested in your services"),
            "Interested",
        )
        self.assertEqual(
            classifier.classify_reply("Yes, please tell me more"),
            "Interested",
        )

    def test_not_interested(self):
        self.assertEqual(
            classifier.classify_reply("Not interested, thanks"),
            "Not interested",
        )
        self.assertEqual(
            classifier.classify_reply("Stop emailing me"),
            "Not interested",
        )

    def test_out_of_office(self):
        self.assertEqual(
            classifier.classify_reply("I am out of office"),
            "Out of office",
        )
        self.assertEqual(
            classifier.classify_reply("OOO until Monday"),
            "Out of office",
        )

    def test_other(self):
        self.assertEqual(classifier.classify_reply("Hello there"), "Other")


class TestDiscovery(unittest.TestCase):
    """Test discovery module functions."""

    def test_extract_emails(self):
        emails = discovery.extract_emails("Contact us at john@biz.com or jane@biz.com")
        self.assertIn("john@biz.com", emails)
        self.assertIn("jane@biz.com", emails)

    def test_extract_emails_empty(self):
        self.assertEqual(discovery.extract_emails(""), [])
        self.assertEqual(discovery.extract_emails("no emails here"), [])

    def test_filter_business_emails(self):
        emails = ["john@gmail.com", "owner@biz.com", "info@company.com"]
        filtered = discovery.filter_business_emails(emails)
        self.assertIn("owner@biz.com", filtered)
        self.assertIn("info@company.com", filtered)
        self.assertNotIn("john@gmail.com", filtered)

    def test_is_directory_site(self):
        self.assertTrue(discovery.is_directory_site("https://yelp.com/biz/abc"))
        self.assertFalse(discovery.is_directory_site("https://realbiz.com"))

    def test_has_website_builder(self):
        self.assertTrue(discovery.has_website_builder("https://biz.wix.com"))
        self.assertFalse(discovery.has_website_builder("https://realbiz.com"))


class TestWriter(unittest.TestCase):
    """Test email writer."""

    def test_make_subject(self):
        subject = writer.make_subject("Rose City Handyman")
        self.assertEqual(subject, "A website idea for Rose City Handyman")

    def test_template_fallback(self):
        body = writer.write_email(
            "Test Biz",
            "They offer eco-friendly cleaning",
            "cleaning",
            "Test User",
            "Test Company",
            "Test value prop",
            openrouter_api_key=None,
        )
        self.assertIn("Test Biz", body)
        self.assertIn("Test User", body)
        self.assertIn("STOP", body)

    def test_categorize(self):
        from src.main import categorize
        self.assertEqual(categorize("Rose City Cleaning"), "cleaning")
        self.assertEqual(categorize("PDX Landscaping"), "landscaping")
        self.assertEqual(categorize("Handyman Pro"), "handyman")
        self.assertEqual(categorize("Unknown Biz"), "services")

    def test_clean_business_name(self):
        from src.main import clean_business_name
        self.assertEqual(
            clean_business_name("Rose City Handyman | Home Services"),
            "Rose City Handyman",
        )
        self.assertEqual(
            clean_business_name("PDX Cleaning (About)"),
            "PDX Cleaning",
        )


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
