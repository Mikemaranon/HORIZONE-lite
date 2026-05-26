class ToolCallPolicy:
    DEFAULT_AUTO_EXECUTE_RISKS = {
        "read_only",
        "external_network",
        "writes_workspace",
    }

    def __init__(self, auto_execute_risks=None):
        self.auto_execute_risks = set(auto_execute_risks or self.DEFAULT_AUTO_EXECUTE_RISKS)

    def evaluate(self, tool, tool_call, context=None):
        context = context or {}
        risk_level = str((tool or {}).get("risk_level") or "read_only").strip()
        confirmed_tools = set(context.get("confirmed_tools") or [])

        if risk_level in self.auto_execute_risks or tool_call.name in confirmed_tools:
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
