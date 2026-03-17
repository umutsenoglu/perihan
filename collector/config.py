"""Collector configuration."""

from pathlib import Path

# Output directory for generated content
OUTPUT_DIR = Path(__file__).parent / "output"

# Content categories and their subdirectories
CATEGORIES = {
    "knowledge": "Generic knowledge articles on specific topics",
    "medical": "Doctor reports, lab results, prescriptions, appointment notes",
    "messaging": "WhatsApp, email, SMS conversation histories",
    "legal": "Court proceedings, lawyer correspondence, legal documents",
    "finance": "Bank statements, invoices, tax documents",
    "personal": "Diaries, personal notes, journals, to-do lists, reflections",
    "calendar": "Appointments, events, reminders, schedules",
    "trello": "Trello board exports in XML format",
}

# How many files to generate per batch
BATCH_SIZE = 3

# Seconds between batches
BATCH_INTERVAL = 30

# Gemini model for content generation
GEMINI_MODEL = "gemini-2.0-flash"
