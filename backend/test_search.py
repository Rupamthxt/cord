from retrieval.search import search

results = search(
    "Why are onboarding problems increasing?"
)

for result in results:
    print("\n")
    print(result[1][0].payload["text"])