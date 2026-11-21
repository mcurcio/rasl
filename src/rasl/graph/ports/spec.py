"""Port specifications: what payload types and how many elements a port takes.

Payload types are named by class or by registered name (see ``rasl.signal.registry``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Type, Union

AcceptsSpec = Union[str, Type, Tuple[str, ...], Tuple[Type, ...]]
"""Type alias for port type constraints.

Can be a single payload type name (e.g., "array") or a tuple of names
(e.g., ("array", "color")) for ports that accept multiple types.
"""

CountSpec = Union[int, Tuple[int], Tuple[int, int], None]
"""Count specification.

- int: Fixed count (e.g., 512)
- (min,): Variable with minimum only (e.g., (0,) for unbounded)
- (min, max): Variable with bounds (e.g., (0, 512))
- None: Variable with no bounds (equivalent to (0,))
"""


def _parse_count_spec(
    spec: CountSpec,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Parse a count specification into (fixed_count, min_count, max_count).

    Returns:
        Tuple of (fixed_count, min_count, max_count).
        If fixed_count is not None, min/max are None.
        If fixed_count is None, this is a variable-length port.
    """
    if spec is None:
        # Variable, no bounds
        return (None, 0, None)
    if isinstance(spec, int):
        # Fixed count
        if spec < 0:
            raise ValueError(f"Count must be non-negative, got {spec}")
        return (spec, None, None)
    if isinstance(spec, tuple):
        if len(spec) == 1:
            # (min,) - variable with minimum only
            min_count = spec[0]
            if not isinstance(min_count, int) or min_count < 0:
                raise ValueError(
                    f"Minimum count must be non-negative int, got {min_count}"
                )
            return (None, min_count, None)
        if len(spec) == 2:
            # (min, max) - variable with bounds
            min_count, max_count = spec
            if not isinstance(min_count, int) or min_count < 0:
                raise ValueError(
                    f"Minimum count must be non-negative int, got {min_count}"
                )
            if not isinstance(max_count, int) or max_count < 0:
                raise ValueError(
                    f"Maximum count must be non-negative int, got {max_count}"
                )
            if max_count < min_count:
                raise ValueError(
                    f"Maximum count ({max_count}) must be >= minimum ({min_count})"
                )
            return (None, min_count, max_count)
        raise ValueError(
            f"Count tuple must have 1 or 2 elements, got {len(spec)}"
        )
    raise ValueError(f"Invalid count spec type: {type(spec).__name__}")


@dataclass(frozen=True, slots=True)
class InputPortSpec:
    """Specification for a single port's type and count constraints.

    Attributes:
        accepts: The payload type name(s) this port accepts. Can be a single
            string (e.g., "array") or a tuple of strings (e.g., ("array", "color")).
            Type names are resolved via the payload registry at validation time.
        count: Count specification:
            - int: Fixed count (e.g., 512)
            - (min,): Variable with minimum only
            - (min, max): Variable with bounds
            - None: Variable with no bounds (default)
        description: Optional human-readable description of the port.
        values_multiple_of: The total number of values supplied (rows × components)
            must be a multiple of this; None for no such rule. Checked when the graph
            is built where every source's rows and width are known (a ``ConnectError``
            with ``MULTIPLE``); otherwise the node checks it on each frame.

    Examples:
        >>> from rasl.color import ColorPayload
        >>> from rasl.signal import MatrixPayload
        >>> InputPortSpec(MatrixPayload, count=512)  # Fixed 512 count
        >>> InputPortSpec(MatrixPayload, count=(0,))  # Variable, no minimum
        >>> InputPortSpec(MatrixPayload, count=(3,))  # Variable, at least 3
        >>> InputPortSpec((MatrixPayload, ColorPayload))  # Accepts either type
        >>> InputPortSpec(MatrixPayload)  # Variable count, no bounds (default)
    """

    accepts: AcceptsSpec
    count: CountSpec = None
    description: str = ""
    values_multiple_of: int | None = None

    def __post_init__(self) -> None:
        _parse_count_spec(self.count)
        if self.values_multiple_of is not None and self.values_multiple_of < 1:
            raise ValueError(f"values_multiple_of must be at least 1, got {self.values_multiple_of}")

    @property
    def accepted_types(self) -> tuple[str, ...]:
        """Return tuple of accepted payload type names.
        
        Handles both string-based accepts (new style) and class-based
        accepts (legacy) for backwards compatibility.
        """
        if isinstance(self.accepts, str):
            return (self.accepts,)
        if isinstance(self.accepts, tuple):
            # Could be tuple of strings or tuple of classes
            if self.accepts and isinstance(self.accepts[0], str):
                return self.accepts
            # Tuple of classes - convert to domain names
            return tuple(
                getattr(cls, "domain", cls.__name__) for cls in self.accepts
            )
        # Single class - convert to domain name
        return (getattr(self.accepts, "domain", self.accepts.__name__),)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve accepted type names to actual payload classes.

        Returns:
            Tuple of payload classes for the accepted type names.
            For class-based accepts (legacy), returns the classes directly.
            Unknown type names are skipped here; ``unknown_type_names`` lists
            them, and ``GraphBuilder.connect`` refuses a port that has any.
        """
        # Handle class-based accepts (legacy)
        if not isinstance(self.accepts, str):
            if isinstance(self.accepts, tuple):
                if self.accepts and not isinstance(self.accepts[0], str):
                    return self.accepts  # Already classes
            elif not isinstance(self.accepts, str):
                return (self.accepts,)  # Single class

        # String-based accepts - resolve via registry
        from rasl.signal import get_payload_type

        types: list[Type] = []
        for name in self.accepted_types:
            payload_cls = get_payload_type(name)
            if payload_cls is not None:
                types.append(payload_cls)
        return tuple(types)

    def unknown_type_names(self) -> tuple[str, ...]:
        """The accepted type names that no payload is registered under.

        A port that names a type nothing registered would accept any payload,
        so the graph refuses to connect it. Class-based specs have none.
        """
        if isinstance(self.accepts, str) or (
            isinstance(self.accepts, tuple) and self.accepts and isinstance(self.accepts[0], str)
        ):
            from rasl.signal import get_payload_type

            return tuple(name for name in self.accepted_types if get_payload_type(name) is None)
        return ()

    @property
    def is_variable(self) -> bool:
        """True if the element count is not fixed (``count`` is None or a tuple)."""
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed is None

    @property
    def fixed_count(self) -> Optional[int]:
        """The exact element count, or None for a variable-length port."""
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed

    @property
    def min_count(self) -> int:
        """Fewest elements allowed: the fixed count, else the minimum (0 if none was given)."""
        fixed, min_count, _ = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return min_count if min_count is not None else 0

    @property
    def max_count(self) -> Optional[int]:
        """Most elements allowed: the fixed count, else the maximum; None if unbounded."""
        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return max_count

    def validate_index(self, index: int) -> bool:
        """Check if an index is valid for this port.

        Args:
            index: 0-based channel index to validate.

        Returns:
            True if the index is valid, False otherwise.
        """
        if index < 0:
            return False

        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return index < fixed
        if max_count is not None:
            return index < max_count
        # Variable with no max: any non-negative index is valid
        return True

    def validate_range(self, start: int, end: int) -> bool:
        """Check if a range [start, end) is valid for this port."""
        if start < 0 or end < start:
            return False
        if end == start:
            return True
        return self.validate_index(end - 1)

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts the given payload type."""
        resolved_types = self.resolve_payload_types()
        if not resolved_types:
            return True

        for accept_type in resolved_types:
            if hasattr(accept_type, "is_compatible_with"):
                if accept_type.is_compatible_with(payload_type):
                    return True
            elif issubclass(payload_type, accept_type):
                return True

        return False

    def coercion_target(self, payload_type: Type) -> Type | None:
        """The type this port retypes ``payload_type`` as, or None when it does not.

        A port that does not accept ``payload_type`` as it is takes it by coercion when
        exactly one of the types it accepts is a more specific type that coerces from
        it (``FramePayload.coerces_from``). With none, or with two (which one is meant
        is not known), it does not.
        """
        candidates = [
            accepted
            for accepted in self.resolve_payload_types()
            if hasattr(accepted, "coerces_from") and accepted.coerces_from(payload_type)
        ]
        return candidates[0] if len(candidates) == 1 else None


ProducesSpec = Union[str, Type]


@dataclass(frozen=True, slots=True)
class OutputPortSpec:
    """Specification for an output port: the one payload type it produces, and its count.

    Attributes:
        produces: The payload class or registered type name. Exactly one: a tuple raises
            ValueError.
        count: Count specification, as for ``InputPortSpec.count``.
        description: Optional human-readable description of the port.
        same_as: The name of one of the node's input ports, for an output that passes on
            the payload type it receives there (a filter that keeps colors colors). When
            the graph is built, the output is typed as whatever feeds that input; when
            nothing does, or its sources disagree, as ``produces``. None for an output
            that always emits ``produces``.
        components: Columns per element the output always emits, when its type does
            not fix them (a plain matrix of known width); None when unknown until it
            runs. A color type's own ``components`` needs no declaration here.
    """

    produces: ProducesSpec
    count: CountSpec = None
    description: str = ""
    same_as: str | None = None
    components: int | None = None

    def __post_init__(self) -> None:
        _parse_count_spec(self.count)
        if isinstance(self.produces, tuple):
            raise ValueError("OutputPortSpec.produces must be a single type")

    @property
    def type_name(self) -> str:
        """Registered name of the produced payload type.

        The string as given, or for a class its ``domain`` (its ``__name__`` if it has none).
        """
        if isinstance(self.produces, str):
            return self.produces
        return getattr(self.produces, "domain", self.produces.__name__)

    @property
    def known_components(self) -> int | None:
        """Columns per element, when known before the graph runs: declared, or the type's."""
        if self.components is not None:
            return self.components
        resolved = self.resolve_payload_types()
        components = getattr(resolved[0], "components", None) if resolved else None
        return components if isinstance(components, int) else None

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve the produced type to its payload class.

        Returns:
            A one-element tuple, or an empty tuple if the type name is not registered.
        """
        if not isinstance(self.produces, str):
            return (self.produces,)

        from rasl.signal import get_payload_type

        payload_cls = get_payload_type(self.produces)
        if payload_cls is None:
            return ()
        return (payload_cls,)

    def unknown_type_names(self) -> tuple[str, ...]:
        """The produced type name, if no payload is registered under it."""
        if isinstance(self.produces, str):
            from rasl.signal import get_payload_type

            if get_payload_type(self.produces) is None:
                return (self.produces,)
        return ()

    @property
    def is_variable(self) -> bool:
        """True if the element count is not fixed (``count`` is None or a tuple)."""
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed is None

    @property
    def fixed_count(self) -> Optional[int]:
        """The exact element count, or None for a variable-length port."""
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed

    @property
    def min_count(self) -> int:
        """Fewest elements allowed: the fixed count, else the minimum (0 if none was given)."""
        fixed, min_count, _ = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return min_count if min_count is not None else 0

    @property
    def max_count(self) -> Optional[int]:
        """Most elements allowed: the fixed count, else the maximum; None if unbounded."""
        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return max_count

    def validate_index(self, index: int) -> bool:
        """Check if a 0-based element index is within the port's count.

        A port with no fixed count and no maximum takes any non-negative index.
        """
        if index < 0:
            return False
        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return index < fixed
        if max_count is not None:
            return index < max_count
        return True

    def validate_range(self, start: int, end: int) -> bool:
        """Check if the range [start, end) is valid for this port.

        An empty range is valid for any non-negative ``start``.
        """
        if start < 0 or end < start:
            return False
        if end == start:
            return True
        return self.validate_index(end - 1)

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if a payload of the given type may be written to this port.

        Decided by the produced class's ``is_compatible_with`` when it has one, else by
        ``issubclass``. Returns True for every type when the produced type name is not
        registered.
        """
        resolved_types = self.resolve_payload_types()
        if not resolved_types:
            return True

        accept_type = resolved_types[0]
        if hasattr(accept_type, "is_compatible_with"):
            return accept_type.is_compatible_with(payload_type)
        return issubclass(payload_type, accept_type)
