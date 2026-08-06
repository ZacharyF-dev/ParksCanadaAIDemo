# Mini Jira MCP

A lightweight Jira-like application designed for local AI and MCP experimentation.

It includes:

* 🧠 An MCP server built with FastMCP
* 🌐 HTTP Streamable MCP transport
* 🔌 A simple REST API
* 🗄️ A lightweight SQLite database
* 🌱 Seed/sample data

---

## Features

### Ticket Management

* Create tickets
* List tickets
* View ticket details
* Update ticket status
* Assign or unassign tickets
* Add comments
* List comments
* Search tickets

### Supported Statuses

* `todo`
* `in_progress`
* `blocked`
* `done`

---

# Requirements

* Python 3.11+

---

# Installation

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install the project:

```bash
pip install -e .
```

---

# Running the Application

Start both the backend and frontend:

```bash
python run.py
```

This launches:

| Service           | URL                   |
| ----------------- | --------------------- |
| Backend API + MCP | http://127.0.0.1:8000 |
| Frontend UI       | http://127.0.0.1:8001 |

Open the frontend in your browser:

```
http://127.0.0.1:8001
```

---

# Database

Mini Jira MCP uses a local SQLite database:

```
mini_jira.db
```

On first startup, the application automatically creates the database and seeds it with a small set of example tickets and comments.

---

# MCP Endpoint

The Streamable HTTP MCP endpoint is available at:

```
http://127.0.0.1:8000/mcp
```

---

# Available MCP Tools

* `create_ticket`
* `list_tickets`
* `get_ticket`
* `update_status`
* `assign_ticket`
* `add_comment`
* `list_comments`

---

# Example MCP Tool Calls

## Create a Ticket

```json
{
  "name": "create_ticket",
  "arguments": {
    "title": "Checkout page fails for guest users",
    "description": "Observed 500 error after clicking Pay Now.",
    "priority": "high",
    "assignee": "alex"
  }
}
```

## Update Ticket Status

```json
{
  "name": "update_status",
  "arguments": {
    "ticket_id": 1,
    "status": "in_progress"
  }
}
```

## Add a Comment

```json
{
  "name": "add_comment",
  "arguments": {
    "ticket_id": 1,
    "author": "alex",
    "body": "Investigating now."
  }
}
```

---

# REST API

The web UI communicates with the backend through a simple REST API.

## List Tickets

```
GET /api/tickets
```

Optional query parameters:

* `status`
* `q`

Example:

```
GET /api/tickets?status=todo&q=login
```

---

## Get Ticket Details

```
GET /api/tickets/{ticket_id}
```

---

## Create a Ticket

```
POST /api/tickets
Content-Type: application/json
```

Request body:

```json
{
  "title": "New issue",
  "description": "Details here",
  "priority": "medium",
  "assignee": "sam"
}
```

---

## Update Ticket Status

```
PATCH /api/tickets/{ticket_id}/status
Content-Type: application/json
```

Request body:

```json
{
  "status": "done"
}
```

---

## Assign a Ticket

```
PATCH /api/tickets/{ticket_id}/assign
Content-Type: application/json
```

Assign a user:

```json
{
  "assignee": "alex"
}
```

Clear the assignment:

```json
{
  "assignee": null
}
```

---

## Add a Comment

```
POST /api/tickets/{ticket_id}/comments
Content-Type: application/json
```

Request body:

```json
{
  "author": "sam",
  "body": "This is fixed in my branch."
}
```

---

# Configuration

The following environment variables are optional:

| Variable                  | Description              |
| ------------------------- | ------------------------ |
| `MINI_JIRA_DB_PATH`       | SQLite database location |
| `MINI_JIRA_BACKEND_HOST`  | Backend host             |
| `MINI_JIRA_BACKEND_PORT`  | Backend port             |
| `MINI_JIRA_FRONTEND_HOST` | Frontend host            |
| `MINI_JIRA_FRONTEND_PORT` | Frontend port            |

Example:

```bash
export MINI_JIRA_BACKEND_PORT=9000
export MINI_JIRA_FRONTEND_PORT=9001

python run.py
```

---

# Notes

This project is intentionally minimal and intended for local development and AI experimentation.

Current limitations:

* No authentication
* Local-only deployment
* No real-time push updates (the UI polls every 5 seconds)
* No Docker setup required

---

# FastMCP Compatibility

The application currently mounts the MCP endpoint using:

```python
app.mount("/mcp", mcp.streamable_http_app())
```

Some FastMCP versions expose a different integration API, for example:

```python
mcp.mount_http(app, path="/mcp")
```

If the mount method differs in your installed FastMCP version, refer to the corresponding FastMCP documentation and update the integration accordingly.
