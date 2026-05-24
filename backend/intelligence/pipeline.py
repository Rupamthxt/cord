import time
import logging
from typing import Dict, Any, Optional

from backend.reasoning.query_classifier import QueryClassifier
from backend.intelligence.evidence_aggregator import EvidenceAggregator
from backend.reasoning.root_cause_analyzer import RootCauseAnalyzer
from backend.intelligence.insight_synthesizer import InsightSynthesizer
from backend.services.db_manager import DBManager

logger = logging.getLogger(__name__)


class OperationalIntelligencePipeline:
    """
    Coordinates and executes the multi-stage operational reasoning pipeline:
    Query -> Query Classification -> Evidence Aggregation -> Root-Cause Analyzer -> Insight Synthesis
    """

    def __init__(self, db_manager: Optional[DBManager] = None):
        self.db = db_manager or DBManager()
        self.classifier = QueryClassifier()
        self.aggregator = EvidenceAggregator(db_manager=self.db)
        self.analyzer = RootCauseAnalyzer(db_manager=self.db)
        self.synthesizer = InsightSynthesizer()

    def execute(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Runs the full operational intelligence workflow.
        """
        start_time = time.time()
        logger.info(f"Executing Operational Intelligence Pipeline for: '{query}'")

        # Stage 1: Query Classification
        classification = self.classifier.classify(query)

        # Stage 2 & 3: Evidence Aggregation (fetches chunks, events, and correlations)
        evidence = self.aggregator.aggregate(query, limit=limit)

        # Stage 4: Root Cause & Escalation Chain Analyzer
        root_cause = self.analyzer.analyze(
            query=query,
            related_events=evidence["events"],
            correlations=evidence["correlations"]
        )

        # Stage 5: Insight Synthesis
        insight = self.synthesizer.synthesize(
            query=query,
            query_classification=classification,
            aggregated_evidence=evidence,
            root_cause_analysis=root_cause
        )

        duration = time.time() - start_time
        logger.info(f"Pipeline execution completed in {duration:.4f}s")

        return {
            "query": query,
            "query_type": classification["query_type"],
            "insight": insight,
            "evidence": {
                "chunks": evidence["chunks"],
                "events": evidence["events"],
                "correlations": evidence["correlations"]
            },
            "diagnostics": {
                "query_classification": classification,
                "execution_time_seconds": round(duration, 4),
                "matched_patterns_count": len(root_cause.get("matched_patterns", []))
            }
        }
