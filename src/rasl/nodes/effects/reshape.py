"""Reshape: regroup a matrix's values into rows of a set width."""

from __future__ import annotations

import numpy as np
from pydantic import Field

from rasl.graph.node import BaseNode, TickContext, TransformNodeConfig, node
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import MatrixPayload


@node("ReshapeNode", "Reshape")
class ReshapeNode(BaseNode):
    """Regroups a matrix's values row-major into rows of ``components`` values.

    A 170 × 3 RGB matrix becomes 510 × 1 with ``components 1``, and 510 single channels
    become 170 triplets with ``components 3``. The values are read row by row and
    written row by row: nothing is reordered, only regrouped.

    Ports:
        input ``input``: a matrix (any width) whose total values (rows × columns) are a
            multiple of ``components``. Checked when the graph is built where the rows
            and width are known, else on each frame.
        output ``output``: a matrix of ``components`` columns and ``values / components``
            rows.

    Example config::

        node Reshape triplets {
            components 3;
            connect channels;
        }

    A changed ``components`` restarts the node (no ``update_config``).
    """

    class Config(TransformNodeConfig):
        """Configuration for ReshapeNode."""

        components: int = Field(..., ge=1, description="Values per output row")

    def __init__(self, config: Config) -> None:
        """Build the ports for ``config.components``."""
        super().__init__(config)
        self._components = config.components
        self.inputs = PortGroup.inputs(
            input=InputPortSpec(MatrixPayload, values_multiple_of=self._components)
        )
        self.outputs = PortGroup.outputs(
            output=OutputPortSpec(MatrixPayload, components=self._components)
        )

    async def pull(self, tick: TickContext) -> None:
        """Write the input's values, regrouped into rows of ``components``, to ``output``.

        The output is a new float32 array of shape (values / components, components),
        never a view of the input's buffer. Writes nothing when the input has no frame.

        Raises:
            ValueError: If the frame's total values are not a multiple of ``components``.
        """
        frame = self.inputs.input.read()
        if frame is None:
            return
        values = np.asarray(frame.payload.data, dtype=np.float32).reshape(-1)
        if values.size % self._components != 0:
            raise ValueError(
                f"Reshape {self.id}: {values.size} values is not a multiple of "
                f"{self._components} components"
            )
        regrouped = np.array(values, dtype=np.float32, copy=True).reshape(-1, self._components)
        self.outputs.output.write(frame.with_payload(MatrixPayload(regrouped)))
