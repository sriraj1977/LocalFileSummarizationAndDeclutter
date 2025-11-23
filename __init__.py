import os
import time
import datetime

from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.adk.apps.app import App, EventsCompactionConfig
from google.genai import types
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

APP_NAME = "File Manager"
USER_ID = "Default"
SESSION = "default"

MODEL_NAME = "gemini-2.5-flash-lite"

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

session_service = InMemorySessionService()


# -------------------------------------------------------------
# TOOL 1: list files older than X days
# -------------------------------------------------------------
def list_old_files(directory_path: str, days_threshold: int = 90):
    """Scan directory and return list of files older than X days."""
    now = time.time()
    cutoff = now - (days_threshold * 86400)
    old_files = []

    try:
        for root, dirs, files in os.walk(directory_path):
            for names in files:
                filepath = os.path.join(root, names)
                try:
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < cutoff:
                        mod_time = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d')
                        size_mb = os.path.getsize(filepath) / (1024 * 1024)
                        old_files.append(f"{filepath} (Last modified: {mod_time}, Size: {size_mb:.2f} MB)")
                except OSError:
                    continue
    except Exception as e:
        return f"Error accessing directory: {e}"

    if not old_files:
        return "No files found exceeding that age limit."

    return "\n".join(old_files)


old_files_tool = FunctionTool(list_old_files)


# -------------------------------------------------------------
# TOOL 2: delete file safely
# -------------------------------------------------------------
def delete_file(file_path: str) -> str:
    """Safely delete a file."""
    forbidden_keywords = ["WINDOWS", "System32", ".git", ".ipynb_checkpoints"]
    if any(keyword in file_path for keyword in forbidden_keywords):
        return f"SAFETY ALERT: Deletion of '{file_path}' was blocked."

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return f"SUCCESS: Deleted {file_path}"
        else:
            return f"ERROR: File not found."
    except Exception as e:
        return f"ERROR: Could not delete file. Reason: {str(e)}"


delete_tool = FunctionTool(delete_file)


# -------------------------------------------------------------
# AGENT 1: Listing Specialist
# -------------------------------------------------------------
Listing_Agent = Agent(
    name="Listing_Specialist",
    model=Gemini(model=MODEL_NAME, retry_options=retry_config),
    description="Scans a directory and lists old files.",
    tools=[old_files_tool],
    instruction="""
    You are a File System Auditor.

    RULES:
    1. If user does not provide a directory path, reply EXACTLY:
       STATUS: NEED_PATH
    2. If a path is provided, use the tool 'list_old_files'.
    3. Output a clear numbered list.
    """,
    output_key="found_files_list"
)


# -------------------------------------------------------------
# AGENT 2: Approval + Deletion Agent
# -------------------------------------------------------------
Archive_or_delete = Agent(
    name="Human_Approval_Agent",
    model=Gemini(model=MODEL_NAME, retry_options=retry_config),
    description="Gets list of old files, asks user for deletion permission.",
    tools=[delete_tool],
    instruction="""
    You decide what happens to the scanned files.

    If input is EXACTLY "STATUS: NEED_PATH":
        Ask: "Please provide the directory path to scan."

    If input says "No files found":
        Tell the user: "No old files found."

    If files ARE listed:
        Show the list.
        Ask user: "Do you want to DELETE these files? (Yes/No)"

    If user says YES:
        Use 'delete_file' to delete each selected file.
        Confirm completion.
    """,
    output_key="deletion_report"
)


# -------------------------------------------------------------
# SEQUENTIAL PIPELINE
# -------------------------------------------------------------
deleting_agent = SequentialAgent(
    name="sequential_deleting_agent",
    description="Scans for old files, then asks for deletion.",
    sub_agents=[Listing_Agent, Archive_or_delete],
)


# -------------------------------------------------------------
# FILESYSTEM MCP SERVER
# -------------------------------------------------------------
mcp_args = ["-y", "@modelcontextprotocol/server-filesystem"]

file_system_mcp_server = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=mcp_args,
        ),
        timeout=30,
    )
)


# -------------------------------------------------------------
# ROOT AGENT
# -------------------------------------------------------------
root_agent = Agent(
    name="Manager_Agent",
    model=Gemini(model=MODEL_NAME),
    instruction="""
        You are the top-level file management supervisor.
        If the user requests ANY cleanup or file operation:
        → USE the 'sequential_deleting_agent' tool.
        
        For non-file questions, answer normally.
    """,
    tools=[deleting_agent, file_system_mcp_server]
)





# -------------------------------------------------------------
# RUNNER
# -------------------------------------------------------------
runner = InMemoryRunner(app=root_agent)
