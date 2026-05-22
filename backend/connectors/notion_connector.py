import os

from notion_client import Client

notion = Client(
    auth=os.getenv("NOTION_API_KEY")
)

result = notion.search()

print(result)