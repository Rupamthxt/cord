from backend.retrieval.search import search

results = search(
    "Why are onboarding problems increasing?"
)

for result in results:
    print("\n")
    p = result[1][0].payload
    print(p["text"])
    print("\nSource: ",p['metadata']['source'])