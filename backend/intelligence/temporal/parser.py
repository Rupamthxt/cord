"""
backend/temporal/parser.py
--------------------------
Parses user queries for time constraints and date expressions, returning
standard datetime ranges and a cleaned query string.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def parse_temporal_query(
    query: str,
    anchor_time: Optional[datetime] = None,
) -> Tuple[Optional[datetime], Optional[datetime], str]:
    """Parse a natural language query for temporal constraints.

    Returns:
        (start_time, end_time, clean_query)
        where clean_query has the temporal phrases removed.
    """
    if not query:
        return None, None, ""

    if anchor_time is None:
        anchor_time = datetime.now(timezone.utc)

    # Work on a lowercase copy for regex matching
    query_lower = query.lower()
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    matched_phrase: Optional[str] = None

    # 1. Regex Matchers for Relative Times
    # "last X hours"
    m_hours = re.search(r"\b(?:during|since|in|over)?\s*(?:last|past|the\s+last|the\s+past)?\s+(\d+)\s+hours?\b", query_lower)
    if m_hours:
        hours = int(m_hours.group(1))
        start_time = anchor_time - timedelta(hours=hours)
        end_time = anchor_time
        matched_phrase = m_hours.group(0)

    # "last X days"
    m_days = re.search(r"\b(?:during|since|in|over)?\s*(?:last|past|the\s+last|the\s+past)?\s+(\d+)\s+days?\b", query_lower)
    if not start_time and m_days:
        days = int(m_days.group(1))
        start_time = anchor_time - timedelta(days=days)
        end_time = anchor_time
        matched_phrase = m_days.group(0)

    # "last X weeks"
    m_weeks = re.search(r"\b(?:during|since|in|over)?\s*(?:last|past|the\s+last|the\s+past)?\s+(\d+)\s+weeks?\b", query_lower)
    if not start_time and m_weeks:
        weeks = int(m_weeks.group(1))
        start_time = anchor_time - timedelta(weeks=weeks)
        end_time = anchor_time
        matched_phrase = m_weeks.group(0)

    # "last X months"
    m_months = re.search(r"\b(?:during|since|in|over)?\s*(?:last|past|the\s+last|the\s+past)?\s+(\d+)\s+months?\b", query_lower)
    if not start_time and m_months:
        months = int(m_months.group(1))
        start_time = anchor_time - timedelta(days=months * 30)
        end_time = anchor_time
        matched_phrase = m_months.group(0)

    # "last 24 hours" (exact phrase if not caught by digits)
    if not start_time and "last 24 hours" in query_lower:
        start_time = anchor_time - timedelta(hours=24)
        end_time = anchor_time
        matched_phrase = "last 24 hours"

    # "today"
    if not start_time and re.search(r"\btoday\b", query_lower):
        start_time = anchor_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = anchor_time
        matched_phrase = "today"

    # "yesterday"
    if not start_time and re.search(r"\byesterday\b", query_lower):
        start_time = (anchor_time - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_time = anchor_time.replace(hour=0, minute=0, second=0, microsecond=0)
        matched_phrase = "yesterday"

    # 2. Quarters: "since Q[1-4]" or "during Q[1-4]"
    m_q = re.search(r"\b(?:since|during)\s+q([1-4])\b", query_lower)
    if not start_time and m_q:
        q = int(m_q.group(1))
        year = anchor_time.year
        matched_phrase = m_q.group(0)

        # Calculate Quarter ranges
        if q == 1:
            start_time = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_time = datetime(year, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
        elif q == 2:
            start_time = datetime(year, 4, 1, tzinfo=timezone.utc)
            end_time = datetime(year, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
        elif q == 3:
            start_time = datetime(year, 7, 1, tzinfo=timezone.utc)
            end_time = datetime(year, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
        elif q == 4:
            start_time = datetime(year, 10, 1, tzinfo=timezone.utc)
            end_time = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # 3. Explicit Calendar Dates: "since March 12"
    m_date = re.search(
        r"\b(?:since|after|on)\s+([a-z]+)\s+(\d{1,2})\b", query_lower
    )
    if not start_time and m_date:
        month_name = m_date.group(1)
        day = int(m_date.group(2))
        if month_name in MONTH_MAP:
            month = MONTH_MAP[month_name]
            year = anchor_time.year
            try:
                dt = datetime(year, month, day, tzinfo=timezone.utc)
                # If parsed date is in future, assume previous year
                if dt > anchor_time:
                    dt = datetime(year - 1, month, day, tzinfo=timezone.utc)
                start_time = dt
                end_time = anchor_time
                matched_phrase = m_date.group(0)
            except ValueError:
                # Invalid date combination (e.g. Feb 30)
                pass

    # 4. ISO Date format: "since 2026-05-20" or "after 2026-05-20"
    m_iso = re.search(
        r"\b(?:since|after|on)\s+(\d{4}-\d{2}-\d{2})\b", query_lower
    )
    if not start_time and m_iso:
        iso_str = m_iso.group(1)
        try:
            start_time = datetime.fromisoformat(iso_str).replace(tzinfo=timezone.utc)
            end_time = anchor_time
            matched_phrase = m_iso.group(0)
        except ValueError:
            pass

    # 5. Clean query string if we matched a temporal phrase
    clean_query = query
    if matched_phrase:
        # Find exact case match in query to replace
        pattern = re.compile(re.escape(matched_phrase), re.IGNORECASE)
        clean_query = pattern.sub("", query).strip()
        # Clean double spaces
        clean_query = re.sub(r"\s+", " ", clean_query)

    logger.debug(
        "Temporal parser | raw=%r | start=%s | end=%s | clean=%r",
        query,
        start_time,
        end_time,
        clean_query,
    )
    return start_time, end_time, clean_query
