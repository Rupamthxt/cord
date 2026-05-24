import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class QueryClassifier:
    """
    Lightweight keyword and rule-based classifier that maps incoming queries
    to operational intelligence query profiles.
    """

    # Keyword mappings for classification
    CLASSIFICATION_PROFILES = {
        "root_cause_analysis": {
            "keywords": ["why", "root cause", "reason", "because", "cause", "triggered", "after release", "rollback", "failed due to"],
            "explanation": "Query focuses on finding correlation chains, dependencies, or preceding triggers of an incident."
        },
        "recurring_issue": {
            "keywords": ["recurring", "repeated", "rising", "again", "frequent", "often", "frequently", "repeatedly"],
            "explanation": "Query focuses on identifying repeated system failures, outages, or recurring onboarding issues."
        },
        "trend_analysis": {
            "keywords": ["trend", "progression", "increasing", "worsening", "over time", "history", "month", "days", "growth"],
            "explanation": "Query focuses on temporal progression, frequency changes, or operational trend signals over time."
        },
        "escalation_analysis": {
            "keywords": ["escalation", "escalate", "alert", "pagerduty", "severity", "sev", "paged", "on-call"],
            "explanation": "Query focuses on operational escalation paths, alert response times, or severity-level escalations."
        },
        "bottleneck_analysis": {
            "keywords": ["bottleneck", "delay", "blocked", "slow", "onboarding", "pipeline", "wasting time", "worsening delay"],
            "explanation": "Query focuses on identifying slower workflows, onboarding blockers, or pipeline delivery delays."
        },
        "timeline_analysis": {
            "keywords": ["timeline", "sequence", "chronology", "history", "when", "first", "then", "followed by", "progression"],
            "explanation": "Query focuses on a chronological breakdown of events and source references."
        },
        "anomaly_investigation": {
            "keywords": ["anomaly", "unusual", "spike", "outage", "leak", "failure", "jump", "outlier", "sudden"],
            "explanation": "Query focuses on investigating sudden deviations, metrics spikes, or unexpected system states."
        }
    }

    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classifies the incoming query and returns the matching profile.
        """
        query_lower = query.lower()
        matched_profile = None
        max_matches = 0
        matched_keywords = []

        # Find profile with highest matching keywords count
        for profile, details in self.CLASSIFICATION_PROFILES.items():
            matches = []
            for kw in details["keywords"]:
                # Use regex with word boundary to avoid partial matches (e.g. 'why' in 'anywhere')
                if re.search(r"\b" + re.escape(kw) + r"\b", query_lower):
                    matches.append(kw)
            
            if len(matches) > max_matches:
                max_matches = len(matches)
                matched_profile = profile
                matched_keywords = matches
            elif len(matches) == max_matches and len(matches) > 0:
                # Tie breaker: prefer root_cause or recurring_issue
                if profile in ["root_cause_analysis", "recurring_issue"] and matched_profile not in ["root_cause_analysis", "recurring_issue"]:
                    matched_profile = profile
                    matched_keywords = matches

        # Fallback to recurring_issue if no keywords match but query is operational,
        # or default to general search
        if not matched_profile:
            # Fall back to root_cause_analysis if query starts with question words
            if query_lower.startswith(("how", "what", "which", "where")):
                matched_profile = "root_cause_analysis"
                matched_keywords = []
            else:
                matched_profile = "recurring_issue"
                matched_keywords = []

        details = self.CLASSIFICATION_PROFILES.get(matched_profile, {
            "explanation": "Query classified under general operational query profile."
        })

        # Confidence calculation: based on matches count
        confidence = 0.5 + min(len(matched_keywords) * 0.15, 0.49)

        logger.info(f"Query classified: '{query}' -> {matched_profile} (Confidence: {confidence:.2f})")
        
        return {
            "query_type": matched_profile,
            "confidence": round(confidence, 2),
            "keywords_matched": matched_keywords,
            "explanation": details["explanation"]
        }
