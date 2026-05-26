import inspect
import re


TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TOOL_RISK_LEVELS = {
    "read_only",
    "external_network",
    "writes_workspace",
    "runs_command",
    "destructive",
}


class ToolContractError(ValueError):
    pass


def validate_tool_module(module, file_path, *, is_builtin=False):
    tool_name = getattr(module, "TOOL_NAME", "")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ToolContractError("TOOL_NAME must be a non-empty string.")

    normalized_name = tool_name.strip()
    if not TOOL_NAME_PATTERN.match(normalized_name):
        raise ToolContractError(
            "TOOL_NAME must use lowercase letters, numbers, and underscores only."
        )

    tool_display_name = getattr(module, "TOOL_DISPLAY_NAME", "")
    if tool_display_name is None:
        tool_display_name = ""
    if not isinstance(tool_display_name, str):
        raise ToolContractError("TOOL_DISPLAY_NAME must be a string when provided.")
    normalized_display_name = tool_display_name.strip() or normalized_name.replace("_", " ")

    tool_description = getattr(module, "TOOL_DESCRIPTION", "")
    if not isinstance(tool_description, str) or not tool_description.strip():
        raise ToolContractError("TOOL_DESCRIPTION must be a non-empty string.")

    tool_parameters = getattr(module, "TOOL_PARAMETERS", {})
    if not isinstance(tool_parameters, dict):
        raise ToolContractError("TOOL_PARAMETERS must be a dictionary.")

    tool_capabilities = _normalize_string_list(
        getattr(module, "TOOL_CAPABILITIES", []),
        "TOOL_CAPABILITIES",
    )
    tool_use_when = _normalize_string_list(
        getattr(module, "TOOL_USE_WHEN", []),
        "TOOL_USE_WHEN",
    )
    tool_risk_level = getattr(module, "TOOL_RISK_LEVEL", "read_only")
    if tool_risk_level is None:
        tool_risk_level = "read_only"
    if not isinstance(tool_risk_level, str):
        raise ToolContractError("TOOL_RISK_LEVEL must be a string when provided.")
    normalized_risk_level = tool_risk_level.strip() or "read_only"
    if normalized_risk_level not in TOOL_RISK_LEVELS:
        raise ToolContractError(
            "TOOL_RISK_LEVEL must be one of: "
            + ", ".join(sorted(TOOL_RISK_LEVELS))
        )

    run_callable = getattr(module, "run", None)
    if not callable(run_callable):
        raise ToolContractError("Tool modules must define a callable run(arguments) function.")

    _validate_run_signature(run_callable)

    return {
        "name": normalized_name,
        "display_name": normalized_display_name,
        "description": tool_description.strip(),
        "parameters": tool_parameters,
        "capabilities": tool_capabilities,
        "use_when": tool_use_when,
        "risk_level": normalized_risk_level,
        "filename": file_path.name,
        "module_path": str(file_path),
        "is_builtin": bool(is_builtin),
        "runner": run_callable,
    }


def _normalize_string_list(raw_value, field_name):
    if raw_value is None:
        return []

    if not isinstance(raw_value, (list, tuple)):
        raise ToolContractError(f"{field_name} must be a list of strings when provided.")

    normalized_items = []
    for item in raw_value:
        if not isinstance(item, str):
            raise ToolContractError(f"{field_name} must contain only strings.")
        normalized = item.strip()
        if normalized:
            normalized_items.append(normalized)

    return normalized_items


def _validate_run_signature(run_callable):
    signature = inspect.signature(run_callable)
    positional_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if len(positional_parameters) != 1:
        raise ToolContractError("run(arguments) must accept exactly one positional argument.")
