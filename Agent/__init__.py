import os
import time
import datetime

import shutil
from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.apps.app import App
from google.genai import types
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService, DatabaseSessionService
from google.adk.tools import load_memory, preload_memory

APP_NAME = "declutter_agent"
USER_ID = "user"
SESSION = "default"

MODEL_NAME = "gemini-2.5-flash-lite"

memory_service = (InMemoryMemoryService())

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

async def auto_save_to_memory(callback_context):
    """Automatically save session to memory after each agent turn."""
    await callback_context._invocation_context.memory_service.add_session_to_memory(
        callback_context._invocation_context.session
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


#   |---         |\  /|
#   |--- | L E   | \/ | A N A G E R
#   |            |    |
class file_manager():
    """A class that provides file management operations like copy and move."""
    
    @staticmethod
    def copy_file(source_path: str, destination_path: str) -> str:
        try:
            if not os.path.exists(source_path):
                return f"ERROR: Source file '{source_path}' not found."
            if not os.path.isfile(source_path):
                return f"ERROR: '{source_path}' is not a file."
            if os.path.isdir(destination_path):
                filename = os.path.basename(source_path)
                destination_path = os.path.join(destination_path, filename)
            
            dest_dir = os.path.dirname(destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                return "Invalid"
            
            # Copy the file
            shutil.copy2(source_path, destination_path)
            
            # Get file size for confirmation
            size_mb = os.path.getsize(destination_path) / (1024 * 1024)
            return f"SUCCESS: Copied '{source_path}' to '{destination_path}' ({size_mb:.2f} MB)"
        except PermissionError:
            return f"ERROR: Permission denied. Cannot copy to '{destination_path}'."
        except Exception as e:
            return f"ERROR: Failed to copy file. Reason: {str(e)}"
    
    @staticmethod
    def move_file(source_path: str, destination_path: str) -> str:
        """Move a file from source to destination."""
        forbidden_keywords = ["WINDOWS", "System32", ".git", ".ipynb_checkpoints"]
        if any(keyword in source_path for keyword in forbidden_keywords):
            return f"SAFETY ALERT: Moving '{source_path}' was blocked for safety reasons."
        try:
            if not os.path.exists(source_path):
                return f"ERROR: Source file '{source_path}' not found."
            
            if not os.path.isfile(source_path):
                return f"ERROR: '{source_path}' is not a file."
            
            # If destination is a directory, preserve the filename
            if os.path.isdir(destination_path):
                filename = os.path.basename(source_path)
                destination_path = os.path.join(destination_path, filename)
    
            dest_dir = os.path.dirname(destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                return "Destination Doesnt Exist"
            
            size_mb = os.path.getsize(source_path) / (1024 * 1024)
            shutil.move(source_path, destination_path)
            return f"SUCCESS: Moved '{source_path}' to '{destination_path}' ({size_mb:.2f} MB)"

        except PermissionError:
            return f"ERROR: Permission denied. Cannot move to '{destination_path}'."
        except Exception as e:
            return f"ERROR: Failed to move file. Reason: {str(e)}"
    
    @staticmethod
    def move_to_destination(source_path: str, destination_directory: str, create_subfolders: bool = False) -> str:
        """Move a file to a specific destination directory with options.
        """
        # Safety check for critical system files
        forbidden_keywords = ["WINDOWS", "System32", ".git", ".ipynb_checkpoints"]
        if any(keyword in source_path for keyword in forbidden_keywords):
            return f"SAFETY ALERT: Moving '{source_path}' was blocked for safety reasons."
        
        try:
            if not os.path.exists(source_path):
                return f"ERROR: Source file '{source_path}' not found."
            
            if not os.path.isfile(source_path):
                return f"ERROR: '{source_path}' is not a file."
            
            if not os.path.exists(destination_directory):
                if create_subfolders:
                    os.makedirs(destination_directory)
                    print(f"Created directory: {destination_directory}")
                else:
                    return f"ERROR: Destination directory '{destination_directory}' does not exist. Set create_subfolders=True to create it."
            
            if not os.path.isdir(destination_directory):
                return f"ERROR: '{destination_directory}' is not a directory."
            
            filename = os.path.basename(source_path)
            final_destination = os.path.join(destination_directory, filename)
            
            if os.path.exists(final_destination):
                return f"WARNING: File '{filename}' already exists in '{destination_directory}'. Move cancelled to prevent overwriting."
            
            # Get file size before moving
            size_mb = os.path.getsize(source_path) / (1024 * 1024)
            
            # Move the file
            shutil.move(source_path, final_destination)
            
            return f"SUCCESS: Moved '{filename}' to '{destination_directory}' ({size_mb:.2f} MB)"
            
        except PermissionError:
            return f"ERROR: Permission denied. Cannot access '{destination_directory}'."
        except Exception as e:
            return f"ERROR: Failed to move file. Reason: {str(e)}"
        
copy_file_tool = FunctionTool(file_manager.copy_file)
move_file_tool= FunctionTool(file_manager.move_file)
special_move_tool = FunctionTool(file_manager.move_to_destination)

# -------------------------------------------------------------
# TOOL 3: Additional Python-based file operations
# -------------------------------------------------------------
def list_directory(directory_path: str) -> str:
    """List all files and directories in the given path."""
    try:
        items = os.listdir(directory_path)
        if not items:
            return f"Directory '{directory_path}' is empty."
        
        result = [f"Contents of '{directory_path}':"]
        for item in items:
            full_path = os.path.join(directory_path, item)
            if os.path.isdir(full_path):
                result.append(f"[DIR]  {item}")
            else:
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                result.append(f"[FILE] {item} ({size_mb:.2f} MB)")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory: {e}"

list_dir_tool = FunctionTool(list_directory)

def get_file_info(file_path: str) -> str:
    """Get detailed information about a file."""
    try:
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
        stats = os.stat(file_path)
        size_mb = stats.st_size / (1024 * 1024)
        mod_time = datetime.datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        create_time = datetime.datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
        
        return f"""File Information for: {file_path}
Size: {size_mb:.2f} MB
Last Modified: {mod_time}
Created: {create_time}
"""
    except Exception as e:
        return f"Error getting file info: {e}"

file_info_tool = FunctionTool(get_file_info)
    
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
    output_key="deletion_report",
    after_agent_callback=auto_save_to_memory,

)

# -----------------------------------------------------
# SEQUENTIAL AGENT : LISTING AGENT -> HUMAN APPROVAL AGENT
# ----------------------------------------------------
declutter_agent = SequentialAgent(
    name="Declutter_Pipeline",
    description="First scans for old files, then asks for permission to delete them.",
    sub_agents=[Listing_Agent, Archive_or_delete],
)

# --------------------------------------------------------
# File Ops Ag
# --------------------------------------------------------
File_Operations_Agent = LlmAgent(
    name="File_Operations_Agent",
    description="Agent that provides file system operations using Python tools",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    instruction="""
    You are a File Operations Agent that helps users manage their local file system.
    
    CRITICAL INSTRUCTION - YOU MUST ALWAYS OUTPUT TOOL RESULTS:
    After calling ANY tool, you MUST immediately display the complete results to the user.
    DO NOT just acknowledge that you called a tool.
    DO NOT summarize - show the FULL output.
    
    Example correct behavior:
    User: "List the contents of C:\\Pictures"
    You: [Call list_directory tool]
    You: "Here are the contents of C:\\Pictures:
    
    [FILE] image1.jpg (2.5 MB)
    [FILE] image2.png (1.3 MB)
    [DIR] Vacation Photos
    [DIR] Family"
    
    Example WRONG behavior (DO NOT DO THIS):
    You: "I've listed the directory." 
    You: "The tool was called successfully." 
    
    YOUR CAPABILITIES:
    i. List directory contents - use list_directory tool
    ii. Get detailed file information - use get_file_info tool
    iii. Search for old files - use list_old_files tool
    iv. Delete files (with user approval) - use delete_file tool
    v. Copy files - use copy_file tool
    vi. Move files - use move_file tool
    vii. Move files to specific destinations - use move_to_destination tool
    
    FORMATTING RULES:
    - When showing directory listings: Display each file/folder on a new line
    - Preserve the [FILE] and [DIR] markers from the tool output
    - Include file sizes when available
    - Use clear section headers
    
    SAFETY RULES:
    - For deletions: ALWAYS ask for explicit confirmation before deleting
    - For moves: Confirm with user before moving (changes original location)
    - For copies: Can proceed without confirmation (original remains intact)
    - Show file details before any destructive operation
    - Only proceed after receiving clear "Yes" confirmation
    
    REMEMBER: Your job is to be the interface between the tools and the user. 
    Always show what the tools return!
    """,
    tools=[list_dir_tool, file_info_tool, old_files_tool, delete_tool, copy_file_tool, move_file_tool, special_move_tool],
    after_agent_callback=auto_save_to_memory,

)

# ------------------------------------------------
# ROOT AGENT
# ------------------------------------------------
root_agent = Agent(
    name="File_Manager",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    sub_agents=[declutter_agent, File_Operations_Agent],
    description="A file management agent that can route between decluttering and file system operations.",
    instruction="""You are a File Manager agent. You can help users with:
    - File decluttering: Delegate to 'Declutter_Pipeline' to scan and delete old files
    - File system operations: Delegate to 'File_Operations_Agent' for listing directories, getting file info, copying and moving files
    
    Route the user's request to the appropriate sub-agent based on what they need.""",
    tools=[preload_memory],
    after_agent_callback=auto_save_to_memory,
)

# ------------------------------------------------
# APP SETUP (for web server)
# ------------------------------------------------

session_service = InMemorySessionService()

runner = Runner(
    agent = root_agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=memory_service
)