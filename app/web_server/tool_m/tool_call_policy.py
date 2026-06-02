class ToolCallPolicy:
    DEFAULT_AUTO_EXECUTE_RISKS = {
        "read_only",
        "external_network",
    }

    def __init__(self, auto_execute_risks=None):
        self.auto_execute_risks = set(auto_execute_risks or self.DEFAULT_AUTO_EXECUTE_RISKS)

    def evaluate(self, tool, tool_call, context=None):
        context = context or {}
        risk_level = str((tool or {}).get("risk_level") or "read_only").strip()

        if self._is_confirmed_call(tool_call, context):
            return {
                "allowed": True,
                "status": "confirmed",
                "risk_level": risk_level,
                "reason": "The user confirmed this exact tool call.",
            }

        if risk_level in self.auto_execute_risks:
            return {
                "allowed": True,
                "status": "allowed",
                "risk_level": risk_level,
                "reason": "Tool risk is allowed for automatic execution.",
            }

        return {
            "allowed": False,
            "status": "confirmation_required",
            "risk_level": risk_level,
            "reason": "This tool requires explicit confirmation before execution.",
        }

    def _is_confirmed_call(self, tool_call, context):
        confirmed_calls = list(context.get("confirmed_tool_calls") or [])
        confirmed_tool_call = context.get("confirmed_tool_call")
        if confirmed_tool_call:
            confirmed_calls.append(confirmed_tool_call)

        for confirmed_call in confirmed_calls:
            if not isinstance(confirmed_call, dict):
                continue

            confirmed_name = str(
                confirmed_call.get("name") or confirmed_call.get("tool_name") or ""
            ).strip()
            confirmed_arguments = confirmed_call.get("arguments")
            if confirmed_name == tool_call.name and confirmed_arguments == tool_call.arguments:
                return True

        return False
