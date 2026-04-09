import base64


def api_headers(key: str) -> dict:
    return {"X-API-KEY": key}


class TestA2AIntegration:
    def test_get_agent_card_for_enabled_agent(self, client, fake_app, fake_agent, db):
        fake_agent.a2a_enabled = True
        fake_agent.a2a_name_override = "A2A Test Agent"
        fake_agent.a2a_skill_tags = ["test", "support"]
        db.add(fake_agent)
        db.flush()

        response = client.get(
            f"/.well-known/a2a/id/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "A2A Test Agent"
        assert payload["url"].endswith(
            f"/a2a/v1/id/{fake_app.app_id}/agents/{fake_agent.agent_id}"
        )
        assert payload["capabilities"]["streaming"] is True
        assert payload["securitySchemes"]["apiKey"]["type"] == "apiKey"
        assert payload["skills"][0]["tags"] == ["test", "support"]

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
        assert body["result"]["status"]["state"] == "completed"
        assert body["result"]["metadata"]["conversation_id"] == 321
        assert captured["message"] == "Summarize this attachment"
        assert len(captured["file_references"]) == 1

        artifacts = body["result"]["artifacts"]
        assert len(artifacts) == 2
        assert artifacts[0]["parts"][0]["kind"] == "text"
        assert artifacts[1]["parts"][0]["kind"] == "file"
        assert "static/persistent/report.txt" in artifacts[1]["parts"][0]["file"]["uri"]
