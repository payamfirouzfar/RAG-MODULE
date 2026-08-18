"""AST-based import-boundary check for ragtorch.retrieval, reusing the
established Step 7/8/24 pattern
(test_architecture_module_has_no_provider_dependencies and its
siblings): parse each module's actual source, collect every imported
top-level module name, assert none matches a forbidden provider/
network-client name. A naive substring scan would false-positive on
"torch" being contained in "ragtorch", so imports are parsed via ast,
not grepped.
"""

from __future__ import annotations

import ast
import inspect

import ragtorch.retrieval.bm25 as bm25_module
import ragtorch.retrieval.fusion as fusion_module

FORBIDDEN = (
    "openai",
    "anthropic",
    "google",
    "cohere",
    "pinecone",
    "chromadb",
    "qdrant",
    "weaviate",
    "langchain",
    "llama_index",
    "haystack",
    "requests",
    "httpx",
    "urllib3",
    "aiohttp",
    "torch",
    "transformers",
)


def _imported_top_level_modules(module) -> set[str]:
    source = inspect.getsource(module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0].lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0].lower())
    return imported


def test_bm25_module_has_no_provider_or_network_dependencies():
    imported = _imported_top_level_modules(bm25_module)
    for name in FORBIDDEN:
        assert name not in imported, f"unexpected import in bm25.py: {name}"


def test_fusion_module_has_no_provider_or_network_dependencies():
    imported = _imported_top_level_modules(fusion_module)
    for name in FORBIDDEN:
        assert name not in imported, f"unexpected import in fusion.py: {name}"
