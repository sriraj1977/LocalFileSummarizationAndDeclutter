from . import agent
import os

import time
import datetime

from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.adk.apps.app import App, EventsCompactionConfig
from google.genai import types

from google.adk.models.google_llm import Gemini
from google.adk.sessions import InMemorySessionService
from google.adk.sessions import DatabaseSessionService
from google.adk.runners import Runner
from google.adk.tools.tool_context import ToolContext

# print("✅ ADK components imported successfully.")
APP_NAME = "default"  # Application
USER_ID = "default"  # User
SESSION = "default"  # Session

MODEL_NAME = "gemini-2.5-flash-lite"

retry_config = types.HttpRetryOptions(
    attempts=5,  
    exp_base=7,  # Delay multiplier
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],  
)

# Initialize the session service (In-memory or Database)
session_service = InMemorySessionService()
# Define helper functions that will be reused throughout the notebook
async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
):
    print(f"\n ### Session: {session_name}")

    # Get app name from the Runner
    app_name = runner_instance.app_name

    # Attempt to create a new session or retrieve an existing one
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )
    except:
        session = await session_service.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )

    # Process queries if provided
    if user_queries:
        # Convert single query to list for uniform processing
        if type(user_queries) == str:
            user_queries = [user_queries]

        # Process each query in the list sequentially
        for query in user_queries:
            print(f"\nUser > {query}")

            # Convert the query string to the ADK Content format
            query = types.Content(role="user", parts=[types.Part(text=query)])

            # Stream the agent's response asynchronously
            async for event in runner_instance.run_async(user_id=USER_ID, session_id=session.id, new_message=query):
                # Check if the event contains valid content
                if event.content and event.content.parts:
                    # Filter out empty or "None" responses before printing
                    if (
                        event.content.parts[0].text != "None"
                        and event.content.parts[0].text
                    ):
                        print(f"{MODEL_NAME} > ", event.content.parts[0].text)
    else:
        print("No queries!")



# File Finder : Tool 1 
def list_old_files (directory_path : str, days_threshold: int = 90) :
    """ Scan the directory and find the files that are older than 90 days (specified) and return the list with file path and their size"""
    now = time.time()      
    cutoff = now - (days_threshold * 86400) 
    old_files = []

    try :
        for root, dirs, files in os.walk(directory_path) :
            for names in files:
                filepath = os.path.join(root, names)             #file path  =  path + file name
                try :
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < cutoff:
                        # Convert timestamp to readable date
                        mod_time = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d')
                        size_mb = os.path.getsize(filepath)/(1024 * 1024)
                        old_files.append(f"{filepath} (Last modified: {mod_time}, Size: {size_mb:.2f} MB)")
                        
                except OSError:
                    continue # Skip files we can't access
                    
    except Exception as e:
        return f"Error accessing directory: {e}"

    if not old_files:
        return "No files found exceeding that age limit."
    
    return "\n".join(old_files)




# Here we Need Delete file tool ---------------Python Code----------------❗❗❗❗❗❗
def delete_file(file_path: str) -> str:
    """
    Permanently deletes a specific file from the file system.
    Args:
        file_path (str): The absolute path of the file to delete.
    Returns:
        str: A status message indicating success or error.
    """
    # Safety Guard: Prevent deleting common system critical paths ❗❗❗❗❗[add  protected path here]
    forbidden_keywords = ["WINDOWS", "System32", ".git", ".ipynb_checkpoints"]
    if any(keyword in file_path for keyword in forbidden_keywords):
        return f"SAFETY ALERT: Deletion of '{file_path}' was blocked for safety."
    try:
        if os.path.exists(file_path):
            os.remove(file_path) # <--- The actual delete command
            return f"SUCCESS: Deleted {file_path}"
        else:
            return f"ERROR: File not found at {file_path}"
    except Exception as e:
        return f"ERROR: Could not delete file. Reason: {str(e)}"
    
# --- Worker Agent (The Scanner) ---
Listing_Agent = LlmAgent(
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
    
    output_key="found_files_list" # Changed variable name to be Pythonic
)

# --- Manager Agent (The Decision Maker) ---
Archive_or_delete = LlmAgent(
    name="Human_Approval_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    description="A manager agent that reviews the scan results and executes deletion.",
    tools=[delete_file], # ONLY needs the delete tool now
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

print(" Deletion Agent defined")

root_agent = SequentialAgent(
    name="Declutter_Pipeline",
    description="First scans for old files, then asks for permission to delete them.",
    sub_agents=[Listing_Agent, Archive_or_delete],
)

decluttering_app = App(
    name="Declutterer_Pro",
    root_agent=root_agent,
)

