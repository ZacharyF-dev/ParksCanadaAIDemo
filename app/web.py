from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def create_web_app() -> FastAPI:
    app = FastAPI(title="Mini Jira Web")
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse("static/index.html")

    return app