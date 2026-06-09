import unittest

from tool_m import ToolCallParser, ToolCallPolicy, ToolCatalog
from tool_m.tool_call_parser import ToolCallParseError


class ToolCallingTests(unittest.TestCase):
    def test_catalog_serializes_declarative_metadata(self):
        catalog = ToolCatalog(
            [
                {
                    "name": "workspace_search",
                    "display_name": "workspace search",
                    "description": "Searches files.",
                    "parameters": {"query": {"type": "string", "required": True}},
                    "capabilities": ["find project files"],
                    "use_when": ["Need local project evidence."],
                    "risk_level": "read_only",
                }
            ]
        )

        messages = catalog.build_messages([{"role": "user", "content": "Review this project."}])

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("workspace_search", messages[0]["content"])
        self.assertIn("find project files", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")

    def test_parser_accepts_json_with_surrounding_text_and_reason(self):
        parser = ToolCallParser()

        tool_call = parser.parse_text(
            'Use this:\n{"tool_call":{"name":"web_search","arguments":{"query":"horizone lite"},"reason":"Need current sources."}}'
        )

        self.assertEqual(tool_call.name, "web_search")
        self.assertEqual(tool_call.arguments["query"], "horizone lite")
        self.assertEqual(tool_call.reason, "Need current sources.")

    def test_parser_accepts_no_tool_decision(self):
        decision = ToolCallParser().parse_decision_text(
            '{"tool_decision":{"needs_tool":false,"reason":"Creative writing needs no tool."}}'
        )

        self.assertFalse(decision.needs_tool)
        self.assertIsNone(decision.tool_call)
        self.assertEqual(decision.reason, "Creative writing needs no tool.")

    def test_parser_rejects_ambiguous_arguments(self):
        parser = ToolCallParser()

        with self.assertRaises(ToolCallParseError):
            parser.parse_text('{"tool_call":{"name":"web_search","arguments":"horizone lite"}}')

    def test_policy_blocks_high_risk_tools_without_confirmation(self):
        policy = ToolCallPolicy(auto_execute_risks={"read_only"})
        tool_call = ToolCallParser().parse_text(
            '{"tool_call":{"name":"workspace_run_command","arguments":{"command":"pytest"}}}'
        )

        decision = policy.evaluate(
            {"name": "workspace_run_command", "risk_level": "runs_command"},
            tool_call,
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["status"], "confirmation_required")

    def test_policy_allows_confirmed_high_risk_tools(self):
        policy = ToolCallPolicy(auto_execute_risks={"read_only"})
        tool_call = ToolCallParser().parse_text(
            '{"tool_call":{"name":"workspace_run_command","arguments":{"command":"pytest"}}}'
        )

        decision = policy.evaluate(
            {"name": "workspace_run_command", "risk_level": "runs_command"},
            tool_call,
            context={
                "confirmed_tool_calls": [
                    {
                        "name": "workspace_run_command",
                        "arguments": {"command": "pytest"},
                    }
                ]
            },
        )

        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["status"], "confirmed")

    def test_policy_rejects_confirmation_with_different_arguments(self):
        policy = ToolCallPolicy(auto_execute_risks={"read_only"})
        tool_call = ToolCallParser().parse_text(
            '{"tool_call":{"name":"workspace_run_command","arguments":{"command":"pytest"}}}'
        )

        decision = policy.evaluate(
            {"name": "workspace_run_command", "risk_level": "runs_command"},
            tool_call,
            context={
                "confirmed_tool_calls": [
                    {
                        "name": "workspace_run_command",
                        "arguments": {"command": "rm -rf ."},
                    }
                ]
            },
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["status"], "confirmation_required")


if __name__ == "__main__":
    unittest.main()
