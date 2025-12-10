"""ConfigDispatch - Routes directives to handlers and parses fields.

This module provides:
- @config decorator for registering keyword handlers
- ConfigDispatch helper for processing directive blocks
"""

from __future__ import annotations

from typing import Any, Callable, Type, TypeVar, get_origin, get_args

from pydantic import BaseModel

from .directive import Directive

T = TypeVar("T", bound=BaseModel)


class ConfigError(Exception):
    """Configuration parsing error with source location.

    Attributes:
        message: Description of the error.
        line: Line number where error occurred (1-indexed).
        column: Column number where error occurred (0-indexed).
        source_line: The source line text for display.
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int | None = None,
        source_line: str | None = None,
    ) -> None:
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line
        super().__init__(self._format())

    def _format(self) -> str:
        """Format error with source location and caret indicator."""
        parts = []
        if self.line:
            parts.append(f"Line {self.line}: {self.message}")
        else:
            parts.append(self.message)
        
        # Show source line with caret if available
        if self.source_line is not None:
            parts.append(f"\n  {self.source_line}")
            if self.column is not None:
                parts.append(f"\n  {' ' * self.column}^")
        
        return "".join(parts)
    
    def with_source(self, source_text: str) -> "ConfigError":
        """Return new ConfigError with source line extracted from full text.
        
        Args:
            source_text: Full source file content.
            
        Returns:
            New ConfigError with source_line populated.
        """
        if self.line > 0:
            lines = source_text.splitlines()
            if 0 < self.line <= len(lines):
                return ConfigError(
                    self.message,
                    line=self.line,
                    column=self.column,
                    source_line=lines[self.line - 1],
                )
        return self


def config(keyword: str, model: Type[BaseModel] | None = None):
    """Decorator to register a method as handler for a keyword.

    The decorated method will be called for each directive matching
    the keyword. If a model is specified, the directive's block will
    be pre-parsed into that model and available via directive.config.

    Args:
        keyword: The directive keyword this method handles.
        model: Optional Pydantic model to pre-parse the block into.

    Returns:
        Decorator function.

    Example:
        @config("connect", model=ConnectOptions)
        def handle_connect(self, directive: Directive) -> list[ConnectionSpec]:
            # directive.config is pre-parsed ConnectOptions
            return expand_connections(directive)
    """

    def decorator(method: Callable) -> Callable:
        method._config_keyword = keyword  # type: ignore
        method._config_model = model  # type: ignore
        return method

    return decorator


class ConfigDispatch:
    """Routes directives to @config handlers and parses Pydantic fields.

    This helper handles the mechanics of:
    - Finding @config decorated methods on the owner
    - Routing directives to appropriate handlers
    - Parsing simple fields into Pydantic models
    - Pre-parsing nested models for handlers

    Example:
        class MyNode:
            def __init__(self):
                self.dispatch = ConfigDispatch(self)

            @config("custom")
            def handle_custom(self, directive: Directive) -> Something:
                return Something(directive.args[0])

        # Later:
        config, results = node.dispatch.process(directive, MyNode.Config)
        customs = results.get("custom", [])
    """

    def __init__(self, owner: object) -> None:
        """Initialize dispatch for an owner object.

        Args:
            owner: Object with @config decorated methods.
        """
        self.owner = owner
        self._handlers = self._collect_handlers()

    def _collect_handlers(self) -> dict[str, tuple[Callable, Type[BaseModel] | None]]:
        """Find all @config decorated methods on owner."""
        handlers: dict[str, tuple[Callable, Type[BaseModel] | None]] = {}

        for name in dir(self.owner):
            try:
                method = getattr(self.owner, name, None)
            except Exception:
                continue

            if callable(method) and hasattr(method, "_config_keyword"):
                keyword = method._config_keyword
                model = getattr(method, "_config_model", None)
                handlers[keyword] = (method, model)

        return handlers

    def process(
        self,
        directive: Directive,
        config_class: Type[T],
    ) -> tuple[T, dict[str, list[Any]]]:
        """Process a directive's block into config and handler results.

        Iterates through child directives:
        - Directives matching @config handlers are routed to those handlers
        - Directives matching Pydantic fields are parsed into the model
        - Unknown directives raise ConfigError

        Args:
            directive: Parent directive whose block to process.
            config_class: Pydantic model class for simple fields.

        Returns:
            Tuple of (validated config, handler results dict).
            Handler results are keyed by keyword, values are lists.

        Raises:
            ConfigError: If unknown keyword encountered.
        """
        field_data = self._extract_arg_fields(directive, config_class)
        handler_results: dict[str, list[Any]] = {}

        for child in directive.block:
            keyword = child.keyword

            # Check for @config handler
            if keyword in self._handlers:
                method, model = self._handlers[keyword]

                # Pre-parse model if specified
                if model is not None:
                    parsed_config = self.parse_model(child, model)
                    # Attach to directive (bypass frozen)
                    object.__setattr__(child, "_config", parsed_config)

                result = method(child)
                if result is not None:
                    if isinstance(result, list):
                        handler_results.setdefault(keyword, []).extend(result)
                    else:
                        handler_results.setdefault(keyword, []).append(result)

            # Check for Pydantic field
            elif keyword in config_class.model_fields:
                field_info = config_class.model_fields[keyword]
                value = self._parse_field(child, field_info)

                if self._is_list_field(field_info):
                    field_data.setdefault(keyword, []).append(value)
                else:
                    field_data[keyword] = value

            else:
                raise ConfigError(f"Unknown keyword '{keyword}'", line=child.line)

        config = config_class(**field_data)
        return config, handler_results

    def parse_model(
        self,
        directive: Directive,
        model: Type[T],
    ) -> T:
        """Parse directive into Pydantic model (fields only, no handlers).

        This is useful for parsing nested blocks that don't need
        custom handler logic.

        Args:
            directive: Directive to parse.
            model: Pydantic model class.

        Returns:
            Validated model instance.
        """
        data = self._extract_arg_fields(directive, model)

        for child in directive.block:
            if child.keyword in model.model_fields:
                field_info = model.model_fields[child.keyword]
                data[child.keyword] = self._parse_field(child, field_info)

        return model(**data)

    def _extract_arg_fields(
        self,
        directive: Directive,
        model: Type[BaseModel],
    ) -> dict[str, Any]:
        """Map positional args to fields via arg_fields class attribute.

        If the model has an `arg_fields` class attribute (list of field names),
        positional args are mapped to those fields in order.

        Args:
            directive: Directive with args to extract.
            model: Model class that may have arg_fields.

        Returns:
            Dict of field name -> coerced value.
        """
        data: dict[str, Any] = {}
        arg_fields: list[str] = getattr(model, "arg_fields", [])

        for i, field_name in enumerate(arg_fields):
            if i < len(directive.args):
                field_info = model.model_fields.get(field_name)
                if field_info:
                    data[field_name] = self._coerce(
                        directive.args[i],
                        field_info.annotation,
                    )

        return data

    def _parse_field(self, directive: Directive, field_info: Any) -> Any:
        """Parse single field from directive.

        Handles:
        - Nested Pydantic models (recurses)
        - Primitive types (coerces from first arg)

        Args:
            directive: Directive to parse.
            field_info: Pydantic FieldInfo for the target field.

        Returns:
            Parsed and coerced value.
        """
        inner_type = self._get_inner_type(field_info.annotation)

        # Nested model → recurse
        if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
            return self.parse_model(directive, inner_type)

        # Primitive → coerce first arg
        if directive.args:
            return self._coerce(directive.args[0], inner_type)

        return None

    def _is_list_field(self, field_info: Any) -> bool:
        """Check if field is a list type."""
        origin = get_origin(field_info.annotation)
        return origin is list

    def _get_inner_type(self, annotation: Any) -> type:
        """Get inner type for list[T] or just T."""
        origin = get_origin(annotation)
        if origin is list:
            args = get_args(annotation)
            return args[0] if args else str
        return annotation

    def _coerce(self, value: str, target_type: type) -> Any:
        """Coerce string value to target type.

        Args:
            value: String value from config.
            target_type: Target Python type.

        Returns:
            Coerced value.
        """
        # Handle Optional types
        origin = get_origin(target_type)
        if origin is type(None):
            return None

        # Unwrap Optional[T] to T
        if hasattr(target_type, "__origin__"):
            args = get_args(target_type)
            if type(None) in args:
                # It's Optional[T], get the non-None type
                for arg in args:
                    if arg is not type(None):
                        target_type = arg
                        break

        if target_type is str:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "yes", "1", "on")

        return value
