from __future__ import annotations

import pytest

from ragtorch.core.errors import ExecutionError, RegistryError
from ragtorch.core.module import Module, RAGModule


class Double(Module):
    def forward(self, input):
        return input * 2


class Boom(Module):
    def forward(self, input):
        raise ValueError("kaboom")


class Parent(Module):
    def __init__(self):
        super().__init__()
        self.child_a = Double()
        self.child_b = Double()

    def forward(self, input):
        return self.child_b(self.child_a(input))


def test_forward_via_call():
    m = Double()
    assert m(21) == 42


def test_base_module_forward_not_implemented():
    m = Module()
    with pytest.raises(NotImplementedError):
        m.forward(1)


def test_child_registration_via_attribute_assignment():
    p = Parent()
    names = dict(p.named_children())
    assert set(names) == {"child_a", "child_b"}


def test_children_iteration():
    p = Parent()
    assert len(list(p.children())) == 2


def test_named_modules_includes_self_and_descendants():
    p = Parent()
    names = [n for n, _ in p.named_modules()]
    assert names == ["Parent", "child_a", "child_b"]


def test_modules_includes_self():
    p = Parent()
    mods = list(p.modules())
    assert mods[0] is p
    assert len(mods) == 3


def test_duplicate_registration_same_instance_ok():
    p = Parent()
    p.register_module("child_a", p.child_a)  # no error


def test_duplicate_registration_different_instance_raises():
    p = Parent()
    with pytest.raises(RegistryError, match="already exists"):
        p.register_module("child_a", Double())


def test_register_non_module_raises():
    p = Parent()
    with pytest.raises(RegistryError):
        p.register_module("bad", "not a module")


def test_forward_exception_wrapped_in_execution_error():
    b = Boom()
    with pytest.raises(ExecutionError, match="Boom"):
        b(1)


def test_ragmodule_is_a_module_subclass():
    assert issubclass(RAGModule, Module)


def test_ragmodule_isinstance_check():
    class MyRAG(RAGModule):
        def forward(self, input):
            return input

    assert isinstance(MyRAG(), RAGModule)
    assert isinstance(MyRAG(), Module)
    assert not isinstance(Double(), RAGModule)


def test_repr_no_children():
    assert repr(Double()) == "Double()"


def test_repr_with_children():
    r = repr(Parent())
    assert "Parent(" in r
    assert "(child_a): Double()" in r
    assert "(child_b): Double()" in r


def test_inspect_contains_counts_and_tree():
    p = Parent()
    out = p.inspect()
    assert "Modules: 3" in out
    assert "Depth: 2" in out
    assert "child_a (Double)" in out
    assert "child_b (Double)" in out


# ---------------------------------------------------------------------------
# Step 19: module registration cycle detection
# ---------------------------------------------------------------------------


def test_direct_self_registration_raises():
    m = Double()
    with pytest.raises(RegistryError, match="cycle"):
        m.register_module("self", m)


def test_indirect_two_node_cycle_raises():
    a = Double()
    b = Double()
    a.register_module("b", b)

    with pytest.raises(RegistryError, match="cycle"):
        b.register_module("a", a)


def test_indirect_multi_level_cycle_raises():
    a = Double()
    b = Double()
    c = Double()
    a.register_module("b", b)
    b.register_module("c", c)

    with pytest.raises(RegistryError, match="cycle"):
        c.register_module("a", a)


def test_valid_acyclic_registration_succeeds():
    a = Double()
    b = Double()
    c = Double()
    a.register_module("b", b)
    b.register_module("c", c)  # no error

    assert [name for name, _ in a.named_modules()] == ["Double", "b", "b.c"]


def test_diamond_shaped_sharing_is_not_a_cycle():
    """The same instance registered under two different parents is
    sharing, not a cycle -- register_module only rejects an edge that
    would make a module reachable from itself."""
    shared = Double()
    left = Double()
    right = Double()
    left.register_module("shared", shared)
    right.register_module("shared", shared)  # no error, distinct parents


def test_same_instance_same_name_reregistration_still_ok_with_cycle_check_present():
    p = Parent()
    p.register_module("child_a", p.child_a)  # unchanged pre-existing behavior


def test_different_instance_same_name_still_raises_duplicate_error():
    p = Parent()
    with pytest.raises(RegistryError, match="already exists"):
        p.register_module("child_a", Double())


def test_non_module_registration_still_raises():
    p = Parent()
    with pytest.raises(RegistryError):
        p.register_module("bad", "not a module")


def test_rejected_cycle_does_not_mutate_the_graph():
    a = Double()
    b = Double()
    a.register_module("b", b)

    before = dict(b.named_children())
    with pytest.raises(RegistryError, match="cycle"):
        b.register_module("a", a)

    assert dict(b.named_children()) == before
    assert "a" not in dict(b.named_children())


def test_rejected_cycle_leaves_architecture_traversable():
    parent = Double()
    child = Double()
    parent.register_module("child", child)

    with pytest.raises(RegistryError, match="cycle"):
        child.register_module("parent", parent)

    assert [name for name, _ in parent.named_modules()] == ["Double", "child"]

    snapshot = parent.snapshot()
    assert len(snapshot.nodes) == 2


def test_attribute_assignment_also_rejects_cycles():
    """__setattr__ routes through register_module, so cycle rejection
    applies to attribute-based registration too, not only the explicit
    register_module() call."""

    class Wrapper(Module):
        def __init__(self):
            super().__init__()

        def forward(self, input):
            return input

    a = Wrapper()
    b = Wrapper()
    a.child = b

    with pytest.raises(RegistryError, match="cycle"):
        b.child = a
