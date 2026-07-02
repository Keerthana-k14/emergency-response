import os
import json
from dotenv import load_dotenv

load_dotenv()

from google.adk.apps import App
from google.adk.workflow._workflow import Workflow
from google.adk.workflow._graph import Edge, START
from google.adk.workflow._function_node import FunctionNode
from pydantic import BaseModel, Field
from google import genai
from app.config import config

# ---------------------------------------------------------------------------
# Structured output schemas for the AI Agents
# ---------------------------------------------------------------------------
class TriageDecision(BaseModel):
    severity: str = Field(description="The severity of the emergency: 'low', 'medium', or 'high'")
    emergency_type: str = Field(description="The type of emergency: 'medical', 'fire', 'police', or 'mixed'")
    required_responders: list[str] = Field(description="List of responders needed, e.g. ['ambulance', 'hospital', 'fire', 'police']")
    summary: str = Field(description="A concise 1-sentence summary of the situation")

class ResponderAction(BaseModel):
    action_taken: str = Field(description="The specific action the responder is taking based on the emergency")
    eta_minutes: int = Field(description="Estimated time of arrival in minutes")

class InstructionPlan(BaseModel):
    instructions: list[str] = Field(description="List of 3-5 short, actionable, real-time safety/first-aid instructions for the user while waiting.")

# ---------------------------------------------------------------------------
# Business logic using Gemini AI
# ---------------------------------------------------------------------------
def _get_gemini_client():
    # Fallback to dummy key if not set, but the user provided it in .env
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY not found in environment.")
    return genai.Client()

def orchestrator_logic(ctx, report: str) -> str:
    """Triage incoming emergency using Gemini."""
    client = _get_gemini_client()
    
    prompt = f"""
    You are an expert emergency 911 dispatcher. Analyze this emergency report:
    "{report}"
    
    Determine the severity, emergency type, and which responder agencies need to be dispatched.
    Respond strictly in JSON matching the schema.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': TriageDecision,
            },
        )
        triage = json.loads(response.text)
        
        # Save triage info into state for the responder agents
        ctx.state["report"] = report
        ctx.state["severity"] = triage.get("severity", "unknown")
        ctx.state["summary"] = triage.get("summary", "No summary provided")
        
        # Dynamically determine routes based on required responders
        routes = []
        responders = triage.get("required_responders", [])
        if "ambulance" in responders or triage.get("emergency_type") in ["medical", "mixed"]:
            routes.append("to_ambulance")
        if "hospital" in responders or triage.get("emergency_type") in ["medical", "mixed"]:
            routes.append("to_hospital")
        if "fire" in responders or triage.get("emergency_type") == "fire":
            routes.append("to_fire")
        if "police" in responders or triage.get("emergency_type") == "police":
            routes.append("to_police")
            
        if not routes:
            routes = ["to_police"] # Default fallback
            
        routes.append("to_instruction")
            
        ctx.route = routes
        return f"Triaged as {ctx.state['severity']} severity {triage.get('emergency_type')} emergency."
        
    except Exception as e:
        print(f"Error during AI triage: {e}")
        ctx.state["report"] = report
        ctx.state["severity"] = "unknown"
        ctx.route = ["to_ambulance", "to_hospital"]
        return "Fallback Triage executed due to AI error."

def responder_agent_logic(agency_name: str, ctx) -> str | None:
    """Generic logic for responder agents to generate an action plan."""
    client = _get_gemini_client()
    report = ctx.state.get("report", "Unknown emergency")
    severity = ctx.state.get("severity", "unknown")
    
    prompt = f"""
    You are the dispatcher for the {agency_name} department.
    An emergency has been reported with {severity.upper()} severity.
    Report details: "{report}"
    
    Formulate your response plan. 
    Respond strictly in JSON matching the schema.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': ResponderAction,
            },
        )
        plan = json.loads(response.text)
        action = plan.get("action_taken", "Dispatching units")
        eta = plan.get("eta_minutes", 5)
        
        if "responder_actions" not in ctx.state:
            ctx.state["responder_actions"] = []
        actions = list(ctx.state["responder_actions"])
        actions.append(f"[{agency_name}] Action: {action} (ETA: {eta} mins)")
        ctx.state["responder_actions"] = actions
        
        return None
    except Exception as e:
        if "responder_actions" not in ctx.state:
            ctx.state["responder_actions"] = []
        actions = list(ctx.state["responder_actions"])
        actions.append(f"[{agency_name}] Standard units dispatched to {report[:20]}...")
        ctx.state["responder_actions"] = actions
        return None

def ambulance_logic(ctx) -> str | None:
    return responder_agent_logic("Ambulance/EMS", ctx)

def hospital_logic(ctx) -> str | None:
    return responder_agent_logic("Hospital Coordinator", ctx)
    
def fire_logic(ctx) -> str | None:
    return responder_agent_logic("Fire Department", ctx)
    
def police_logic(ctx) -> str | None:
    return responder_agent_logic("Police Department", ctx)

def instruction_logic(ctx) -> str | None:
    """Provides real-time safety instructions while waiting for responders."""
    client = _get_gemini_client()
    report = ctx.state.get("report", "Unknown emergency")
    severity = ctx.state.get("severity", "unknown")
    
    prompt = f"""
    An emergency has been reported with {severity.upper()} severity.
    Report details: "{report}"
    
    Provide 3-5 critical, short, actionable safety or first-aid instructions for the caller to follow right now while waiting for help.
    Respond strictly in JSON matching the schema.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': InstructionPlan,
            },
        )
        plan = json.loads(response.text)
        instructions = plan.get("instructions", ["Stay calm and wait for help."])
        
        ctx.state["instructions"] = instructions
        
        return None
    except Exception as e:
        ctx.state["instructions"] = ["Stay calm.", "Ensure you are in a safe location.", "Wait for responders to arrive."]
        return None

# Wrap the functions as FunctionNode objects
orchestrator_node = FunctionNode(func=orchestrator_logic, name="Orchestrator")
ambulance_node = FunctionNode(func=ambulance_logic, name="Ambulance")
hospital_node = FunctionNode(func=hospital_logic, name="Hospital")
fire_node = FunctionNode(func=fire_logic, name="Fire")
police_node = FunctionNode(func=police_logic, name="Police")
instruction_node = FunctionNode(func=instruction_logic, name="Instruction")

# ---------------------------------------------------------------------------
# Build the ADK workflow graph
# ---------------------------------------------------------------------------
workflow = Workflow(
    name="emergency_workflow",
    edges=[
        Edge(from_node=START, to_node=orchestrator_node),
        Edge(from_node=orchestrator_node, to_node=ambulance_node, route="to_ambulance"),
        Edge(from_node=orchestrator_node, to_node=hospital_node, route="to_hospital"),
        Edge(from_node=orchestrator_node, to_node=fire_node, route="to_fire"),
        Edge(from_node=orchestrator_node, to_node=police_node, route="to_police"),
        Edge(from_node=orchestrator_node, to_node=instruction_node, route="to_instruction"),
    ],
)

root_agent = workflow

app = App(
    root_agent=workflow,
    name="app",
)
