import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError


class ToolExecutionError(RuntimeError):
    pass


class ToolExecutor:
    def __init__(self, db_manager=None, *, timeout_seconds=10):
        self.db = db_manager
        self.timeout_seconds = timeout_seconds

    def execute(self, runtime_tool, arguments):
        tool_name = runtime_tool["name"]
        normalized_arguments = arguments if isinstance(arguments, dict) else {}
        started_at = time.perf_counter()

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(runtime_tool["runner"], normalized_arguments)
                result = future.result(timeout=self.timeout_seconds)
        except TimeoutError as error:
            message = f"Tool '{tool_name}' timed out."
            self._log_execution(
                tool_name,
                normalized_arguments,
                {"ok": False, "error": message},
                started_at,
            )
            raise ToolExecutionError(message) from error
        except Exception as error:
            message = str(error) or f"Tool '{tool_name}' failed unexpectedly."
            self._log_execution(
                tool_name,
                normalized_arguments,
                {"ok": False, "error": message},
                started_at,
            )
            raise ToolExecutionError(message) from error

        if not isinstance(result, dict):
            message = f"Tool '{tool_name}' must return a dictionary."
            self._log_execution(
                tool_name,
                normalized_arguments,
                {"ok": False, "error": message},
                started_at,
            )
            raise ToolExecutionError(message)

        self._log_execution(
            tool_name,
            normalized_arguments,
            {"ok": True, "result": result},
            started_at,
        )
        return result

    def _log_execution(self, tool_name, arguments, result_payload, started_at):
        if not self.db:
            return

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        self.db.agent_logs.create(
            action="tool_execution",
            details=json.dumps(
                {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result_payload,
                    "duration_ms": duration_ms,
                },
                ensure_ascii=False,
            ),
        )
