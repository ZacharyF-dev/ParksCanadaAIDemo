from fastapi.testclient import TestClient


def test_create_ticket_via_ui(client: TestClient) -> None:
    response = client.post(
        "/tickets/new",
        data={
            "title": "UI created ticket",
            "description": "Created from HTML form",
            "priority": "High",
            "assignee": "alice",
            "reporter": "tester",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/tickets/")


def test_ticket_detail_page_after_create(client: TestClient) -> None:
    create_response = client.post(
        "/tickets/new",
        data={
            "title": "Detail test",
            "description": "Ticket detail page should render",
            "priority": "Medium",
            "assignee": "bob",
            "reporter": "tester",
        },
        follow_redirects=False,
    )

    location = create_response.headers["location"]
    detail_response = client.get(location)

    assert detail_response.status_code == 200
    assert "Detail test" in detail_response.text
    assert "bob" in detail_response.text


def test_update_ticket_via_ui(client: TestClient) -> None:
    create_response = client.post(
        "/tickets/new",
        data={
            "title": "Old title",
            "description": "Old description",
            "priority": "Low",
            "assignee": "alice",
            "reporter": "tester",
        },
        follow_redirects=False,
    )
    location = create_response.headers["location"]
    ticket_id = int(location.rsplit("/", maxsplit=1)[-1])

    update_response = client.post(
        f"/tickets/{ticket_id}/update",
        data={
            "title": "New title",
            "description": "New description",
            "priority": "Critical",
            "assignee": "charlie",
            "reporter": "tester",
            "actor": "ui.user",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 303

    detail_response = client.get(f"/tickets/{ticket_id}")
    assert "New title" in detail_response.text
    assert "New description" in detail_response.text
    assert "Critical" in detail_response.text
    assert "charlie" in detail_response.text


def test_transition_ticket_via_ui(client: TestClient) -> None:
    create_response = client.post(
        "/tickets/new",
        data={
            "title": "Transition me",
            "description": "",
            "priority": "Medium",
            "assignee": "",
            "reporter": "tester",
        },
        follow_redirects=False,
    )
    ticket_id = int(create_response.headers["location"].rsplit("/", maxsplit=1)[-1])

    transition_response = client.post(
        f"/tickets/{ticket_id}/transition",
        data={
            "status": "In Progress",
            "actor": "workflow.user",
        },
        follow_redirects=False,
    )
    assert transition_response.status_code == 303

    detail_response = client.get(f"/tickets/{ticket_id}")
    assert "In Progress" in detail_response.text


def test_invalid_transition_returns_400(client: TestClient) -> None:
    create_response = client.post(
        "/tickets/new",
        data={
            "title": "Bad transition",
            "description": "",
            "priority": "Medium",
            "assignee": "",
            "reporter": "tester",
        },
        follow_redirects=False,
    )
    ticket_id = int(create_response.headers["location"].rsplit("/", maxsplit=1)[-1])

    response = client.post(
        f"/tickets/{ticket_id}/transition",
        data={
            "status": "Resolved",
            "actor": "workflow.user",
        },
    )
    assert response.status_code == 400
    assert "Invalid transition" in response.text


def test_add_comment_via_ui(client: TestClient) -> None:
    create_response = client.post(
        "/tickets/new",
        data={
            "title": "Comment me",
            "description": "",
            "priority": "Medium",
            "assignee": "",
            "reporter": "tester",
        },
        follow_redirects=False,
    )
    ticket_id = int(create_response.headers["location"].rsplit("/", maxsplit=1)[-1])

    comment_response = client.post(
        f"/tickets/{ticket_id}/comments",
        data={
            "author": "commenter",
            "body": "This is a test comment",
        },
        follow_redirects=False,
    )
    assert comment_response.status_code == 303

    detail_response = client.get(f"/tickets/{ticket_id}")
    assert "This is a test comment" in detail_response.text
    assert "commenter" in detail_response.text