from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from jira_foundry_agent.agent import run_agent
from jira_foundry_agent.settings import settings


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)


class ChatResponse(BaseModel):
    response: str


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>JiraLite Foundry Agent</title>
<style>body{font-family:system-ui;max-width:850px;margin:3rem auto;padding:0 1rem;color:#172033}textarea{box-sizing:border-box;width:100%;min-height:130px;padding:.8rem;font:inherit}button{margin-top:.75rem;background:#1264d6;color:white;border:0;border-radius:.35rem;padding:.7rem 1rem;font:inherit;cursor:pointer}pre{white-space:pre-wrap;background:#f4f6f8;padding:1rem;border-radius:.35rem;min-height:4rem}</style>
</head><body><h1>JiraLite Foundry Agent</h1><p>The app and MCP tools run locally. Azure AI Foundry is used only for model inference.</p><textarea id="message" placeholder="Example: List all blocked tickets."></textarea><br><button id="send">Send</button><h2>Response</h2><pre id="response">Ready.</pre>
<script>const b=document.getElementById('send'),m=document.getElementById('message'),o=document.getElementById('response');b.onclick=async()=>{b.disabled=true;o.textContent='Working…';try{const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:m.value})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Request failed');o.textContent=d.response}catch(e){o.textContent='Error: '+e.message}finally{b.disabled=false}};</script></body></html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="JiraLite Foundry Agent", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PAGE

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mcp_url": settings.jira_mcp_url}

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        try:
            return ChatResponse(response=await run_agent(request.message))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Agent request failed: {exc}") from exc

    return app


def main() -> None:
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
