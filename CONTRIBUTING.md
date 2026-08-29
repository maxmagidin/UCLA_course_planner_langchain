# Contributing

Create a branch from `langchain-migration`, run `make setup`, and keep changes
focused on the active LangGraph/FastAPI/Vite runtime. Keep optional model use
request-scoped and provider-neutral; never add server-owned model keys.

Before opening a pull request, run:

```bash
make check
npm --prefix frontend run build
```

Tests that touch UCLA network sources must mock them in the ordinary suite.
When a parser changes, add a de-identified fixture and expected classification.
Never commit DARS reports, API keys, cookies, student identifiers, or scraped
private data.
