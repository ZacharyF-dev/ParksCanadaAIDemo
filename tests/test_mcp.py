import os

from fastapi.testclient import TestClient


def test_mcp_tools_public_when_token_not_set(client: TestClient) -> None:
    response = client.get("/mcp/tools")
    assert response.status_code == 200

    payload = response.json()
    tool_names = {tool["name"] for tool in payload["tools"]}
    assert "create_ticket" in tool_names
    assert "get_ticket" in tool_names
    assert "list_tickets" in tool_names
    assert "update_ticket" in tool_names
    assert "transition_ticket" in tool_names
    assert "add_comment" in tool_names
    assert "get_ticket_history" in tool_names


def test_mcp_create_and_get_ticket(client: TestClient) -> None:
    create_response = client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "MCP created ticket",
                "description": "Created via MCP",
                "priority": "High",
                "assignee": "agent.user",
                "reporter": "agent.test",
            },
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["result"]
    ticket_id = created["id"]

    get_response = client.post(
        "/mcp/call",
        json={
            "tool": "get_ticket",
            "arguments": {
                "ticket_id": ticket_id,
            },
        },
    )
    assert get_response.status_code == 200
    ticket = get_response.json()["result"]
    assert ticket["title"] == "MCP created ticket"
    assert ticket["priority"] == "High"
    assert ticket["assignee"] == "agent.user"


def test_mcp_list_tickets(client: TestClient) -> None:
    client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "First ticket",
                "description": "one",
                "priority": "Low",
                "reporter": "tester",
            },
        },
    )
    client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "Second ticket",
                "description": "two",
                "priority": "Critical",
                "reporter": "tester",
            },
        },
    )

    response = client.post(
        "/mcp/call",
        json={
            "tool": "list_tickets",
            "arguments": {
                "priority": "Critical",
            },
        },
    )
    assert response.status_code == 200
    results = response.json()["result"]
    assert len(results) == 1
    assert results[0]["title"] == "Second ticket"


def test_mcp_update_ticket(client: TestClient) -> None:
    create_response = client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "Update target",
                "description": "before",
                "priority": "Low",
                "reporter": "tester",
            },
        },
    )
    ticket_id = create_response.json()["result"]["id"]

    response = client.post(
        "/mcp/call",
        json={
            "tool": "update_ticket",
            "arguments": {
                "ticket_id": ticket_id,
                "title": "Updated title",
                "description": "after",
                "priority": "Critical",
                "assignee": "updated.user",
                "actor": "agent.updater",
            },
        },
    )
    assert response.status_code == 200

    get_response = client.post(
        "/mcp/call",
        json={
            "tool": "get_ticket",
            "arguments": {
                "ticket_id": ticket_id,
            },
        },
    )
    ticket = get_response.json()["result"]
    assert ticket["title"] == "Updated title"
    assert ticket["description"] == "after"
    assert ticket["priority"] == "Critical"
    assert ticket["assignee"] == "updated.user"


def test_mcp_transition_ticket(client: TestClient) -> None:
    create_response = client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "Transition target",
                "description": "",
                "priority": "Medium",
                "reporter": "tester",
            },
        },
    )
    ticket_id = create_response.json()["result"]["id"]

    transition_response = client.post(
        "/mcp/call",
        json={
            "tool": "transition_ticket",
            "arguments": {
                "ticket_id": ticket_id,
                "status": "In Progress",
                "actor": "workflow.agent",
            },
        },
    )
    assert transition_response.status_code == 200
    assert transition_response.json()["result"]["status"] == "In Progress"


def test_mcp_invalid_transition_rejected(client: TestClient) -> None:
    create_response = client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "Invalid transition target",
                "description": "",
                "priority": "Medium",
                "reporter": "tester",
            },
        },
    )
    ticket_id = create_response.json()["result"]["id"]

    response = client.post(
        "/mcp/call",
        json={
            "tool": "transition_ticket",
            "arguments": {
                "ticket_id": ticket_id,
                "status": "Resolved",
                "actor": "workflow.agent",
            },
        },
    )
    assert response.status_code == 400
    assert "Invalid transition" in response.text


def test_mcp_add_comment_and_get_history(client: TestClient) -> None:
    create_response = client.post(
        "/mcp/call",
        json={
            "tool": "create_ticket",
            "arguments": {
                "title": "Comment target",
                "description": "",
                "priority": "Medium",
                "reporter": "tester",
            },
        },
    )
    ticket_id = create_response.json()["result"]["id"]

    comment_response = client.post(
        "/mcp/call",
        json={
            "tool": "add_comment",
            "arguments": {
                "ticket_id": ticket_id,
                "author": "comment.agent",
                "body": "Please investigate this behavior",
            },
        },
    )
    assert comment_response.status_code == 200

    history_response = client.post(
        "/mcp/call",
        json={
            "tool": "get_ticket_history",
            "arguments": {
                "ticket_id": ticket_id,
            },
        },
    )
    assert history_response.status_code == 200
    result = history_response.json()["result"]
    assert len(result["comments"]) == 1
    assert result["comments"][0]["author"] == "comment.agent"
    assert len(result["events"]) >= 2


def test_mcp_unknown_tool_returns_404(client: TestClient) -> None:
    response = client.post(
        "/mcp/call",
        json={
            "tool": "does_not_exist",
            "arguments": {},
        },
    )
    assert response.status_code == 404


def test_mcp_missing_ticket_returns_404(client: TestClient) -> None:
    response = client.post(
        "/mcp/call",
        json={
            "tool": "get_ticket",
            "arguments": {
                "ticket_id": 9999,
            },
        },
    )
    assert response.status_code == 404