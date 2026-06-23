from .tool_call_parser import ToolCallParseError, ToolCallRequest
from .tool_execution_trace import ToolExecutionTrace


class ToolCallOrchestrator:
    def __init__(
        self,
        *,
        model_manager,
        tool_executor,
        tool_call_parser,
        tool_call_policy,
        execution_trace=None,
        max_tool_round_trips=3,
    ):
        self.model_manager = model_manager
        self.tool_executor = tool_executor
        self.tool_call_parser = tool_call_parser
        self.tool_call_policy = tool_call_policy
        self.execution_trace = execution_trace or ToolExecutionTrace()
        self.max_tool_round_trips = max_tool_round_trips

    def chat(
        self,
        provider_name,
        messages,
        model,
        settings,
        *,
        tool_catalog,
        should_stop=None,
        tool_context=None,
    ):
        forced_state = self._build_forced_chain_state(tool_context)
        if forced_state:
            return self._chat_forced_chain(
                provider_name,
                messages,
                model,
                settings,
                tool_catalog=tool_catalog,
                should_stop=should_stop,
                tool_context=tool_context,
                forced_state=forced_state,
            )

        planning_messages = tool_catalog.build_planning_messages(messages)
        final_messages = tool_catalog.build_answer_messages(messages)
        tool_events = []
        response = None
        confirmed_tool_call = self._build_confirmed_tool_call(tool_context)
        if confirmed_tool_call:
            tool_event = self._execute_tool_call(
                confirmed_tool_call,
                tool_catalog=tool_catalog,
                tool_context=tool_context,
            )
            tool_events.append(tool_event)
            final_messages.extend(
                self.execution_trace.build_exchange_messages(
                    confirmed_tool_call,
                    tool_event,
                )
            )
            final_response = self.model_manager.chat(
                provider_name,
                final_messages,
                model,
                settings or {},
            )
            return self._finalize_response(
                final_response,
                tool_events,
                provider_name=provider_name,
                model=model,
            )

        for _ in range(self.max_tool_round_trips + 1):
            if self._is_stop_requested(should_stop):
                return self._build_cancelled_response(provider_name, model, tool_events)

            response = self.model_manager.chat(
                provider_name,
                planning_messages,
                model,
                settings or {},
            )
            try:
                decision = self._parse_tool_decision(response)
            except ToolCallParseError as error:
                self._append_decision_error_message(planning_messages, error, response=response)
                continue

            if not decision:
                if tool_events:
                    return self._finalize_response(
                        response,
                        tool_events,
                        provider_name=provider_name,
                        model=model,
                    )

                self._append_decision_error_message(
                    planning_messages,
                    "Planning response must be a tool_call or tool_decision JSON object.",
                    response=response,
                )
                continue

            if not decision.needs_tool:
                final_response = self.model_manager.chat(
                    provider_name,
                    final_messages,
                    model,
                    settings or {},
                )
                return self._finalize_response(
                    final_response,
                    tool_events,
                    provider_name=provider_name,
                    model=model,
                )

            tool_call = decision.tool_call
            tool_event = self._execute_tool_call(
                tool_call,
                tool_catalog=tool_catalog,
                tool_context=tool_context,
            )
            tool_events.append(tool_event)
            if self._requires_confirmation(tool_event):
                return self._build_confirmation_response(
                    provider_name,
                    model,
                    tool_events,
                )
            exchange_messages = self.execution_trace.build_exchange_messages(tool_call, tool_event)
            planning_messages.extend(exchange_messages)
            final_messages.extend(exchange_messages)

        return self._handle_tool_limit(
            response,
            provider_name,
            final_messages,
            model,
            settings or {},
            tool_events,
        )

    def stream_chat(
        self,
        provider_name,
        messages,
        model,
        settings,
        *,
        tool_catalog,
        should_stop=None,
        tool_context=None,
    ):
        forced_state = self._build_forced_chain_state(tool_context)
        if forced_state:
            yield from self._stream_forced_chain(
                provider_name,
                messages,
                model,
                settings,
                tool_catalog=tool_catalog,
                should_stop=should_stop,
                tool_context=tool_context,
                forced_state=forced_state,
            )
            return

        planning_messages = tool_catalog.build_planning_messages(messages)
        final_messages = tool_catalog.build_answer_messages(messages)
        tool_events = []
        response = None
        confirmed_tool_call = self._build_confirmed_tool_call(tool_context)
        if confirmed_tool_call:
            yield self._build_tool_start_stream_event(confirmed_tool_call, tool_catalog)
            tool_event = self._execute_tool_call(
                confirmed_tool_call,
                tool_catalog=tool_catalog,
                tool_context=tool_context,
            )
            tool_events.append(tool_event)
            final_messages.extend(
                self.execution_trace.build_exchange_messages(
                    confirmed_tool_call,
                    tool_event,
                )
            )
            yield self._build_tool_result_stream_event(tool_event)
            yield from self._stream_final_response(
                provider_name,
                final_messages,
                model,
                settings or {},
                tool_events,
                should_stop=should_stop,
            )
            return

        for _ in range(self.max_tool_round_trips + 1):
            if self._is_stop_requested(should_stop):
                yield {
                    "type": "response",
                    "response": self._build_cancelled_response(
                        provider_name,
                        model,
                        tool_events,
                    ),
                }
                return

            response = self.model_manager.chat(
                provider_name,
                planning_messages,
                model,
                settings or {},
            )
            try:
                decision = self._parse_tool_decision(response)
            except ToolCallParseError as error:
                self._append_decision_error_message(planning_messages, error, response=response)
                continue

            if not decision:
                if tool_events:
                    final_response = self._finalize_response(
                        response,
                        tool_events,
                        provider_name=provider_name,
                        model=model,
                    )
                    content = (final_response.get("message") or {}).get("content", "")
                    if content:
                        yield {
                            "type": "delta",
                            "delta": content,
                        }
                    yield {
                        "type": "response",
                        "response": final_response,
                    }
                    return

                self._append_decision_error_message(
                    planning_messages,
                    "Planning response must be a tool_call or tool_decision JSON object.",
                    response=response,
                )
                continue

            if not decision.needs_tool:
                yield from self._stream_final_response(
                    provider_name,
                    final_messages,
                    model,
                    settings or {},
                    tool_events,
                    should_stop=should_stop,
                )
                return

            tool_call = decision.tool_call
            yield self._build_tool_start_stream_event(tool_call, tool_catalog)
            tool_event = self._execute_tool_call(
                tool_call,
                tool_catalog=tool_catalog,
                tool_context=tool_context,
            )
            tool_events.append(tool_event)
            yield self._build_tool_result_stream_event(tool_event)
            if self._requires_confirmation(tool_event):
                yield {
                    "type": "response",
                    "response": self._build_confirmation_response(
                        provider_name,
                        model,
                        tool_events,
                    ),
                }
                return
            exchange_messages = self.execution_trace.build_exchange_messages(tool_call, tool_event)
            planning_messages.extend(exchange_messages)
            final_messages.extend(exchange_messages)

        self._append_user_instruction(
            final_messages,
            (
                "Tool limit reached. Do not request more tools. "
                "Answer the user with the information already available."
            ),
        )
        yield from self._stream_final_response(
            provider_name,
            final_messages,
            model,
            settings or {},
            tool_events,
            should_stop=should_stop,
        )

    def _chat_forced_chain(
        self,
        provider_name,
        messages,
        model,
        settings,
        *,
        tool_catalog,
        should_stop,
        tool_context,
        forced_state,
    ):
        final_messages, chain_messages = self._build_forced_chain_messages(
            messages,
            tool_catalog,
            forced_state["completed_events"],
        )
        tool_events = []
        for index in range(forced_state["current_index"], len(forced_state["directives"])):
            if self._is_stop_requested(should_stop):
                return self._build_cancelled_response(provider_name, model, tool_events)

            directive = forced_state["directives"][index]
            tool_call = self._resolve_forced_tool_call(
                provider_name,
                chain_messages,
                model,
                settings,
                directive,
                tool_catalog=tool_catalog,
                confirmed_tool_call=(
                    forced_state.get("confirmed_tool_call")
                    if index == forced_state["current_index"]
                    else None
                ),
            )
            tool_event = self._execute_tool_call(
                tool_call,
                tool_catalog=tool_catalog,
                tool_context=tool_context,
            )
            tool_events.append(tool_event)
            if self._requires_confirmation(tool_event):
                self._attach_forced_chain_state(
                    tool_event,
                    forced_state["directives"],
                    index,
                    [*forced_state["completed_events"], *tool_events[:-1]],
                )
                return self._build_confirmation_response(provider_name, model, tool_events)
            if not tool_event.get("ok"):
                return self._build_failed_tool_response(provider_name, model, tool_events)

            exchange_messages = self.execution_trace.build_exchange_messages(tool_call, tool_event)
            final_messages.extend(exchange_messages)
            chain_messages.extend(exchange_messages)

        final_response = self.model_manager.chat(
            provider_name,
            final_messages,
            model,
            settings or {},
        )
        return self._finalize_response(
            final_response,
            tool_events,
            provider_name=provider_name,
            model=model,
        )

    def _stream_forced_chain(
        self,
        provider_name,
        messages,
        model,
        settings,
        *,
        tool_catalog,
        should_stop,
        tool_context,
        forced_state,
    ):
        final_messages, chain_messages = self._build_forced_chain_messages(
            messages,
            tool_catalog,
            forced_state["completed_events"],
        )
        tool_events = []
        for index in range(forced_state["current_index"], len(forced_state["directives"])):
            if self._is_stop_requested(should_stop):
                yield {
                    "type": "response",
                    "response": self._build_cancelled_response(provider_name, model, tool_events),
                }
                return

            directive = forced_state["directives"][index]
            tool_call = self._resolve_forced_tool_call(
                provider_name,
                chain_messages,
                model,
                settings,
                directive,
                tool_catalog=tool_catalog,
                confirmed_tool_call=(
                    forced_state.get("confirmed_tool_call")
                    if index == forced_state["current_index"]
                    else None
                ),
            )
            yield self._build_tool_start_stream_event(tool_call, tool_catalog)
            tool_event = self._execute_tool_call(
                tool_call,
                tool_catalog=tool_catalog,
                tool_context=tool_context,
            )
            tool_events.append(tool_event)
            yield self._build_tool_result_stream_event(tool_event)
            if self._requires_confirmation(tool_event):
                self._attach_forced_chain_state(
                    tool_event,
                    forced_state["directives"],
                    index,
                    [*forced_state["completed_events"], *tool_events[:-1]],
                )
                yield {
                    "type": "response",
                    "response": self._build_confirmation_response(
                        provider_name,
                        model,
                        tool_events,
                    ),
                }
                return
            if not tool_event.get("ok"):
                failure_response = self._build_failed_tool_response(
                    provider_name,
                    model,
                    tool_events,
                )
                content = (failure_response.get("message") or {}).get("content", "")
                if content:
                    yield {"type": "delta", "delta": content}
                yield {"type": "response", "response": failure_response}
                return

            exchange_messages = self.execution_trace.build_exchange_messages(tool_call, tool_event)
            final_messages.extend(exchange_messages)
            chain_messages.extend(exchange_messages)

        yield from self._stream_final_response(
            provider_name,
            final_messages,
            model,
            settings or {},
            tool_events,
            should_stop=should_stop,
        )

    def _build_forced_chain_state(self, tool_context):
        context = tool_context or {}
        resume = context.get("forced_tool_resume")
        if isinstance(resume, dict) and resume.get("directives"):
            return {
                "directives": list(resume["directives"]),
                "current_index": int(resume.get("current_index") or 0),
                "completed_events": list(resume.get("completed_events") or []),
                "confirmed_tool_call": self._build_confirmed_tool_call(context),
            }

        directives = context.get("forced_tool_directives")
        if not directives:
            return None
        return {
            "directives": list(directives),
            "current_index": 0,
            "completed_events": [],
            "confirmed_tool_call": None,
        }

    def _build_forced_chain_messages(self, messages, tool_catalog, completed_events):
        final_messages = tool_catalog.build_answer_messages(messages)
        chain_messages = [*list(messages or [])]
        for tool_event in completed_events:
            tool_call = ToolCallRequest(
                name=str(tool_event.get("tool_name") or "").strip(),
                arguments=dict(tool_event.get("arguments") or {}),
                reason=str(tool_event.get("reason") or "").strip(),
            )
            exchange_messages = self.execution_trace.build_exchange_messages(tool_call, tool_event)
            final_messages.extend(exchange_messages)
            chain_messages.extend(exchange_messages)
        return final_messages, chain_messages

    def _resolve_forced_tool_call(
        self,
        provider_name,
        messages,
        model,
        settings,
        directive,
        *,
        tool_catalog,
        confirmed_tool_call=None,
    ):
        tool_name = str(directive.get("tool_name") or "").strip()
        if confirmed_tool_call:
            if confirmed_tool_call.name != tool_name:
                raise ValueError("Confirmed tool call does not match the forced command chain")
            return confirmed_tool_call

        runtime_tool = tool_catalog.get(tool_name)
        if not runtime_tool:
            return ToolCallRequest(
                name=tool_name,
                arguments={},
                reason=str(directive.get("instruction") or "").strip(),
            )
        if not (runtime_tool.get("parameters") or {}):
            return ToolCallRequest(
                name=tool_name,
                arguments={},
                reason=str(directive.get("instruction") or f"User invoked /{tool_name}").strip(),
            )

        planning_messages = tool_catalog.build_forced_planning_messages(
            messages,
            tool_name,
            directive.get("instruction"),
        )
        last_error = ""
        for _ in range(2):
            response = self.model_manager.chat(
                provider_name,
                planning_messages,
                model,
                settings or {},
            )
            try:
                tool_call = self._parse_tool_call(response)
            except ToolCallParseError as error:
                tool_call = None
                last_error = str(error)
            if tool_call and tool_call.name == tool_name:
                validation_error = self._validate_arguments(
                    runtime_tool,
                    tool_call.arguments,
                )
                if not validation_error:
                    return tool_call
                last_error = validation_error
            elif tool_call:
                last_error = f"Expected {tool_name}, received {tool_call.name}."
            else:
                last_error = last_error or f"Expected arguments for {tool_name}."
            self._append_user_instruction(
                planning_messages,
                (
                    f"Invalid forced tool arguments: {last_error} "
                    f"Return one tool_call for {tool_name} only."
                ),
            )

        return ToolCallRequest(
            name=tool_name,
            arguments={},
            reason=f"Argument planning failed: {last_error}",
        )

    def _attach_forced_chain_state(
        self,
        tool_event,
        directives,
        current_index,
        completed_events,
    ):
        tool_event["forced_chain"] = {
            "directives": [dict(directive) for directive in directives],
            "current_index": current_index,
            "completed_events": [
                {
                    key: value
                    for key, value in dict(event).items()
                    if key != "forced_chain"
                }
                for event in completed_events
            ],
        }

    def _parse_tool_call(self, response):
        return self.tool_call_parser.parse_response(response)

    def _parse_tool_decision(self, response):
        return self.tool_call_parser.parse_decision_response(response)

    def _requires_confirmation(self, tool_event):
        return str((tool_event.get("policy") or {}).get("status") or "").strip() == "confirmation_required"

    def _build_confirmation_response(self, provider_name, model, tool_events):
        tool_event = tool_events[-1] if tool_events else {}
        tool_name = str(tool_event.get("tool_name") or "tool").strip()
        path = str((tool_event.get("arguments") or {}).get("path") or "").strip()
        target = f" `{path}`" if path else ""
        action = "append to" if tool_name == "workspace_append_file" else "write"

        return {
            "provider": provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": (
                    f"I need your approval before I {action}{target} in the workspace."
                ),
            },
            "usage": {},
            "finish_reason": "confirmation_required",
            "message_id": None,
            "raw": {
                "tool_events": tool_events,
            },
        }

    def _build_confirmed_tool_call(self, tool_context=None):
        confirmation = (tool_context or {}).get("confirmed_tool_call")
        if not isinstance(confirmation, dict):
            return None

        name = str(confirmation.get("name") or confirmation.get("tool_name") or "").strip()
        if not name:
            return None

        arguments = confirmation.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return None

        return ToolCallRequest(
            name=name,
            arguments=arguments,
            reason=str(confirmation.get("reason") or "").strip(),
        )

    def _append_parse_error_message(self, tool_aware_messages, error):
        self._append_user_instruction(
            tool_aware_messages,
            (
                f"Tool call was invalid: {error} "
                "Do not execute anything yet. Retry with the exact JSON contract "
                "or answer normally if no tool is needed."
            ),
        )

    def _append_decision_error_message(self, planning_messages, error, response=None):
        self._append_sanitized_planning_response(planning_messages, response)
        self._append_user_instruction(
            planning_messages,
            (
                f"Tool decision was invalid. Tool call was invalid: {error} "
                "Do not execute anything yet. Retry with exactly one JSON object: "
                "either a top-level tool_call or "
                '{"tool_decision":{"needs_tool":false,"reason":"brief reason"}}.'
            ),
        )

    def _append_sanitized_planning_response(self, messages, response=None):
        content = str(((response or {}).get("message") or {}).get("content") or "").strip()
        if not content:
            return

        messages.append(
            {
                "role": "assistant",
                "content": "Invalid non-JSON tool planning response omitted.",
            }
        )

    def _append_assistant_response(self, messages, response=None):
        content = str(((response or {}).get("message") or {}).get("content") or "").strip()
        if not content:
            return

        if messages and messages[-1].get("role") == "assistant":
            messages[-1]["content"] = (
                f"{messages[-1].get('content', '').rstrip()}\n\n{content}"
            ).strip()
            return

        messages.append(
            {
                "role": "assistant",
                "content": content,
            }
        )

    def _append_user_instruction(self, messages, content):
        if messages and messages[-1].get("role") == "user":
            messages[-1]["content"] = (
                f"{messages[-1].get('content', '').rstrip()}\n\n{content}"
            ).strip()
            return

        messages.append(
            {
                "role": "user",
                "content": content,
            }
        )

    def _stream_final_response(
        self,
        provider_name,
        messages,
        model,
        settings,
        tool_events,
        *,
        should_stop=None,
    ):
        if self._last_tool_failed(tool_events):
            failure_response = self._build_failed_tool_response(
                provider_name,
                model,
                tool_events,
            )
            content = (failure_response.get("message") or {}).get("content", "")
            if content:
                yield {"type": "delta", "delta": content}
            yield {"type": "response", "response": failure_response}
            return

        final_response = None
        for event in self.model_manager.stream_chat(
            provider_name,
            messages,
            model,
            settings,
            should_stop=should_stop,
        ):
            if event.get("type") == "response":
                final_response = self._finalize_response(
                    event.get("response"),
                    tool_events,
                    provider_name=provider_name,
                    model=model,
                )
                yield {
                    **event,
                    "response": final_response,
                }
                continue

            yield event

        if final_response is None and self._is_stop_requested(should_stop):
            yield {
                "type": "response",
                "response": self._build_cancelled_response(
                    provider_name,
                    model,
                    tool_events,
                ),
            }

    def _execute_tool_call(self, tool_call, *, tool_catalog, tool_context=None):
        runtime_tool = tool_catalog.get(tool_call.name)
        if not runtime_tool:
            return self.execution_trace.build_tool_event(
                tool_call,
                {
                    "ok": False,
                    "error": f"Tool '{tool_call.name}' is not available for this turn.",
                },
                runtime_tool=None,
                policy_decision={
                    "allowed": False,
                    "status": "unavailable",
                    "risk_level": "unknown",
                },
            )

        validation_error = self._validate_arguments(runtime_tool, tool_call.arguments)
        if validation_error:
            return self.execution_trace.build_tool_event(
                tool_call,
                {
                    "ok": False,
                    "error": validation_error,
                },
                runtime_tool=runtime_tool,
                policy_decision={
                    "allowed": False,
                    "status": "invalid_arguments",
                    "risk_level": runtime_tool.get("risk_level", "read_only"),
                },
            )

        policy_decision = self.tool_call_policy.evaluate(
            runtime_tool,
            tool_call,
            context=tool_context,
        )
        if not policy_decision.get("allowed"):
            return self.execution_trace.build_tool_event(
                tool_call,
                {
                    "ok": False,
                    "error": policy_decision.get("reason") or "Tool execution is not allowed.",
                },
                runtime_tool=runtime_tool,
                policy_decision=policy_decision,
            )

        try:
            tool_result = self.tool_executor.execute(runtime_tool, tool_call.arguments)
            result_payload = {
                "ok": True,
                "result": tool_result,
            }
        except Exception as error:
            result_payload = {
                "ok": False,
                "error": str(error),
            }

        return self.execution_trace.build_tool_event(
            tool_call,
            result_payload,
            runtime_tool=runtime_tool,
            policy_decision=policy_decision,
        )

    def _validate_arguments(self, runtime_tool, arguments):
        parameters = runtime_tool.get("parameters") or {}
        if not isinstance(parameters, dict):
            return ""

        for name, schema in parameters.items():
            if not isinstance(schema, dict):
                continue

            if schema.get("required") and name not in arguments:
                return f"Missing required argument: {name}."

            if (
                schema.get("required")
                and schema.get("type") == "string"
                and isinstance(arguments.get(name), str)
                and not arguments[name].strip()
            ):
                return f"Argument '{name}' must not be empty."

            if name in arguments and not self._matches_type(arguments[name], schema.get("type")):
                expected_type = schema.get("type")
                return f"Argument '{name}' must be {expected_type}."

        return ""

    def _matches_type(self, value, expected_type):
        if not expected_type:
            return True

        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            return isinstance(value, list)

        return True

    def _handle_tool_limit(
        self,
        response,
        provider_name,
        tool_aware_messages,
        model,
        settings,
        tool_events,
    ):
        if response is None:
            return self._build_cancelled_response(provider_name, model, tool_events)

        self._append_user_instruction(
            tool_aware_messages,
            (
                "Tool limit reached. Do not request more tools. "
                "Answer the user with the information already available."
            ),
        )
        final_response = self.model_manager.chat(
            provider_name,
            tool_aware_messages,
            model,
            settings,
        )
        return self._finalize_response(
            final_response,
            tool_events,
            provider_name=provider_name,
            model=model,
        )

    def _finalize_response(self, response, tool_events, *, provider_name, model):
        response = self._attach_tool_events(response, tool_events)
        if self._last_tool_failed(tool_events):
            return self._build_failed_tool_response(provider_name, model, tool_events)

        try:
            final_tool_call = self._parse_tool_call(response)
        except ToolCallParseError:
            final_tool_call = None

        if not tool_events or not final_tool_call:
            return response

        fallback_response = self._build_tool_only_fallback_response(
            provider_name,
            model,
            tool_events,
        )
        return self._attach_tool_events(fallback_response, tool_events)

    def _last_tool_failed(self, tool_events):
        return bool(tool_events and not tool_events[-1].get("ok"))

    def _build_failed_tool_response(self, provider_name, model, tool_events):
        fallback_response = self._build_tool_only_fallback_response(
            provider_name,
            model,
            tool_events,
        )
        return self._attach_tool_events(fallback_response, tool_events)

    def _attach_tool_events(self, response, tool_events):
        if not tool_events:
            return response

        raw_response = response.get("raw") or {}
        raw_response["tool_events"] = tool_events
        response["raw"] = raw_response
        return response

    def _build_tool_only_fallback_response(self, provider_name, model, tool_events):
        tool_event = tool_events[-1] if tool_events else {}
        display_name = (
            tool_event.get("tool_display_name")
            or str(tool_event.get("tool_name") or "tool").replace("_", " ")
        )
        if tool_event.get("ok"):
            content = f"I used {display_name} and recorded the result."
        else:
            error = str(tool_event.get("error") or "The tool could not complete.")
            content = f"I could not complete {display_name}: {error}"

        return {
            "provider": provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "usage": {},
            "finish_reason": "stop",
            "message_id": None,
            "raw": {
                "tool_only_fallback": True,
            },
        }

    def _build_tool_start_stream_event(self, tool_call, tool_catalog):
        runtime_tool = tool_catalog.get(tool_call.name)
        return {
            "type": "tool_start",
            "tool_name": tool_call.name,
            "display_name": self.execution_trace.resolve_display_name(
                tool_call.name,
                runtime_tool,
            ),
            "reason": tool_call.reason,
            "arguments": tool_call.arguments,
        }

    def _build_tool_result_stream_event(self, tool_event):
        return {
            "type": "tool_result",
            "tool_name": tool_event["tool_name"],
            "display_name": tool_event.get("tool_display_name", ""),
            "ok": bool(tool_event.get("ok")),
            "policy": tool_event.get("policy") or {},
        }

    def _build_cancelled_response(self, provider_name, model, tool_events):
        response = {
            "provider": provider_name,
            "model": model,
            "message": {
                "role": "assistant",
                "content": "",
            },
            "usage": {},
            "finish_reason": "cancelled",
            "message_id": None,
            "raw": {
                "cancelled": True,
            },
        }
        return self._attach_tool_events(response, tool_events)

    def _is_stop_requested(self, should_stop=None):
        return bool(should_stop and should_stop())
