# ruff: noqa
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

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
from google.adk.workflow._workflow import Workflow
from google.adk.workflow._graph import Edge, START
from google.adk.workflow._function_node import FunctionNode

# ---------------------------------------------------------------------------
# Helper tools
# ---------------------------------------------------------------------------

def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"

# ---------------------------------------------------------------------------
# Orchestrator Agent (root)
# ---------------------------------------------------------------------------
orchestrator_agent = Agent(
    name="orchestrator",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="You coordinate emergency response agents and manage shared state.",
    tools=[get_weather, get_current_time],
)

root_agent = orchestrator_agent

# ---------------------------------------------------------------------------
# Business logic for the workflow
# ---------------------------------------------------------------------------
def orchestrator_logic(ctx, report: str) -> str:
    """Process incoming emergency report and store in shared state."""
    ctx.state["report"] = report
    ctx.state["severity"] = "high"
    return "orchestrator_done"

def ambulance_logic(ctx) -> str:
    """Dispatch ambulance based on report information."""
    report = ctx.state.get("report", "unknown location")
    print(f"[Ambulance] Dispatching to {report}")
    return "ambulance_done"

def hospital_logic(ctx) -> str:
    """Notify nearest hospital with patient info."""
    print("[Hospital] Notifying nearest hospital with patient details")
    return "hospital_done"

# Wrap the functions as FunctionNode objects
orchestrator_node = FunctionNode(func=orchestrator_logic, name="Orchestrator")
ambulance_node = FunctionNode(func=ambulance_logic, name="Ambulance")
hospital_node = FunctionNode(func=hospital_logic, name="Hospital")

# ---------------------------------------------------------------------------
# Build the ADK workflow graph
# ---------------------------------------------------------------------------
workflow = Workflow(
    name="emergency_workflow",
    edges=[
        Edge(from_node=START, to_node=orchestrator_node),
        Edge(from_node=orchestrator_node, to_node=ambulance_node, route="to_ambulance"),
        Edge(from_node=orchestrator_node, to_node=hospital_node, route="to_hospital"),
    ],
)
# No explicit start node method; START edge defines entry point

# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------
app = App(
    root_agent=orchestrator_agent,
    name="app",
)

# Attach the workflow to the app for execution
app.workflow = workflow
