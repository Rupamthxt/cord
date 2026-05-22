import os

from notion_client import Client
from backend.connectors.base import BaseConnector

class NotionConnector(BaseConnector):
    def __init__(self):
        self.notion = Client(
            auth = os.getenv("NOTION_API_KEY")
        )
    
    def fetch(self) -> str:
        results = self.notion.search()
        return results['results'][0]['id']

    def get_page_blocks(self, page_id):
        blocks = self.notion.blocks.children.list(block_id=page_id)
        return blocks['results']

    

def main():
    connector = NotionConnector()
    page_id = connector.fetch()
    blocks = connector.get_page_blocks(page_id)
    print(blocks[2])


if __name__ == "__main__":
    main()