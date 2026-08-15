"""Integration tests: modules composed via Sequential and nested Modules
working together end to end (Level B evaluation)."""

from __future__ import annotations

from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


class UpperCase(Module):
    def forward(self, input: str) -> str:
        return input.upper()


class Reverse(Module):
    def forward(self, input: str) -> str:
        return input[::-1]


class Prefix(Module):
    def __init__(self, prefix: str):
        super().__init__()
        self.prefix = prefix

    def forward(self, input: str) -> str:
        return f"{self.prefix}{input}"


class TextPipeline(Module):
    """A composite module built from a nested Sequential, exercising
    registration + inspection + execution together."""

    def __init__(self):
        super().__init__()
        self.stages = Sequential(UpperCase(), Reverse(), Prefix(">> "))

    def forward(self, input: str) -> str:
        return self.stages(input)


def test_end_to_end_pipeline_output():
    pipeline = TextPipeline()
    assert pipeline("hello") == ">> OLLEH"


def test_pipeline_inspection_reflects_nested_structure():
    pipeline = TextPipeline()
    out = pipeline.inspect()
    assert "stages (Sequential)" in out
    assert "step0 (UpperCase)" in out
    assert "step2 (Prefix)" in out


def test_pipeline_named_modules_are_dotted():
    pipeline = TextPipeline()
    names = [n for n, _ in pipeline.named_modules()]
    assert "stages.step0" in names
    assert "stages.step1" in names
    assert "stages.step2" in names


def test_pipeline_module_count():
    pipeline = TextPipeline()
    assert sum(1 for _ in pipeline.modules()) == 5  # pipeline + stages + 3 steps
