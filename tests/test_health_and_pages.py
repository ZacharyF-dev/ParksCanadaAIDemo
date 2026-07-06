from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Tickets" in response.text


def test_new_ticket_page_renders(client: TestClient) -> None:
    response = client.get("/tickets/new")
    assert response.status_code == 200
    assert "Create Ticket" in response.text