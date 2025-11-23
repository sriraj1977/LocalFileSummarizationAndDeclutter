from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
import os
import ssl
import urllib3
import warnings
import datetime
from typing import Dict, Any
from pathlib import Path

# Fix SSL certificate issues
ssl._create_default_https_context = ssl._create_unverified_context

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

print("✅ SSL certificate verification disabled")


# ==========================================
# PYTHON CUSTOM FUNCTIONS (NO DECORATOR)
# ==========================================

def find_old_unaccessed_files(directory: str, days: int = 90) -> Dict[str, Any]:
    """
    Scans a directory recursively to find files not accessed since a specified cutoff time.

    Args:
        directory: The root directory to start scanning from.
        days: The cutoff age in days (files accessed before this will be listed).

    Returns:
        A dictionary containing the status and a list of unaccessed files.
    """
    print(f"🔍 Scanning directory: {directory} for files not accessed in {days} days...")

    # Input Validation
    if not os.path.isdir(directory):
        print(f"❌ Directory not found: {directory}")
        return {"status": "error", "message": f"Directory not found: {directory}"}

    if days <= 0:
        print(f"❌ Invalid days parameter: {days}")
        return {"status": "error", "message": "Days must be a positive number."}

    # Calculate cutoff timestamp
    cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days)
    unaccessed_files = []

    print(f"📅 Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Walk directory
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            file_count += 1
            filepath = os.path.join(dirpath, filename)

            try:
                st = os.stat(filepath)
                last_access = datetime.datetime.fromtimestamp(st.st_atime)

                if last_access < cutoff_time:
                    age_days = (datetime.datetime.now() - last_access).days

                    file_info = {
                        "path": filepath,
                        "last_accessed": last_access.strftime('%Y-%m-%d %H:%M:%S'),
                        "age_days": age_days,
                        "size_bytes": st.st_size,
                        "size_mb": round(st.st_size / (1024 * 1024), 2)
                    }
                    unaccessed_files.append(file_info)
                    print(f"📄 Found: {filepath} (Last accessed: {last_access.strftime('%Y-%m-%d')}, Size: {file_info['size_mb']} MB)")

            except Exception as e:
                print(f"⚠️  Could not access {filepath}: {e}")

    print(f"\n✅ Scan complete! Checked {file_count} files, found {len(unaccessed_files)} old files")

    if unaccessed_files:
        total_size_mb = sum(f['size_mb'] for f in unaccessed_files)
        return {
            "status": "success",
            "count": len(unaccessed_files),
            "total_size_mb": round(total_size_mb, 2),
            "total_size_gb": round(total_size_mb / 1024, 2),
            "cutoff_days": days,
            "files": unaccessed_files[:100],
            "message": f"Found {len(unaccessed_files)} files not accessed in the last {days} days. Total size: {round(total_size_mb / 1024, 2)} GB"
        }
    else:
        return {
            "status": "success",
            "count": 0,
            "files": [],
            "message": f"No files found not accessed in the last {days} days in {directory}."
        }


# ==========================================
# MCP FILE SYSTEM CONFIGURATION
# ==========================================

HOME = str(Path.home())

# Define permitted directories
PERMITTED_DIRECTORIES = [
    f"{HOME}/Downloads",
    f"{HOME}/Desktop",
    f"{HOME}/.Trash",
    f"{HOME}/WebGoat",
    f"{HOME}/THILAGA/Tickets",
]

# Validate directories
valid_directories = []
print("🔍 Validating permitted directories:")
for directory in PERMITTED_DIRECTORIES:
    if os.path.isdir(directory):
        valid_directories.append(directory)
        print(f"  ✅ {directory}")
    else:
        print(f"  ⚠️  Not found: {directory}")

if not valid_directories:
    print("❌ No valid directories found!")
    valid_directories = PERMITTED_DIRECTORIES  # Use anyway for demonstration

# Build MCP args
mcp_args = ["-y", "@modelcontextprotocol/server-filesystem"] + valid_directories

# Create MCP toolset
file_system_mcp_server = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=mcp_args,
        ),
        timeout=30,
    )
)

print(f"✅ MCP File System Tool created with {len(valid_directories)} permitted directories")

# ==========================================
# CREATE AGENT WITH MULTIPLE TOOLS
# ==========================================

root_agent = LlmAgent(
    name="filesystem_declutter_agent",
    model="gemini-2.0-flash-exp",

    description=f"""I am a file system decluttering agent with both MCP file system tools and custom Python analytics.

**Available Directories:**
{chr(10).join(f'- {d}' for d in valid_directories)}

**Capabilities:**
- List and browse directories (MCP tools)
- Find files not accessed in X days (Python function)
- Search, read, and move files
- Analyze storage usage
    """,

    instruction=f"""You are an expert file system decluttering assistant.

**AVAILABLE TOOLS:**

1. **Custom Python Function: find_old_unaccessed_files**
   - Use this to find files not accessed in a specified number of days
   - Parameters: 
     * directory (string, required) - Full path to directory
     * days (integer, optional, default 90) - Number of days threshold
   - Returns: Dictionary with status, count, and list of old files
   - Example usage: Call with directory="/Users/.../Downloads" and days=90

2. **MCP File System Tools:**
   - list_directory: Browse directory contents
   - read_file: Read file contents  
   - search_files: Search for files by pattern
   - move_file: Move or rename files
   - get_file_info: Get detailed file metadata
   - directory_tree: View hierarchical structure

**PERMITTED DIRECTORIES:**
{chr(10).join(f'- {d}' for d in valid_directories)}

**WORKFLOW FOR FINDING OLD FILES:**

1. When user asks to find old/unused files:
   - Identify which directory to scan
   - Determine the days threshold (default 90 if not specified)
   - Call find_old_unaccessed_files(directory="/full/path", days=90)

2. Present results clearly:
   - Total number of old files
   - Total space that could be freed (in GB)
   - List top 10-20 files by size
   - Sort by size or age

3. For other file operations, use MCP tools

**OUTPUT FORMAT:**

## 📊 Old Files Analysis
**Directory:** [path]
**Threshold:** [X] days
**Files Found:** [count]
**Total Space:** [size] GB

### Top Files to Consider:
1. [filename] - [size] MB - Last accessed: [date]
2. ...

Always be helpful and never delete files without explicit user confirmation.""",

    # Pass functions directly to tools array
    tools=[
        find_old_unaccessed_files,    # Python function (no decorator needed)
        file_system_mcp_server          # MCP toolset
    ]
)

# Debug info
if __name__ == "__main__":
    print("="*60)
    print("🚀 FILE SYSTEM DECLUTTER AGENT")
    print("="*60)
    print(f"Agent Name: {root_agent.name}")
    print(f"Model: {root_agent.model}")
    print(f"Tools configured: {len(root_agent.tools)}")
    print("  - 1 Python function (find_old_unaccessed_files)")
    print("  - 1 MCP toolset (file system operations)")
    print(f"Permitted directories: {len(valid_directories)}")
    for d in valid_directories:
        print(f"  • {d}")
    print("="*60)
    print("✅ Agent created successfully!")
    print("\nTo use: adk web .")
    print("\nTest prompts:")
    print(f'  "Find files in {valid_directories[0]} not accessed in 90 days"')
    print(f'  "Scan {valid_directories[1]} for files not used in 180 days"')
    print('  "List all files in my Desktop directory"')