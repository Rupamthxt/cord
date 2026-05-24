import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
DB_PATH = os.path.join(DB_DIR, "memory_store.db")


class DBManager:
    """
    Manages SQLite-based relational database for organizational reasoning:
    - Entity co-occurrences and scoring.
    - Operational events and mappings to chunks.
    - Cross-source correlations.
    """

    def __init__(self):
        # Ensure database directory exists
        os.makedirs(DB_DIR, exist_ok=True)
        self.initialize_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"SQLite transaction failed: {e}")
            raise e
        finally:
            conn.close()

    def initialize_db(self):
        """Create schema tables if they do not exist."""
        with self.get_connection() as conn:
            # 1. Entity co-occurrences
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_cooccurrences (
                    entity_a TEXT,
                    entity_b TEXT,
                    score REAL DEFAULT 1.0,
                    last_seen TEXT,
                    PRIMARY KEY (entity_a, entity_b)
                )
            """)
            
            # 2. Events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    title TEXT,
                    timestamp TEXT,
                    summary TEXT,
                    event_type TEXT,
                    related_teams TEXT
                )
            """)

            # 3. Event entity mappings
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_entities (
                    event_id TEXT,
                    entity_name TEXT,
                    PRIMARY KEY (event_id, entity_name),
                    FOREIGN KEY(event_id) REFERENCES events(event_id)
                )
            """)

            # 4. Event source references (chunk links)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_source_refs (
                    event_id TEXT,
                    source_ref TEXT,
                    PRIMARY KEY (event_id, source_ref),
                    FOREIGN KEY(event_id) REFERENCES events(event_id)
                )
            """)

            # 5. Cross-source correlations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS correlations (
                    correlation_id TEXT PRIMARY KEY,
                    source_a TEXT,
                    source_b TEXT,
                    correlation_type TEXT,
                    score REAL,
                    reason TEXT,
                    timestamp TEXT,
                    UNIQUE(source_a, source_b, correlation_type)
                )
            """)
        logger.info(f"SQLite Relational Memory database initialized at: {DB_PATH}")

    def add_event(
        self,
        event_id: str,
        title: str,
        timestamp: str,
        summary: str,
        event_type: str,
        entities: List[str],
        source_refs: List[str],
        related_teams: List[str]
    ):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (event_id, title, timestamp, summary, event_type, related_teams)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, title, timestamp, summary, event_type, ",".join(related_teams))
            )
            for entity in entities:
                conn.execute(
                    "INSERT OR IGNORE INTO event_entities (event_id, entity_name) VALUES (?, ?)",
                    (event_id, entity)
                )
            for ref in source_refs:
                conn.execute(
                    "INSERT OR IGNORE INTO event_source_refs (event_id, source_ref) VALUES (?, ?)",
                    (event_id, ref)
                )

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
            if not row:
                return None
            
            entities_rows = conn.execute("SELECT entity_name FROM event_entities WHERE event_id = ?", (event_id,)).fetchall()
            source_rows = conn.execute("SELECT source_ref FROM event_source_refs WHERE event_id = ?", (event_id,)).fetchall()
            
            return {
                "event_id": row["event_id"],
                "title": row["title"],
                "timestamp": row["timestamp"],
                "summary": row["summary"],
                "event_type": row["event_type"],
                "related_teams": row["related_teams"].split(",") if row["related_teams"] else [],
                "entities": [r["entity_name"] for r in entities_rows],
                "source_refs": [r["source_ref"] for r in source_rows]
            }

    def record_cooccurrence(self, entity_a: str, entity_b: str, weight: float = 1.0, timestamp: str = None):
        if entity_a.lower() == entity_b.lower():
            return
        
        # Keep lexicographical order to prevent duplicates like (A, B) and (B, A)
        ent_first, ent_second = sorted([entity_a, entity_b])
        if not timestamp:
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO entity_cooccurrences (entity_a, entity_b, score, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entity_a, entity_b) DO UPDATE SET
                    score = score + EXCLUDED.score,
                    last_seen = EXCLUDED.last_seen
                """,
                (ent_first, ent_second, weight, timestamp)
            )

    def traverse_relationships(self, entity_name: str, depth: int = 1) -> List[Dict[str, Any]]:
        """
        Retrieves direct and indirect co-occurrence relationships for an entity.
        Useful for graph traversal query support.
        """
        with self.get_connection() as conn:
            query = """
                SELECT entity_b AS related_entity, score FROM entity_cooccurrences WHERE entity_a = ?
                UNION
                SELECT entity_a AS related_entity, score FROM entity_cooccurrences WHERE entity_b = ?
                ORDER BY score DESC
            """
            rows = conn.execute(query, (entity_name, entity_name)).fetchall()
            return [{"entity": r["related_entity"], "score": r["score"]} for r in rows]

    def add_correlation(self, source_a: str, source_b: str, c_type: str, score: float, reason: str, timestamp: str):
        # Order inputs lexicographically to keep database keys stable
        s_first, s_second = sorted([source_a, source_b])
        correlation_id = f"{s_first}_{s_second}_{c_type}"
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO correlations (correlation_id, source_a, source_b, correlation_type, score, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(correlation_id) DO UPDATE SET
                    score = EXCLUDED.score,
                    reason = EXCLUDED.reason,
                    timestamp = EXCLUDED.timestamp
                """,
                (correlation_id, s_first, s_second, c_type, score, reason, timestamp)
            )

    def get_correlations_for_source(self, source_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            query = """
                SELECT source_b AS related_source, correlation_type, score, reason, timestamp FROM correlations WHERE source_a = ?
                UNION
                SELECT source_a AS related_source, correlation_type, score, reason, timestamp FROM correlations WHERE source_b = ?
                ORDER BY score DESC
            """
            rows = conn.execute(query, (source_id, source_id)).fetchall()
            return [
                {
                    "related_source": r["related_source"],
                    "type": r["correlation_type"],
                    "score": r["score"],
                    "reason": r["reason"],
                    "timestamp": r["timestamp"]
                }
                for r in rows
            ]

    def get_timeline(
        self,
        start_time: str = None,
        end_time: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            query = "SELECT event_id FROM events"
            params = []
            
            conditions = []
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)
                
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
                
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            
            events = []
            for r in rows:
                ev = self.get_event(r["event_id"])
                if ev:
                    events.append(ev)
            return events
