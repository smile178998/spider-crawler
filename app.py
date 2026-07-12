#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web Scraper — FastAPI web application."""

import asyncio
import json
import queue
import threading
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scraper_core import run_pipeline

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Modern Web Scraper", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class ScrapeRequest(BaseModel):
    url: str
    text_selector: str = ""
    comment_selector: str = ""
    cookie: str = ""
    wait_ms: int = Field(default=2500, ge=500, le=12000)
    scroll: bool = True


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(
        (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    )


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
    url = req.url.strip()
    if not url:
        return {"error": "URL is required"}

    if not urlparse(url).scheme:
        url = "https://" + url

    log_q: queue.Queue = queue.Queue()

    def worker():
        run_pipeline(
            url,
            req.text_selector.strip(),
            req.comment_selector.strip(),
            req.cookie.strip(),
            req.wait_ms,
            req.scroll,
            log_q,
        )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def event_stream():
        while thread.is_alive() or not log_q.empty():
            try:
                kind, payload = log_q.get_nowait()
                data = json.dumps(
                    {"type": kind, "data": payload},
                    ensure_ascii=False,
                )
                yield f"data: {data}\n\n"
                if kind in ("done", "error"):
                    return
            except queue.Empty:
                await asyncio.sleep(0.1)

        while not log_q.empty():
            try:
                kind, payload = log_q.get_nowait()
                data = json.dumps(
                    {"type": kind, "data": payload},
                    ensure_ascii=False,
                )
                yield f"data: {data}\n\n"
                if kind in ("done", "error"):
                    return
            except queue.Empty:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
