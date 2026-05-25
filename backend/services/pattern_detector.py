import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from backend.services.db_manager import DBManager

logger = logging.getLogger(__name__)


class PatternDetector:
    """
    Analyzes derived events incrementally to detect operational patterns:
    - Recurring incidents involving the same entity (e.g. repeated database instability).
    - Escalation chains (e.g. incidents/escalations happening within 60 minutes of a deployment).
    - Frequency spikes (e.g. sudden volume increases of specific event types).
    Enforces strict workspace isolation.
    """

    def __init__(self, db_manager: Optional[DBManager] = None):
        self.db = db_manager or DBManager()

    def analyze_event(self, event_id: str, event: Dict[str, Any]):
        """
        Runs the pattern detection suite on a newly created event.
        """
        try:
            workspace_id = event.get("workspace_id", "default_workspace")
            logger.info(
                f"Analyzing operational pattern triggers for event '{event['title']}' "
                f"({event_id}) in workspace '{workspace_id}'..."
            )
            
            # Rule 1: Recurring Issues / Incidents
            self._detect_recurring_incidents(event_id, event, workspace_id)

            # Rule 2: Escalation Chains (Deployment -> Incident / Escalation)
            self._detect_escalation_chains(event_id, event, workspace_id)

            # Rule 3: Frequency Spikes
            self._detect_frequency_spikes(event_id, event, workspace_id)

        except Exception as e:
            logger.error(f"Failed pattern detection for event {event_id}: {e}", exc_info=True)

    def _detect_recurring_incidents(self, event_id: str, event: Dict[str, Any], workspace_id: str):
        """
        Detects if incidents or escalations sharing entities occur repeatedly within the last 7 days.
        """
        if event.get("event_type") not in ["incident", "escalation"]:
            return

        now = datetime.now(timezone.utc)
        seven_days_ago = (now - timedelta(days=7)).isoformat()
        
        # Fetch events from last 7 days in the same workspace
        recent_events = self.db.get_timeline(start_time=seven_days_ago, limit=200, workspace_id=workspace_id)
        
        entities = event.get("entities", [])
        if not entities:
            return

        for entity in entities:
            # Skip generic entities
            if entity.lower() in ["discussion", "incident", "deployment", "slack", "notion", "production", "environment"]:
                continue

            # Find historical matching incidents/escalations involving the same entity
            matching_events = []
            for ev in recent_events:
                if ev.get("event_type") in ["incident", "escalation"] and entity in ev.get("entities", []):
                    matching_events.append(ev)

            # If count of incidents/escalations for this entity is >= 2, register a recurring incident pattern
            if len(matching_events) >= 2:
                # Compile details
                event_ids = [ev["event_id"] for ev in matching_events]
                if event_id not in event_ids:
                    event_ids.append(event_id)
                
                pattern_id = f"pattern_recurring_{entity.lower().replace(' ', '_')}"
                count = len(event_ids)
                
                severity = "high" if count > 3 else "medium"
                confidence = min(0.7 + (count * 0.05), 0.99)
                
                name = f"Recurring incident sequence involving {entity}"
                description = (
                    f"Detected {count} incidents/escalations involving the entity '{entity}' "
                    f"in the last 7 days. This points to potential system instability."
                )

                self.db.add_pattern(
                    pattern_id=pattern_id,
                    pattern_type="recurring_incident",
                    name=name,
                    description=description,
                    severity=severity,
                    confidence=round(confidence, 2),
                    last_detected=now.isoformat(),
                    entities=[entity],
                    related_events=event_ids,
                    workspace_id=workspace_id
                )
                logger.info(f"Pattern detected: '{name}' (Confidence: {confidence:.2f})")

    def _detect_escalation_chains(self, event_id: str, event: Dict[str, Any], workspace_id: str):
        """
        Detects if an incident or escalation (or discussion) occurs within 60 minutes of a deployment event.
        """
        if event.get("event_type") not in ["incident", "escalation", "discussion"]:
            return

        event_time_str = event.get("timestamp")
        if not event_time_str:
            return

        try:
            event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
        except Exception:
            event_time = datetime.now(timezone.utc)

        # Look back 60 minutes for deployment events in the same workspace
        start_lookback = (event_time - timedelta(minutes=60)).isoformat()
        end_lookback = event_time.isoformat()
        
        recent_events = self.db.get_timeline(
            start_time=start_lookback, end_time=end_lookback, limit=50, workspace_id=workspace_id
        )
        
        deployments = [ev for ev in recent_events if ev.get("event_type") == "deployment"]
        if not deployments:
            return

        for deploy in deployments:
            # We found a deployment followed by an issue within 60 mins!
            pattern_id = f"pattern_chain_{deploy['event_id']}_{event_id}"
            
            # Combine entities
            entities_set = set(event.get("entities", [])).union(set(deploy.get("entities", [])))
            # Exclude generic words
            filtered_entities = [
                ent for ent in entities_set 
                if ent.lower() not in ["discussion", "incident", "deployment", "slack", "notion", "production", "environment"]
            ]

            # Construct name and description
            deploy_name = deploy.get("title", "Deployment")
            issue_name = event.get("title", "Issue")
            
            name = "Escalation chain following deployment"
            description = (
                f"Incident/Escalation '{issue_name}' was triggered shortly after "
                f"'{deploy_name}'. Temporal spacing: less than 60 minutes."
            )
            
            self.db.add_pattern(
                pattern_id=pattern_id,
                pattern_type="escalation_chain",
                name=name,
                description=description,
                severity="high",
                confidence=0.85,
                last_detected=datetime.now(timezone.utc).isoformat(),
                entities=filtered_entities,
                related_events=[deploy["event_id"], event_id],
                workspace_id=workspace_id
            )
            logger.info(f"Pattern detected: '{name}' between deploy {deploy['event_id']} and issue {event_id}")

    def _detect_frequency_spikes(self, event_id: str, event: Dict[str, Any], workspace_id: str):
        """
        Detects if the volume of events of a specific type in the last 24h exceeds the daily baseline.
        """
        event_type = event.get("event_type")
        if not event_type or event_type == "discussion":
            return

        now = datetime.now(timezone.utc)
        one_day_ago = (now - timedelta(days=1)).isoformat()
        eight_days_ago = (now - timedelta(days=8)).isoformat()

        # Get all events from the past 8 days in the same workspace
        events_last_8_days = self.db.get_timeline(start_time=eight_days_ago, limit=500, workspace_id=workspace_id)
        
        # Count in last 24h vs preceding 7 days
        count_24h = 0
        count_baseline = 0

        for ev in events_last_8_days:
            if ev.get("event_type") != event_type:
                continue
            
            ev_ts = ev.get("timestamp")
            if not ev_ts:
                continue

            if ev_ts >= one_day_ago:
                count_24h += 1
            else:
                count_baseline += 1

        # Calculate average daily count for baseline
        avg_daily_baseline = count_baseline / 7.0
        
        is_spike = False
        if avg_daily_baseline == 0 and count_24h >= 3:
            is_spike = True
        elif avg_daily_baseline > 0 and count_24h >= 3 and count_24h >= 2.5 * avg_daily_baseline:
            is_spike = True

        if is_spike:
            pattern_id = f"pattern_spike_{event_type}"
            name = f"Spike in {event_type} frequency"
            description = (
                f"Surge in operational events of type '{event_type}' detected: "
                f"{count_24h} events in the last 24 hours, compared to a baseline average "
                f"of {avg_daily_baseline:.1f} per day."
            )
            
            # Find all relevant event IDs
            event_ids = [
                ev["event_id"] for ev in events_last_8_days 
                if ev.get("event_type") == event_type and ev.get("timestamp", "") >= one_day_ago
            ]
            if event_id not in event_ids:
                event_ids.append(event_id)

            self.db.add_pattern(
                pattern_id=pattern_id,
                pattern_type="frequency_spike",
                name=name,
                description=description,
                severity="medium",
                confidence=0.80,
                last_detected=now.isoformat(),
                entities=[],
                related_events=event_ids,
                workspace_id=workspace_id
            )
            logger.info(f"Pattern detected: '{name}' (Count: {count_24h}, Baseline: {avg_daily_baseline:.1f}/day)")
