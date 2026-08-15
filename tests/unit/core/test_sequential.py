from __future__ import annotations

import pytest

from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


class AddOne(Module):
    def forward(self, input):
        return input + 1


class Times(Module):
    def __init__(self, factor):
        super().__init__()
        self.factor = factor

    def forward(self, input):
        return input * self.factor


class Boom(Module):
    def forward(self, input):
        raise ValueError("broken step")


def test_empty_sequential_is_identity():
    seq = Sequential()
    assert seq(42) == 42


def test_single_module_sequential():
    seq = Sequential(AddOne())
    assert seq(1) == 2


def test_multiple_modules_thread_output_to_input():
    seq = Sequential(AddOne(), Times(3))
    # (5 + 1) * 3 = 18
    assert seq(5) == 18


def test_len_and_iteration():
    seq = Sequential(AddOne(), Times(2), AddOne())
    assert len(seq) == 3
    assert [type(s).__name__ for s in seq] == ["AddOne", "Times", "AddOne"]


def test_getitem():
    a, b = AddOne(), Times(2)
    seq = Sequential(a, b)
    assert seq[0] is a
    assert seq[1] is b


def test_failure_in_middle_step_propagates():
    seq = Sequential(AddOne(), Boom(), Times(2))
    with pytest.raises(ExecutionError):
        seq(1)


def test_sequential_children_are_registered():
    seq = Sequential(AddOne(), Times(2))
    names = [n for n, _ in seq.named_children()]
    assert names == ["step0", "step1"]


def test_nested_sequential():
    inner = Sequential(AddOne(), AddOne())
    outer = Sequential(inner, Times(10))
    # ((3+1)+1) * 10 = 50
    assert outer(3) == 50
