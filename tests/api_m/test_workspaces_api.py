import json
from pathlib import Path

from tests.test_support import ApiTestCase


class WorkspacesApiTests(ApiTestCase):
    def test_forced_tool_chain_resumes_after_write_confirmation_without_repeating_completed_tools(self):
        workspace_root = Path(self.temp_dir.name) / "forced-chain-workspace"
        workspace_root.mkdir()
        project_id = self.db.projects.create("Forced chain project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Forced confirmation",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )
        date_tool = self.db.tools.get_by_name("current_date")
        self.client.patch(
            "/api/tools",
            json={"id": date_tool["id"], "is_active": True},
            headers=self.auth_headers,
        )
        date_runs = {"count": 0}

        def run_date(arguments):
            date_runs["count"] += 1
            return {"date": "2026-06-22"}

        self.api_manager.services.tool_registry._runtime_catalog["current_date"]["runner"] = run_date
        calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            calls["count"] += 1
            system_content = messages[0]["content"]
            all_content = "\n".join(message["content"] for message in messages)
            if "explicitly invoked /workspace_write_file" in system_content:
                self.assertIn("Tool result for current_date", all_content)
                return {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": (
                            '{"tool_call":{"name":"workspace_write_file","arguments":'
                            '{"path":"notes.txt","content":"hello","overwrite":false,'
                            '"create_dirs":false}}}'
                        ),
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }
            if "explicitly invoked /workspace_read_file" in system_content:
                self.assertIn("Tool result for workspace_write_file", all_content)
                return {
                    "provider": provider,
                    "model": model,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call":{"name":"workspace_read_file","arguments":{"path":"notes.txt"}}}',
                    },
                    "usage": {},
                    "finish_reason": None,
                    "message_id": None,
                    "raw": {},
                }
            return {
                "provider": provider,
                "model": model,
                "message": {"role": "assistant", "content": "Created and read notes.txt."},
                "usage": {},
                "finish_reason": "stop",
                "message_id": "forced-confirmed-final",
                "raw": {},
            }

        self.model_manager.chat = fake_chat
        content = (
            "/current_date get today "
            "/workspace_write_file create notes.txt "
            "/workspace_read_file read it"
        )
        initial_response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": content}],
            },
            headers=self.auth_headers,
        )
        initial_payload = initial_response.get_json()["response"]
        pending_event = initial_payload["raw"]["tool_events"][1]
        pending_message_id = initial_payload["message"]["id"]

        self.assertEqual(initial_payload["finish_reason"], "confirmation_required")
        self.assertEqual(date_runs["count"], 1)
        self.client.patch(
            "/api/chat/tool-confirmations",
            json={
                "message_id": pending_message_id,
                "tool_event_index": 1,
                "status": "confirming",
            },
            headers=self.auth_headers,
        )
        resume_response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [
                    {"role": "user", "content": content},
                    {"role": "assistant", "content": initial_payload["message"]["content"]},
                ],
                "tool_confirmation": {
                    "name": pending_event["tool_name"],
                    "arguments": pending_event["arguments"],
                    "reason": pending_event.get("reason", ""),
                    "source_message_id": pending_message_id,
                    "source_event_index": 1,
                },
            },
            headers=self.auth_headers,
        )
        resume_payload = resume_response.get_json()["response"]

        self.assertEqual(resume_response.status_code, 200)
        self.assertEqual(date_runs["count"], 1)
        self.assertEqual(
            [event["tool_name"] for event in resume_payload["raw"]["tool_events"]],
            ["workspace_write_file", "workspace_read_file"],
        )
        self.assertEqual((workspace_root / "notes.txt").read_text(encoding="utf-8"), "hello")

    def test_project_workspace_can_connect_index_read_and_search(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        (workspace_root / "app.py").write_text("def hello():\n    return 'horizone'\n", encoding="utf-8")
        (workspace_root / "node_modules").mkdir()
        (workspace_root / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")

        project_id = self.db.projects.create("Workspace Project")

        connect_response = self.client.post(
            "/api/projects/workspace",
            json={
                "project_id": project_id,
                "root_path": str(workspace_root),
                "display_name": "Workspace",
            },
            headers=self.auth_headers,
        )
        connect_payload = connect_response.get_json()
        workspace = connect_payload["workspace"]

        self.assertEqual(connect_response.status_code, 201)
        self.assertEqual(workspace["project_id"], project_id)
        self.assertEqual(workspace["root_path"], str(workspace_root.resolve()))
        self.assertEqual(connect_payload["file_count"], 1)

        files_response = self.client.get(
            f"/api/workspaces/files?workspace_id={workspace['id']}",
            headers=self.auth_headers,
        )
        files_payload = files_response.get_json()

        self.assertEqual(files_response.status_code, 200)
        self.assertEqual([file["path"] for file in files_payload["files"]], ["app.py"])

        read_response = self.client.get(
            f"/api/workspaces/file?workspace_id={workspace['id']}&path=app.py",
            headers=self.auth_headers,
        )
        read_payload = read_response.get_json()

        self.assertEqual(read_response.status_code, 200)
        self.assertIn("return 'horizone'", read_payload["file"]["content"])

        search_response = self.client.post(
            "/api/workspaces/search",
            json={"workspace_id": workspace["id"], "query": "horizone"},
            headers=self.auth_headers,
        )
        search_payload = search_response.get_json()

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_payload["matches"][0]["path"], "app.py")
        self.assertEqual(search_payload["matches"][0]["line"], 2)

    def test_workspace_file_read_blocks_path_traversal(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        outside_file = Path(self.temp_dir.name) / "outside.txt"
        outside_file.write_text("secret", encoding="utf-8")
        project_id = self.db.projects.create("Guarded Project")
        workspace_id = self.db.project_workspaces.upsert(
            project_id,
            str(workspace_root),
            "Workspace",
        )

        response = self.client.get(
            f"/api/workspaces/file?workspace_id={workspace_id}&path=../outside.txt",
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertEqual(payload["error"]["message"], "Path is outside the workspace")

    def test_workspace_file_can_be_written_through_api(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        project_id = self.db.projects.create("Writable Project")
        workspace_id = self.db.project_workspaces.upsert(
            project_id,
            str(workspace_root),
            "Workspace",
        )

        response = self.client.post(
            "/api/workspaces/file",
            json={
                "workspace_id": workspace_id,
                "path": "scripts/helloworld.sh",
                "content": "#!/usr/bin/env bash\necho \"Hello, world!\"\n",
                "create_dirs": True,
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["file"]["path"], "scripts/helloworld.sh")
        self.assertTrue((workspace_root / "scripts" / "helloworld.sh").exists())
        self.assertIn("Hello, world!", (workspace_root / "scripts" / "helloworld.sh").read_text(encoding="utf-8"))

    def test_workspace_file_can_be_appended_through_api(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        (workspace_root / "hello.txt").write_text("hola", encoding="utf-8")
        project_id = self.db.projects.create("Append Project")
        workspace_id = self.db.project_workspaces.upsert(
            project_id,
            str(workspace_root),
            "Workspace",
        )

        response = self.client.post(
            "/api/workspaces/file/append",
            json={
                "workspace_id": workspace_id,
                "path": "hello.txt",
                "content": "que tal estas?",
                "ensure_newline_before": True,
                "ensure_newline_after": True,
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["file"]["path"], "hello.txt")
        self.assertEqual(
            (workspace_root / "hello.txt").read_text(encoding="utf-8"),
            "hola\nque tal estas?\n",
        )

    def test_chat_can_create_workspace_file_with_contextual_tool(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        project_id = self.db.projects.create("Agent Project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Workspace edit",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        def fake_chat(provider, messages, model, settings):
            self.assertIn("Tool result for workspace_write_file", messages[-1]["content"])
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Created `helloworld.sh` in the connected workspace.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-workspace-write-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "continua con la accion aprobada"}],
                "tool_confirmation": {
                    "name": "workspace_write_file",
                    "arguments": {
                        "path": "helloworld.sh",
                        "content": "#!/usr/bin/env bash\necho \"Hello, world!\"\n",
                        "overwrite": False,
                        "create_dirs": False,
                    },
                    "reason": "The user approved this workspace write.",
                },
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue((workspace_root / "helloworld.sh").exists())
        self.assertIn("Hello, world!", (workspace_root / "helloworld.sh").read_text(encoding="utf-8"))
        self.assertIn("workspace_write_file", payload["response"]["raw"]["tool_events"][0]["tool_name"])
        self.assertIn("created helloworld.sh", payload["response"]["raw"]["tool_events"][0]["tool_summary"])
        self.assertEqual(payload["response"]["raw"]["tool_events"][0]["policy"]["status"], "confirmed")
        self.assertIn("Created", payload["response"]["message"]["content"])

    def test_disabled_workspace_tool_is_not_offered_to_chat(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        project_id = self.db.projects.create("Agent Project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Workspace edit",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )
        self.client.patch(
            "/api/tools",
            json={"id": "runtime:workspace_search", "is_active": False},
            headers=self.auth_headers,
        )

        def fake_chat(provider, messages, model, settings):
            self.assertIn("workspace_read_file", messages[0]["content"])
            self.assertNotIn("workspace_search", messages[0]["content"])
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "I can use the remaining workspace tools.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-workspace-tools-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "What can you inspect?"}],
            },
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)

    def test_chat_can_append_workspace_file_with_contextual_tool(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        (workspace_root / "hello.txt").write_text("hola", encoding="utf-8")
        project_id = self.db.projects.create("Agent Append Project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Workspace append",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        def fake_chat(provider, messages, model, settings):
            self.assertIn("Tool result for workspace_append_file", messages[-1]["content"])
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Añadí la frase a `hello.txt`.",
                },
                "usage": {},
                "finish_reason": "stop",
                "message_id": "resp-workspace-append-1",
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "continua con la accion aprobada"}],
                "tool_confirmation": {
                    "name": "workspace_append_file",
                    "arguments": {
                        "path": "hello.txt",
                        "content": "que tal estas?",
                        "ensure_newline_before": True,
                        "ensure_newline_after": True,
                    },
                    "reason": "The user approved this workspace append.",
                },
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (workspace_root / "hello.txt").read_text(encoding="utf-8"),
            "hola\nque tal estas?\n",
        )
        self.assertEqual(
            payload["response"]["raw"]["tool_events"][0]["tool_name"],
            "workspace_append_file",
        )
        self.assertIn(
            "appended to hello.txt",
            payload["response"]["raw"]["tool_events"][0]["tool_summary"],
        )
        self.assertEqual(payload["response"]["raw"]["tool_events"][0]["policy"]["status"], "confirmed")

    def test_chat_blocks_workspace_write_without_user_confirmation(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        project_id = self.db.projects.create("Guarded Agent Project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Guarded workspace write",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": '{"tool_call":{"name":"workspace_write_file","arguments":{"path":"surprise.txt","content":"nope","overwrite":false,"create_dirs":false},"reason":"Trying to write without user intent."}}',
                },
                "usage": {},
                "finish_reason": None,
                "message_id": None,
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "crea surprise.txt con el texto nope"}],
            },
            headers=self.auth_headers,
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(model_calls["count"], 1)
        self.assertFalse((workspace_root / "surprise.txt").exists())
        self.assertEqual(payload["response"]["finish_reason"], "confirmation_required")
        self.assertIn("approval", payload["response"]["message"]["content"].lower())
        self.assertEqual(
            payload["response"]["raw"]["tool_events"][0]["policy"]["status"],
            "confirmation_required",
        )

    def test_streaming_chat_blocks_workspace_write_without_user_confirmation(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        (workspace_root / "hello.txt").write_text("hola\n", encoding="utf-8")
        project_id = self.db.projects.create("Guarded Streaming Agent Project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Guarded streaming workspace write",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )

        model_calls = {"count": 0}

        def fake_chat(provider, messages, model, settings):
            model_calls["count"] += 1
            return {
                "provider": provider,
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": '{"tool_call":{"name":"workspace_write_file","arguments":{"path":"hello.txt","content":"adios","overwrite":true,"create_dirs":false},"reason":"The user asked to update hello.txt."}}',
                },
                "usage": {},
                "finish_reason": None,
                "message_id": None,
                "raw": {},
            }

        self.model_manager.chat = fake_chat

        response = self.client.post(
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "messages": [{"role": "user", "content": "actualiza hello.txt con adios"}],
                "stream": True,
            },
            headers=self.auth_headers,
            buffered=True,
        )
        payload = response.get_data(as_text=True)
        stored_messages = self.db.messages.for_conversation(conversation_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(model_calls["count"], 1)
        self.assertEqual((workspace_root / "hello.txt").read_text(encoding="utf-8"), "hola\n")
        self.assertIn("event: tool_result", payload)
        self.assertIn('"finish_reason": "confirmation_required"', payload)
        self.assertIn('"status": "confirmation_required"', payload)
        self.assertIn("approval", stored_messages[-1]["content"].lower())
        self.assertEqual(stored_messages[-1]["tool_events"][0]["policy"]["status"], "confirmation_required")
        end_payload = self._parse_stream_event_payload(payload, "end")
        self.assertEqual(end_payload["response"]["message"]["id"], stored_messages[-1]["id"])

    def test_tool_confirmation_status_update_persists_for_reloaded_conversation(self):
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Persist confirmation decision",
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )
        message_id = self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="I need approval before writing the file.",
            tool_events=[
                {
                    "ok": False,
                    "tool_name": "workspace_write_file",
                    "arguments": {"path": "hello.txt", "content": "hello"},
                    "error": "This tool requires explicit confirmation before execution.",
                    "policy": {
                        "status": "confirmation_required",
                        "risk_level": "workspace_write",
                    },
                },
            ],
        )

        update_response = self.client.patch(
            "/api/chat/tool-confirmations",
            json={
                "message_id": message_id,
                "tool_event_index": 0,
                "status": "confirming",
            },
            headers=self.auth_headers,
        )
        reload_response = self.client.get(
            f"/api/conversations?id={conversation_id}&include_messages=1",
            headers=self.auth_headers,
        )
        reload_payload = reload_response.get_json()
        reloaded_message = reload_payload["messages"][0]

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(reload_response.status_code, 200)
        self.assertEqual(
            reloaded_message["tool_events"][0]["policy"]["status"],
            "confirming",
        )

    def _parse_stream_event_payload(self, payload, event_name):
        current_event = None
        data_lines = []

        for line in payload.splitlines():
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
                data_lines = []
                continue
            if current_event == event_name and line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
                continue
            if current_event == event_name and not line.strip() and data_lines:
                return json.loads("\n".join(data_lines))

        if current_event == event_name and data_lines:
            return json.loads("\n".join(data_lines))
        raise AssertionError(f"Stream event {event_name!r} was not found")

    def test_conversation_export_includes_contextual_workspace_tools(self):
        workspace_root = Path(self.temp_dir.name) / "workspace"
        workspace_root.mkdir()
        (workspace_root / "hello.txt").write_text("hello\n", encoding="utf-8")
        project_id = self.db.projects.create("Export Workspace Project")
        self.db.project_workspaces.upsert(project_id, str(workspace_root), "Workspace")
        profile = self.db.profiles.get_default()
        conversation_id = self.db.conversations.create(
            title="Workspace export",
            project_id=project_id,
            profile_id=profile["id"],
            provider="ollama",
            model="qwen3",
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="actualiza hello.txt",
            position=0,
        )
        self.db.messages.create(
            conversation_id=conversation_id,
            role="assistant",
            content="No pude actualizarlo.",
            position=1,
            profile_id=profile["id"],
            profile_name=profile["name"],
        )

        response = self.client.get(
            f"/api/conversations/export?id={conversation_id}",
            headers=self.auth_headers,
        )
        payload = response.get_json()["export"]
        available_tool_names = {
            tool["name"]
            for tool in payload["messages"][1]["generation"]["available_tools"]
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["workspace"]["project_id"], project_id)
        self.assertIn("workspace_search", available_tool_names)
        self.assertIn("workspace_read_file", available_tool_names)
        self.assertIn("workspace_append_file", available_tool_names)
        self.assertIn("workspace_write_file", available_tool_names)
        self.assertIn(
            "workspace_write_file",
            payload["messages"][1]["generation"]["input_messages"][0]["content"],
        )
