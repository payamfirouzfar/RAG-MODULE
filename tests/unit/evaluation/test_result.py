from __future__ import annotations

from ragtorch.evaluation.result import current_git_commit


def test_current_git_commit_is_cached():
    first = current_git_commit()
    second = current_git_commit()
    assert first == second
    assert current_git_commit() is second or (first is None and second is None)


def test_current_git_commit_returns_str_or_none():
    result = current_git_commit()
    assert result is None or isinstance(result, str)
