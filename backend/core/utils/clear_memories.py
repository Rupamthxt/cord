import os
import logging
from backend.core.models.setup_client import client
from backend.core.services.db_manager import DB_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_sqlite():
    print("Clearing SQLite database...")
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"Successfully deleted SQLite file at: {DB_PATH}")
        except Exception as e:
            print(f"Error deleting SQLite file: {e}")
    else:
        print("SQLite database file does not exist.")

def clear_qdrant():
    print("Clearing Qdrant vector collections...")
    collections = ["workspace_memory", "workspace_events"]
    for col in collections:
        try:
            # Check if exists
            client.get_collection(col)
            # Delete it
            client.delete_collection(col)
            print(f"Successfully deleted Qdrant collection: {col}")
        except Exception as e:
            if "not found" in str(e).lower() or "404" in str(e):
                print(f"Qdrant collection '{col}' does not exist (or in-memory fresh).")
            else:
                print(f"Error deleting Qdrant collection '{col}': {e}")

if __name__ == "__main__":
    clear_sqlite()
    clear_qdrant()
    print("Memory database reset complete!")
