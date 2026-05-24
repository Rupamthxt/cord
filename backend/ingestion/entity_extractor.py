import re
from typing import Dict, List, Any, Set

class EntityExtractor:
    """
    Lightweight, high-performance entity extractor using regex patterns
    and keyword matchers for operational and organizational metadata.
    """
    
    # Predefined keyword maps for exact/substring matching
    TEAMS = {"engineering", "product", "qa", "support", "devops", "ops", "marketing", "sales", "hr", "finance", "design"}
    SYSTEMS = {"postgres", "postgresql", "qdrant", "aws", "s3", "docker", "kubernetes", "fastapi", "ollama", "sentence-transformers", "github", "jira"}
    ENVIRONMENTS = {"production", "prod", "staging", "dev", "development", "localhost", "test"}
    PRODUCTS = {"notion", "slack", "stripe"}
    OPERATIONAL_CONCEPTS = {"deployment", "migration", "onboarding", "backup", "postmortem", "incident report", "runbook", "sprint"}

    def __init__(self):
        # Compile regexes for speed
        self.project_pattern = re.compile(r"\bproject[-_ ]([a-zA-Z0-9_\-]+)\b", re.IGNORECASE)
        self.incident_pattern = re.compile(r"\b(inc[-_ ][0-9]+|incident[-_ ][0-9]+|outage|sev[-_ ][0-9])\b", re.IGNORECASE)
        self.mention_pattern = re.compile(r"@([a-zA-Z0-9_\.\-]+)")
        
        # Capture capitalization patterns for potential custom projects or products
        self.proper_noun_pattern = re.compile(r"\b[A-Z][a-zA-Z0-9_\-]+\b")

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extract entities from text and return both lists of names and details.
        
        Returns:
            Dict containing:
                "entities": List[str] (names of extracted entities)
                "details": List[Dict[str, str]] (dicts containing "name" and "type")
        """
        if not text:
            return {"entities": [], "details": []}

        details: List[Dict[str, str]] = []
        seen_names: Set[str] = set()

        def add_entity(name: str, entity_type: str):
            normalized_name = name.strip()
            # De-duplicate case-insensitively but preserve case of first mention
            lower_name = normalized_name.lower()
            if lower_name not in seen_names:
                seen_names.add(lower_name)
                details.append({"name": normalized_name, "type": entity_type})

        # 1. Regex Matchers
        # Extract Projects
        projects = self.project_pattern.findall(text)
        for proj in projects:
            add_entity(proj, "project")

        # Extract Incidents
        incidents = self.incident_pattern.findall(text)
        for inc in incidents:
            add_entity(inc, "incident")

        # Extract Mentions (People)
        mentions = self.mention_pattern.findall(text)
        for mention in mentions:
            add_entity(mention, "person")

        # 2. Keyword Matchers
        # Split text into tokens for word-level matches (simple lowercase tokenization)
        words = set(re.findall(r"\b[a-zA-Z0-9_\-]+\b", text.lower()))

        for word in words:
            if word in self.TEAMS:
                add_entity(word.capitalize(), "team")
            elif word in self.SYSTEMS:
                # Handle database naming display cleanly
                display_name = "PostgreSQL" if word in ["postgres", "postgresql"] else word.capitalize()
                add_entity(display_name, "system")
            elif word in self.ENVIRONMENTS:
                add_entity(word, "environment")
            elif word in self.PRODUCTS:
                add_entity(word.capitalize(), "product")
            elif word in self.OPERATIONAL_CONCEPTS:
                add_entity(word, "operational_concept")

        # Look for explicit project-like names in proper nouns (e.g. "Project Apollo" -> Apollo is a project)
        # If "Project X" matches, X is already added. Let's scan for predefined known projects.
        known_projects = {"apollo", "cord", "phoenix", "nexus", "aurora", "copilot"}
        for word in words:
            if word in known_projects:
                add_entity(word.capitalize(), "project")

        # Format output
        entity_names = [d["name"] for d in details]
        return {
            "entities": entity_names,
            "details": details
        }
