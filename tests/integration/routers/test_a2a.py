import base64
from io import BytesIO

from fastapi import UploadFile
from models.a2a_task import A2ATask


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


class TestA2AIntegration:
    def test_deleting_api_key_nulls_a2a_task_reference(
        self,
        db,
        fake_app,
        fake_agent,
        fake_api_key,
    ):
        task = A2ATask(
            task_id="task-api-key-delete",
            context_id="ctx-api-key-delete",
            app_id=fake_app.app_id,
            agent_id=fake_agent.agent_id,
            api_key_id=fake_api_key.key_id,
            status="submitted",
            task_payload={"id": "task-api-key-delete", "status": {"state": "submitted"}},
        )
        db.add(task)
        db.commit()

        db.delete(fake_api_key)
        db.commit()
        db.refresh(task)

        assert task.api_key_id is None

    def test_get_agent_card_for_enabled_agent(self, client, fake_app, fake_agent, db):
        fake_agent.a2a_enabled = True
        fake_agent.a2a_name_override = "A2A Test Agent"
        fake_agent.a2a_skill_tags = ["test", "support"]
        db.add(fake_agent)
        db.flush()

        response = client.get(
            f"/.well-known/a2a/id/{fake_app.app_id}/agents/{fake_agent.agent_id}/agent-card.json"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "A2A Test Agent"
        assert payload["url"].endswith(
            f"/a2a/v1/id/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )
        assert payload["capabilities"]["streaming"] is True
        assert payload["capabilities"]["skills"][0]["inputOutputModes"] == [
            "text",
            "file",
            "data",
        ]
        assert "file" in payload["defaultInputModes"]
        assert "data" in payload["defaultInputModes"]
        assert payload["securitySchemes"]["apiKey"]["type"] == "apiKey"
        assert payload["skills"][0]["tags"] == ["test", "support"]

    def test_get_agent_card_legacy_alias_still_resolves(self, client, fake_app, fake_agent, db):
        fake_agent.a2a_enabled = True
        db.add(fake_agent)
        db.flush()

        response = client.get(
            f"/.well-known/a2a/id/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )

        assert response.status_code == 200
        assert response.json()["url"].endswith(
            f"/a2a/v1/id/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )

    def test_root_agent_card_maps_to_configured_slug_agent(
        self,
        client,
        fake_app,
        fake_agent,
        db,
        monkeypatch,
    ):
        from routers import a2a as a2a_router_module

        fake_app.slug = "cluedo"
        fake_agent.agent_id = 2
        fake_agent.a2a_enabled = True
        db.add(fake_app)
        db.add(fake_agent)
        db.flush()

        monkeypatch.setattr(a2a_router_module, "ROOT_AGENT_CARD_APP_SLUG", "cluedo")
        monkeypatch.setattr(a2a_router_module, "ROOT_AGENT_CARD_AGENT_ID", 2)

        response = client.get("/.well-known/agent-card.json")

        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == fake_agent.name
        assert payload["url"].endswith(
            f"/a2a/v1/apps/{fake_app.slug}/agents/{fake_agent.agent_id}"
        )

    def test_message_send_supports_file_input_and_output_artifacts(
        self,
        client,
        fake_app,
        fake_agent,
        fake_api_key,
        db,
        monkeypatch,
    ):
        from routers import a2a as a2a_router_module
        from services import a2a_agent_executor as executor_module

        a2a_router_module.get_a2a_request_handler.cache_clear()

        fake_agent.a2a_enabled = True
        fake_agent.has_memory = True
        db.add(fake_agent)
        db.flush()

        captured = {}

        async def fake_stream_agent_chat(
            self,
            agent_id,
            message,
            file_references,
            search_params,
            user_context,
            conversation_id,
            db,
        ):
            captured["agent_id"] = agent_id
            captured["message"] = message
            captured["file_references"] = file_references
            captured["conversation_id"] = conversation_id
            yield (
                'data: {"type":"metadata","data":{"conversation_id":321,'
                f'"agent_id":{agent_id},"agent_name":"A2A","has_memory":true}}\n\n'
            )
            yield 'data: {"type":"token","data":{"content":"Hello from Mattin"}}\n\n'
            yield (
                'data: {"type":"done","data":{"response":"Hello from Mattin",'
                '"conversation_id":321,'
                '"files":[{"file_id":"out-1","filename":"report.txt","file_type":"text"}]}}\n\n'
            )

        async def fake_list_attached_files(
            self,
            agent_id,
            user_context=None,
            conversation_id=None,
        ):
            return [
                {
                    "file_id": "out-1",
                    "filename": "report.txt",
                    "file_type": "text",
                    "file_path": "persistent/report.txt",
                    "mime_type": "text/plain",
                }
            ]

        monkeypatch.setattr(
            executor_module.AgentStreamingService,
            "stream_agent_chat",
            fake_stream_agent_chat,
        )
        monkeypatch.setattr(
            executor_module.FileManagementService,
            "list_attached_files",
            fake_list_attached_files,
        )

        encoded_file = base64.b64encode(b"hello from file").decode()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "user",
                    "parts": [
                        {"kind": "text", "text": "Summarize this attachment"},
                        {
                            "kind": "file",
                            "file": {
                                "name": "note.txt",
                                "mimeType": "text/plain",
                                "bytes": encoded_file,
                            },
                        },
                    ],
                }
            },
        }

        response = client.post(
            f"/a2a/v1/id/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=payload,
            headers=api_headers(fake_api_key.key),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["result"]["status"]["state"] == "input-required"
        assert body["result"]["metadata"]["conversation_id"] == 321
        assert captured["message"] == "Summarize this attachment"
        assert len(captured["file_references"]) == 1

        artifacts = body["result"]["artifacts"]
        assert len(artifacts) == 2
        assert artifacts[0]["parts"][0]["kind"] == "text"
        assert artifacts[1]["parts"][0]["kind"] == "file"
        assert "static/persistent/report.txt" in artifacts[1]["parts"][0]["file"]["uri"]

    def test_message_send_accepts_file_ref_alias(
        self,
        client,
        fake_app,
        fake_agent,
        fake_api_key,
        db,
        monkeypatch,
    ):
        from routers import a2a as a2a_router_module
        from services import a2a_agent_executor as executor_module

        a2a_router_module.get_a2a_request_handler.cache_clear()

        fake_agent.a2a_enabled = True
        fake_agent.has_memory = True
        db.add(fake_agent)
        db.flush()

        captured = {}

        async def fake_file_part_to_upload(self, part):
            captured["uri"] = part.file.uri
            captured["mime_type"] = part.file.mime_type
            captured["name"] = part.file.name
            return UploadFile(filename=part.file.name or "attachment", file=BytesIO(b"file-ref"))

        async def fake_resolve_chat_files(
            self,
            files,
            file_reference_ids,
            agent_id,
            user_context,
            conversation_id,
        ):
            captured["upload_count"] = len(files or [])
            return []

        async def fake_stream_agent_chat(
            self,
            agent_id,
            message,
            file_references,
            search_params,
            user_context,
            conversation_id,
            db,
        ):
            captured["message"] = message
            yield (
                'data: {"type":"metadata","data":{"conversation_id":654,'
                f'"agent_id":{agent_id},"agent_name":"A2A","has_memory":true}}\n\n'
            )
            yield 'data: {"type":"done","data":{"response":"File ref processed","conversation_id":654}}\n\n'

        monkeypatch.setattr(
            executor_module.MattinA2AAgentExecutor,
            "_file_part_to_upload",
            fake_file_part_to_upload,
        )
        monkeypatch.setattr(
            executor_module.FileManagementService,
            "resolve_chat_files",
            fake_resolve_chat_files,
        )
        monkeypatch.setattr(
            executor_module.AgentStreamingService,
            "stream_agent_chat",
            fake_stream_agent_chat,
        )

        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "msg-file-ref",
                    "role": "user",
                    "parts": [
                        {"kind": "text", "text": "Analyze this linked file"},
                        {
                            "kind": "fileRef",
                            "fileRef": {
                                "uri": "https://example.com/test-file.txt",
                                "mimeType": "text/plain",
                                "name": "test-file.txt",
                            },
                        },
                    ],
                }
            },
        }

        response = client.post(
            f"/a2a/v1/id/{fake_app.app_id}/agents/{fake_agent.agent_id}",
            json=payload,
            headers=api_headers(fake_api_key.key),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["result"]["status"]["state"] == "input-required"
        assert captured["message"] == "Analyze this linked file"
        assert captured["uri"] == "https://example.com/test-file.txt"
        assert captured["mime_type"] == "text/plain"
        assert captured["name"] == "test-file.txt"
        assert captured["upload_count"] == 1
