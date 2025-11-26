import os
import time
import datetime
import asyncio

from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.apps.app import App
from google.genai import types
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

APP_NAME = "declutter_agent"
USER_ID = "user"
SESSION = "default"

MODEL_NAME = "gemini-2.5-flash-lite"

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

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
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config), 
    description="A specialist agent that scans storage to identify old files.", 
    instruction="""
    You are a File System Auditor. Your ONLY job is to identify files that are candidates for deletion.

    YOUR PROTOCOL:
    1. Receive a directory path from the user.
    2. CRITICAL: If no path is provided, output EXACTLY: "STATUS: NEED_PATH". 
       (Do NOT ask the user yourself. Stay silent.)
    3. If a path IS provided, use 'list_old_files' to scan it.
    4. Output the result as a clear, numbered list.""",
    tools=[old_files_tool],
    output_key="found_files_list"
)
# -------------------------------------------------------------
# AGENT 2: Approval + Deletion Agent
# -------------------------------------------------------------
Archive_or_delete = Agent(
    name="Human_Approval_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    description="A manager agent that reviews the scan results and executes deletion.",
    tools=[delete_tool],
    instruction="""
    You are the Final Decision Maker. You are the ONLY one allowed to speak to the user.
    
    CONTEXT: You have received output from the Listing_Specialist.

    YOUR PROTOCOL:
    1. ANALYZE the input:
       - IF input is "STATUS: NEED_PATH": Ask the user "Please provide the directory path you would like me to scan."
       - IF input says "No files found": Tell the user "No old files found." and stop.
       
    2. IF files are listed:
       - Present them to the user.
       - Ask: "Do you want to DELETE these files? (Yes/No)"

    3. IF User replies "Yes": 
       - Use 'delete_file' tool.
       - Confirm completion.
    """,
    output_key="deletion_report"
)

# -----------------------------------------------------
# SEQUENTIAL AGENT : LISTING AGENT -> HUMAN APPROVAL AGENT
# ----------------------------------------------------
declutter_agent = SequentialAgent(
    name="Declutter_Pipeline",
    description="First scans for old files, then asks for permission to delete them.",
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

# ------------------------------------------------
# Summary Agent 
# ------------------------------------------------
Summary_agent = LlmAgent(
    name="Summary_Agent",
    description="Summary Agent that analyzes the directory and gives details of the files",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    instruction="""
    You are Manager Agent that works to manage file in the local file system. When you are called you can tell them what you can do.
    these are the features you can achieve:
    i. Read/write files
    ii. Create/list/delete directories
    iii. Move files/directories
    iv. Search files
    v. Get file metadata
    vi. Dynamic directory access control via Roots
    """,
    tools=[file_system_mcp_server]
)

# ------------------------------------------------
# ROOT AGENT
# ------------------------------------------------
root_agent = Agent(
    name="File_Manager",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    sub_agents=[declutter_agent, Summary_agent],
    description="A file management agent that can route between decluttering and file system operations.",
    instruction="""You are a File Manager agent. You can help users with:
    - File decluttering: Delegate to 'Declutter_Pipeline' to scan and delete old files
    - File system operations: Delegate to 'Summary_Agent' for reading, writing, listing, and managing files
    
    Route the user's request to the appropriate sub-agent based on what they need.""",
)

# ------------------------------------------------
# APP SETUP (for web server)
# ------------------------------------------------
app = App(
    name=APP_NAME,  
    root_agent=root_agent,
)

# ------------------------------------------------
# SESSION SERVICE (Singleton pattern for web server compatibility)
# ------------------------------------------------
_session_service_instance = None

def get_session_service():
    """Returns a singleton session service instance."""
    global _session_service_instance
    if _session_service_instance is None:
        _session_service_instance = InMemorySessionService()
    return _session_service_instance

# ------------------------------------------------
# HELPER FUNCTION FOR COMMAND LINE TESTING
# ------------------------------------------------
async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
):
    """Helper function for testing via command line."""
    print(f"{session_name}")
    app_name = runner_instance.app_name
    session_service = get_session_service()

    # Get or create session
    try:
        session = await session_service.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )
        print(f"Using existing session: {session.id}")
    except Exception:
        session = await session_service.create_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )
        print(f"Created new session: {session.id}")

    if user_queries:
        if isinstance(user_queries, str):
            user_queries = [user_queries]

        for query in user_queries:
            print(f"\nUser > {query}")
            query_content = types.Content(role="user", parts=[types.Part(text=query)])

            async for event in runner_instance.run_async(
                user_id=USER_ID, 
                session_id=session.id, 
                new_message=query_content
            ):
                if event.content and event.content.parts:
                    text = event.content.parts[0].text
                    if text and text != "None":
                        print(f"{MODEL_NAME} > {text}")
    else:
        print("No queries provided!")

# ------------------------------------------------
# COMMAND LINE EXECUTION
# ------------------------------------------------
if __name__ == "__main__":
    session_service = get_session_service()
    runner = Runner(
        agent=root_agent, 
        app_name=APP_NAME, 
        session_service=session_service
    )
    asyncio.run(
        run_session(
            runner,["Hi! Can you help me declutter old files?","What can you do for me?"],
            "file-management-session"
        )
    )