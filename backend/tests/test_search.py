from backend.intelligence.retrieval.search import search

if __name__ == "__main__":
    results = search(
        "Why are onboarding problems increasing?"
    )
    for result in results.get("results", []):
        print("\n")
        print(result.get("content"))
        print("\nSource: ", result.get("source"))