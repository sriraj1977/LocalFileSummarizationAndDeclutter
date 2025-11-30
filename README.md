# Local File Summarization and Declutter

## Project Description

   This project implements an AI-powered File System Agent designed to help users efficiently manage and declutter their local file systems. Leveraging Google’s Gemini large language models and the Model Context Protocol (MCP), the agent can intelligently scan directories, identify obsolete or redundant files, and safely perform file operations such as listing, moving, copying, and deleting files. The system features a modular, agent-based architecture with human-in-the-loop approval for all destructive actions, ensuring both safety and transparency. With a conversational interface and robust safety checks, this agent streamlines file management tasks while minimizing the risk of accidental data loss.

# Installation Instructions

## 1. Clone the Repository
```sh
git clone https://github.com/sriraj1977/LocalFileSummarizationAndDeclutter.git
cd LocalFileSummarizationAndDeclutter
```

## 2. Python Environment Setup
- Install Python 3.9+ (recommended: 3.10 or 3.11)
- (Optional but recommended) Create a virtual environment:
```sh
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```
- Install Python dependencies:
```sh
pip install -r requirements.txt
```

## 3. Node.js & MCP Setup
- Install Node.js (v18+ recommended):
	- [Download Node.js](https://nodejs.org/)
- Ensure `npx` is available in your PATH:
```sh
npx --version
```
- (Optional) Install MCP globally if needed:
```sh
npm install -g @modelcontextprotocol/server-filesystem
```

## 4. Google ADK Setup
- Install the Google ADK Python package (if not included in requirements):
```sh
pip install google-adk  # or as specified in requirements.txt
```
- Ensure you have access to Gemini models (API keys or service account as required by your org).

## 5. Environment Variables
- Set the `PERMITTED_DIRS` environment variable to restrict file system access:
```sh
export PERMITTED_DIRS="/path/to/dir1:/path/to/dir2"
```
- On Windows:
```bat
set PERMITTED_DIRS=C:\path\to\dir1;C:\path\to\dir2
```

## 6. Run the Agent
- Start the agent (example for FileManager_Agent):
```sh
python -m FileManager_Agent
```
- Or for other agents as needed.

---

# Design Specification & Architecture

## Category 1: The Pitch
### Problem
Modern file systems accumulate clutter, making it hard for users to identify, manage, and safely delete obsolete files. Manual cleanup is error-prone and time-consuming.

### Solution
An AI-powered agent that audits, summarizes, and declutters local file systems. It leverages advanced LLMs (Gemini) and the Model Context Protocol (MCP) to provide safe, auditable, and user-approved file operations.

### Value
- Saves time by automating file audits and cleanup
- Reduces risk of accidental data loss with human-in-the-loop approval
- Provides transparency and traceability for all file operations

## Core Concept & Value
- **AI-Driven File Management:** Uses Gemini LLMs for intelligent file analysis and user interaction.
- **Safe Operations:** All destructive actions (delete/move) require explicit user approval.
- **Extensible Tooling:** Modular agent design allows for easy extension and integration.
- **MCP Integration:** Secure, protocol-driven file system access.

## Technical Implementation

### Architecture Overview
- **Agents:**
	- `Listing_Specialist`: Scans directories for old files.
	- `Human_Approval_Agent`: Reviews and approves deletions.
	- `File_Operations_Agent`: Handles listing, info, copy, move, and delete operations.
	- `Declutter_Pipeline`: Sequential agent combining listing and approval.
	- `File_Manager`: Root agent routing requests to the appropriate sub-agent.
- **MCP Toolset:** Used for secure, protocol-based file system access via Node.js and npx.
- **Gemini Models:** All agent reasoning and user interaction is powered by Gemini (e.g., gemini-2.5-flash-lite).
- **Environment Variables:** `PERMITTED_DIRS` restricts file system access for safety.

### Effective Use of Gemini
- Gemini models are used for:
	- Natural language understanding of user requests
	- Intelligent file selection and summarization
	- Human-like, safe, and transparent user interaction
	- Decision-making in the declutter pipeline
- The agent leverages Gemini's advanced reasoning to ensure only safe, user-approved actions are performed, and all outputs are clear and actionable.

## Screenshots
- See the included screenshots for UI, agent flow, and user interaction examples.

---

## How to Extend
- Add new tools by implementing Python functions and wrapping them with `FunctionTool`.
- Add new agents or sub-agents for specialized workflows.
- Integrate with other LLMs or protocols as needed.

---

## Contact
For questions or contributions, open an issue or PR on the GitHub repository.




