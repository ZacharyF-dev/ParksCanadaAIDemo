from fastapi.testclient import TestClient


def test_api_get_ticket_detail(client: TestClient) -> None:
    create_response = client.post(
        "/tickets/new",
        data={
            "title": "Polling API ticket",
            "description": "For JSON polling",
            "priority": "High",
            "assignee": "agent1",
            "reporter": "tester",
        },
        follow_redirects=False,
    )
    ticket_id = int(create_response.headers["location"].rsplit("/", maxsplit=1)[-1])

    client.post(
        f"/tickets/{ticket_id}/comments",
        data={
            "author": "agent1",
            "body": "Polling comment",
        },
        follow_redirects=False,
    )

    response = client.get(f"/api/tickets/{ticket_id}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["title"] == "Polling API ticket"
    assert payload["priority"] == "High"
    assert payload["assignee"] == "agent1"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["body"] == "Polling comment"
    assert len(payload["events"]) >= 2