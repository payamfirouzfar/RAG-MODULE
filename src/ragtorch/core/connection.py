"""Connection: a single, directed, validated data-flow edge (ADR-015).

Connection persists the fact "this node's declared output feeds that
node's declared input" as data, which check_connection() (ADR-014)
deliberately does not do -- it only checks whether a proposed pairing
would be legal, in the moment, without recording the answer. Connection
is the missing element a future graph/Block composition layer can hold
a collection of.

Connection deliberately does not know about cardinality (whether an
output can feed multiple inputs, or an input can receive multiple
outputs), cycles, execution order, or serialization -- all future work
for a collection/graph type built on top of this element. See ADR-015
Non-goals for the full list.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort, check_connection


@dataclass(frozen=True)
class Connection:
    """A single, directed, validated data-flow edge.

    Construction-time validated: node identifiers must be non-empty
    strings, source_port must actually be an OutputPort, target_port
    must actually be an InputPort, and the pair must be compatible per
    check_connection() (ADR-014). Any violation raises ValidationError
    and no Connection is created. A successfully constructed Connection
    is therefore always known-valid for its lifetime.

    Directionality is enforced at runtime, not just via type
    annotations: Python does not enforce dataclass field annotations,
    and check_connection() does not normalize non-Port arguments into
    ValidationError, so an isinstance check here is what actually
    prevents constructing a "connection" with its ends swapped.
    """

    source_node_id: str
    source_port: OutputPort
    target_node_id: str
    target_port: InputPort

    def __post_init__(self) -> None:
        if not isinstance(self.source_node_id, str) or not self.source_node_id:
            raise ValidationError("Connection source_node_id must be a non-empty string.")
        if not isinstance(self.target_node_id, str) or not self.target_node_id:
            raise ValidationError("Connection target_node_id must be a non-empty string.")
        if not isinstance(self.source_port, OutputPort):
            raise ValidationError("Connection source_port must be an OutputPort.")
        if not isinstance(self.target_port, InputPort):
            raise ValidationError("Connection target_port must be an InputPort.")
        check_connection(self.source_port, self.target_port)
