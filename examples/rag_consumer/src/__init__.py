"""RAG consumer demo application: a real external consumer of the
published `ragmodel` package (import name `ragtorch`).

This package is deliberately NOT part of ragtorch itself. Everything
here — scraping, chunking, embeddings, vector store, reranking, prompt
construction, LLM generation — is application-level code that composes
on top of ragtorch.Module/Sequential/ExecutionEngine, exactly as an
external user of the published library would.

Nothing in this package is imported by, or affects, src/ragtorch/.
"""
