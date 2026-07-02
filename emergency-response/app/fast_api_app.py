# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
import uuid
from collections.abc import AsyncIterator

import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.app_utils.reasoning_engine_adapter import (
    attach_reasoning_engine_routes,
)
from app.app_utils.telemetry import (
    setup_agent_engine_telemetry,
    setup_telemetry,
)
from app.app_utils.typing import Feedback

load_dotenv()
setup_telemetry()
# Must run before get_fast_api_app to set the tracer provider resource.
try:
    setup_agent_engine_telemetry()
    _, project_id = google.auth.default()
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
except Exception as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    std_logger = logging.getLogger(__name__)
    class FallbackLogger:
        def __init__(self, l):
            self._l = l
        def log_struct(self, struct, severity="INFO"):
            self._l.info(f"[{severity}] {struct}")
        def info(self, msg):
            self._l.info(msg)
        def error(self, msg):
            self._l.error(msg)
        def warning(self, msg):
            self._l.warning(msg)
    logger = FallbackLogger(std_logger)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReportPayload(BaseModel):
    name: str
    location: str
    description: str


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runner for the A2A path, sharing the same session/artifact services as the
    # adk_api and reasoning_engine paths (see services.py). Imported here so the
    # agent is built after env/telemetry setup.
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    # Shared by the A2A path and the reasoning_engine adapter routes.
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=services.SESSION_SERVICE_URI,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    lifespan=lifespan,
    allow_origins=["*"],
    web=False,
)


# Proxy routes so the Vertex AI Console Playground (reasoning_engine SDK) can
# talk to this agent alongside the native adk_api routes.
attach_reasoning_engine_routes(app)


import sqlite3
import csv
from io import StringIO
from fastapi.responses import StreamingResponse

DB_FILE = "emergency_reports.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                location TEXT,
                description TEXT,
                severity TEXT,
                emergency_type TEXT,
                responses TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
init_db()

@app.post("/report")
async def receive_report(payload: ReportPayload):
    """Accept emergency report from frontend and log it."""
    logger.log_struct({
        "type": "emergency_report",
        "name": payload.name,
        "location": payload.location,
        "description": payload.description,
        "service": "emergency-response",
    }, severity="INFO")

    # Trigger the workflow runner
    user_id = f"user_{uuid.uuid4()}"
    session_service = services.get_session_service()
    
    # Initialize the session state with the report
    session = await session_service.create_session(
        app_name=app.state.agent_app_name,
        user_id=user_id,
        state={"report": f"Emergency at {payload.location}: {payload.description} (Reported by {payload.name})"}
    )
    
    from google.genai import types
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Trigger emergency workflow")]
    )
    
    events = []
    outputs = []
    
    # These will capture the AI triage output to save in DB
    severity = "unknown"
    emergency_type = "unknown"
    instructions = []
    
    async for event in app.state.runner.run_async(
        new_message=message,
        user_id=user_id,
        session_id=session.id,
    ):
        events.append(event)
        try:
            data = event.model_dump()
            author = data.get("node_info", {}).get("path", "").split("@")[0].split("/")[-1] or data.get("author") or "Workflow"
            
            if data.get("output"):
                outputs.append(f"[{author}] Completed with: {data.get('output')}")
            
            state_delta = data.get("actions", {}).get("state_delta")
            if state_delta:
                if 'severity' in state_delta:
                    severity = state_delta['severity']
                if 'responder_actions' in state_delta:
                    for action in state_delta['responder_actions']:
                        if action not in outputs:
                            outputs.append(action)
                if 'instructions' in state_delta:
                    instructions = state_delta['instructions']
        except Exception:
            pass
            
    # Attempt to extract emergency_type from outputs (since orchestrator returns it in the string)
    for out in outputs:
        if "Triaged as" in out and "emergency" in out:
            try:
                emergency_type = out.split("severity ")[1].split(" emergency")[0]
            except Exception:
                pass
                
    # Save to Database
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO reports (name, location, description, severity, emergency_type, responses) VALUES (?, ?, ?, ?, ?, ?)",
            (payload.name, payload.location, payload.description, severity, emergency_type, "\\n".join(outputs))
        )
        
    return {
        "status": "received",
        "detail": "Report logged and workflow executed",
        "session_id": session.id,
        "events_count": len(events),
        "outputs": outputs,
        "instructions": instructions,
    }

@app.get("/export")
async def export_csv():
    """Export the SQLite database to CSV for Kaggle."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports")
        rows = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        
    f = StringIO()
    writer = csv.writer(f)
    writer.writerow(column_names)
    writer.writerows(rows)
    f.seek(0)
    
    return StreamingResponse(
        iter([f.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=emergency_dataset.csv"}
    )


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
