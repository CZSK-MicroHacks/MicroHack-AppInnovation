"""Name the first missing or malformed field in a modernization contract.

JSON Schema reports an unordered *set* of violations. A facilitator rehearsing
the golden handoff procedure needs the opposite: the single field to fix next.
This module walks the contract schema in the order it declares its own required
fields, so the answer is stable and is the first defect in document order.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

MAX_MESSAGE_LENGTH = 200


def _resolve_schema(
    schema: dict[str, Any], root_schema: dict[str, Any]
) -> dict[str, Any]:
    """Follow local ``#/$defs`` references until a concrete subschema remains."""
    seen: set[str] = set()
    while isinstance(schema, dict) and "$ref" in schema:
        pointer = schema["$ref"]
        if pointer in seen:
            raise ValueError(f"contract schema has a cyclic reference: {pointer}")
        seen.add(pointer)
        schema = root_schema.get("$defs", {}).get(pointer.rsplit("/", 1)[-1], {})
    return schema


def _sub_validator(
    schema: dict[str, Any], root_schema: dict[str, Any]
) -> Draft202012Validator:
    """Build a validator for one subschema that can still resolve ``#/$defs``."""
    document = dict(schema)
    definitions = root_schema.get("$defs")
    if definitions is not None:
        document.setdefault("$defs", definitions)
    return Draft202012Validator(document, format_checker=FormatChecker())


def _closest_near_miss(
    error: JsonSchemaValidationError,
) -> JsonSchemaValidationError:
    """Descend through ``anyOf``/``oneOf`` branches to the closest near miss.

    A composed schema reports the entire instance as invalid, which is a wall of
    text. The branch with the fewest sub-errors is the one the facilitator meant,
    so its deepest sub-error names the field actually worth reporting.
    """
    while error.context:
        branches: dict[Any, list[JsonSchemaValidationError]] = {}
        for sub_error in error.context:
            branches.setdefault(next(iter(sub_error.schema_path), 0), []).append(
                sub_error
            )
        branch = min(branches.values(), key=len)
        error = max(branch, key=lambda sub_error: len(sub_error.absolute_path))
    return error


def _node_defect(
    validator: Draft202012Validator, instance: Any, pointer: str
) -> str | None:
    """Return the shallowest defect at one node, or ``None`` when it is clean."""
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: (
            len(error.absolute_path),
            [str(part) for part in error.absolute_path],
            error.validator or "",
        ),
    )
    if not errors:
        return None
    error = _closest_near_miss(errors[0])
    where = pointer + "".join(f"/{part}" for part in error.absolute_path)
    message = " ".join(error.message.split())
    if len(message) > MAX_MESSAGE_LENGTH:
        message = f"{message[:MAX_MESSAGE_LENGTH]}..."
    return f"{where or '(document root)'} is malformed: {message}"


def first_contract_defect(
    instance: Any,
    root_schema: dict[str, Any],
    schema: dict[str, Any] | None = None,
    pointer: str = "",
) -> str | None:
    """Return the first missing or malformed contract field in document order.

    Args:
        instance: Parsed contract fragment to inspect.
        root_schema: Whole contract schema, used to resolve ``#/$defs``.
        schema: Subschema governing ``instance``; defaults to ``root_schema``.
        pointer: JSON pointer of ``instance`` within the contract.

    Returns:
        One human-readable defect description naming a single JSON pointer, or
        ``None`` when the fragment is complete and well formed.
    """
    resolved = _resolve_schema(root_schema if schema is None else schema, root_schema)
    if resolved.get("type") == "object" and isinstance(instance, dict):
        properties = resolved.get("properties", {})
        for name in resolved.get("required", ()):
            child_pointer = f"{pointer}/{name}"
            if name not in instance:
                return f"{child_pointer} is missing"
            child_schema = properties.get(name)
            if child_schema is None:
                continue
            defect = first_contract_defect(
                instance[name], root_schema, child_schema, child_pointer
            )
            if defect is not None:
                return defect
    return _node_defect(_sub_validator(resolved, root_schema), instance, pointer)
