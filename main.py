"""
main.py - Entry point: FastAPI REST server + Gradio UI on the same port.
  /ui   → Gradio interactive interface
  /docs → FastAPI auto-docs
  /reset, /step, /state, /health → OpenEnv API
"""
from __future__ import annotations
import os
import uvicorn
import gradio as gr
from fastapi.responses import RedirectResponse


def create_app():
    from server import app as api_app
    from app import demo as gradio_demo

    combined = gr.mount_gradio_app(api_app, gradio_demo, path="/")

def run():
    port = int(os.environ.get("PORT", 7860))
    print(f"SRE OpenEnv  |  UI: http://localhost:{port}/ui  |  API: http://localhost:{port}/docs")
    uvicorn.run("main:create_app", factory=True, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run()
