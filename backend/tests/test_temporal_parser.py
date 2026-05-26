"""
Tests for the temporal query parsing engine.
Covers relative time parsing, quarter ranges, specific calendar dates, and query cleaning.

Run with: python -m unittest backend/tests/test_temporal_parser.py
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.intelligence.temporal.parser import parse_temporal_query


class TestTemporalParser(unittest.TestCase):
    """Tests for the parse_temporal_query helper."""

    def setUp(self):
        # Anchor time: Monday May 25, 2026 10:00:00 UTC
        self.anchor = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)

    def test_parse_last_hours(self):
        start, end, query = parse_temporal_query("deployments last 4 hours", anchor_time=self.anchor)
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual(query, "deployments")
        # Difference should be exactly 4 hours
        diff = (end - start).total_seconds()
        self.assertEqual(diff, 4 * 3600)

    def test_parse_last_days(self):
        start, end, query = parse_temporal_query("incidents during past 7 days", anchor_time=self.anchor)
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual(query, "incidents")
        diff = (end - start).total_seconds()
        self.assertEqual(diff, 7 * 24 * 3600)

    def test_parse_today_yesterday(self):
        start, end, query = parse_temporal_query("outage today", anchor_time=self.anchor)
        self.assertEqual(query, "outage")
        self.assertEqual(start.hour, 0)
        self.assertEqual(start.minute, 0)

        start_y, end_y, query_y = parse_temporal_query("yesterday rollback", anchor_time=self.anchor)
        self.assertEqual(query_y, "rollback")
        # yesterday start is 1 day ago at 00:00
        self.assertEqual(start_y.day, 24)

    def test_parse_quarters(self):
        # Q2 in 2026: April 1 to June 30
        start, end, query = parse_temporal_query("migration since Q2", anchor_time=self.anchor)
        self.assertEqual(query, "migration")
        self.assertEqual(start.month, 4)
        self.assertEqual(start.day, 1)
        self.assertEqual(end.month, 6)
        self.assertEqual(end.day, 30)

    def test_parse_calendar_dates(self):
        # "since march 12" -> March 12, 2026
        start, end, query = parse_temporal_query("errors since march 12", anchor_time=self.anchor)
        self.assertEqual(query, "errors")
        self.assertEqual(start.month, 3)
        self.assertEqual(start.day, 12)
        self.assertEqual(start.year, 2026)

    def test_no_temporal_expressions(self):
        start, end, query = parse_temporal_query("what is the database connection pool limit", anchor_time=self.anchor)
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertEqual(query, "what is the database connection pool limit")


if __name__ == "__main__":
    unittest.main()
