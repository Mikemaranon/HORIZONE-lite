import inspect
import re


TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


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

    run_callable = getattr(module, "run", None)
    if not callable(run_callable):
        raise ToolContractError("Tool modules must define a callable run(arguments) function.")

    _validate_run_signature(run_callable)

    return {
        "name": normalized_name,
        "display_name": normalized_display_name,
        "description": tool_description.strip(),
        "parameters": tool_parameters,
        "filename": file_path.name,
        "module_path": str(file_path),
        "is_builtin": bool(is_builtin),
        "runner": run_callable,
    }


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
