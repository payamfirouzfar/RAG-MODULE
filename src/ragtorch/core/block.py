"""Block: a reusable, itself-composable execution unit built from a
CompositionGraph (ADR-020).

Block structurally satisfies Component via Module's existing name/
component_type properties -- no special case, the same relationship
Sequential already has. It owns a CompositionGraph immutably (supplied
once at construction, exposed read-only) and delegates all execution
to the existing, unmodified plan()/Executor/ExecutionEngine.execute_plan
chain: Block never walks steps, resolves components on a hot path
beyond one dict build per forward() call, or schedules anything
itself. This is the direct, verified consequence of composition.py's
own documented invariant that GraphNode.component is accepted
structurally-typed and unchecked -- the runtime never needs to know a
Block exists.

A single input_node/output_node pair is required at construction; a
graph with no entry/exit-node concept of its own has no other
non-speculative way to answer what Block(input) means without
inventing aggregation semantics CompositionGraph (fan-in <= 1,
ADR-016) and the execution boundary (ADR-018 Q4) have both
deliberately deferred. Every non-input_node step is required to have
exactly one dependency for the same reason -- multi-dependency merge
semantics are explicitly out of scope in this version, not silently
decided here.

ExecutionPlan is derived fresh on every forward() call, not cached at
construction -- a deliberate v0.1 choice pending benchmark evidence
(see ADR-020 Q11 and benchmarks/step16_block_composition.py), matching
this project's "measure before optimizing" discipline established for
ADR-018's own O(n^2) context-copying cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ragtorch.core.composition import CompositionGraph
from ragtorch.core.engine import ExecutionEngine
from ragtorch.core.errors import ValidationError
from ragtorch.core.execution_plan import plan
from ragtorch.core.module import Module

if TYPE_CHECKING:
    from ragtorch.core.context import ExecutionContext
    from ragtorch.core.execution import StepExecutionContext
    from ragtorch.core.execution_plan import ExecutionStep


class Block(Module):
    """A reusable, itself-composable execution unit built from a
    CompositionGraph.

    Structurally satisfies Component via Module's existing name/
    component_type properties. graph, input_node, and output_node are
    fixed at construction and exposed read-only -- no method on Block
    mutates the graph. Component failures propagate as ExecutionError
    via Module.__call__'s existing, unmodified wrapping; no
    Block-specific exception type is introduced.
    """

    def __init__(
        self,
        graph: CompositionGraph,
        *,
        input_node: str,
        output_node: str,
    ) -> None:
        super().__init__()

        if not isinstance(graph, CompositionGraph):
            raise TypeError("Block graph must be a CompositionGraph.")

        node_ids = {node.id for node in graph.nodes}

        if input_node not in node_ids:
            raise ValidationError(
                f"Block input_node {input_node!r} is not a node in the supplied graph."
            )
        if output_node not in node_ids:
            raise ValidationError(
                f"Block output_node {output_node!r} is not a node in the supplied graph."
            )

        execution_plan = plan(graph)
        for step in execution_plan.steps:
            if step.node_id != input_node and len(step.dependencies) != 1:
                raise ValidationError(
                    "Block requires every non-input_node step to have exactly one "
                    f"dependency; step {step.node_id!r} has {len(step.dependencies)}."
                )

        self._graph = graph
        self._input_node = input_node
        self._output_node = output_node

    @property
    def graph(self) -> CompositionGraph:
        """Return the CompositionGraph owned by this Block."""
        return self._graph

    @property
    def input_node(self) -> str:
        """Return the id of the node that receives the Block's input."""
        return self._input_node

    @property
    def output_node(self) -> str:
        """Return the id of the node whose result becomes the Block's output."""
        return self._output_node

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        components = {node.id: node.component for node in self._graph.nodes}

        block_input = input
        block_context = context

        def handler(step: ExecutionStep, context: StepExecutionContext) -> object:
            if step.node_id == self._input_node:
                return components[step.node_id](block_input, context=block_context)
            (dependency,) = step.dependencies
            upstream = context.results[dependency]
            return components[step.node_id](upstream, context=block_context)

        result = ExecutionEngine().execute_plan(plan(self._graph), handler, context=block_context)
        return result.output.values[self._output_node]
