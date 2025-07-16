# MCP Agent Coordinator

A Model Context Protocol (MCP) server designed specifically for coordinating multiple AI agents working simultaneously on the same codebase within Cursor IDE. This system prevents conflicts, manages dependencies, and ensures organized parallel development.

## Why Agent Coordination Matters

When multiple AI agents work on the same project without coordination, they create chaos: file conflicts, duplicate work, broken dependencies, and inconsistent implementations. The Agent Coordinator solves this by introducing intelligent workflow management.

This architecture enables true parallel development where agents can:

- **Work simultaneously without conflicts** - Automatic file locking prevents multiple agents from editing the same files
- **Follow logical dependencies** - Tasks execute in the correct order, ensuring foundational work completes before dependent features
- **Maintain project coherence** - Centralized project structure keeps all agents aligned on goals and progress
- **Scale efficiently** - Add more agents to accelerate development without diminishing returns
- **Track comprehensive progress** - Real-time visibility into what's completed, in-progress, and pending

The system organizes work into Projects → Tasks → Todo Items, creating clear ownership and preventing the typical chaos of uncoordinated multi-agent development. Each agent receives specific, non-conflicting work assignments and automatically releases resources when complete.

## Installation

The project uses a Python virtual environment for easy setup. Everything is self-contained and ready to run.

**Windows:**
```
start.bat
```

**macOS/Linux:**
```
./start.sh
```

This automatically creates the virtual environment, installs dependencies, and starts the HTTP server on localhost:8001.

## Cursor Configuration

Add this to your Cursor MCP settings:

```json
{
  "mcpServers": {
    "agent-coordinator": {
      "url": "http://127.0.0.1:8001/sse"
    }
  }
}
```

## Essential Cursor Workflow

**It is pretty much required that you create a custom mode with or include the following prompt in all of your agents**

Instruction: "Before beginning any task, ensure that you use the agent-coordinator MCP, learn from the instructions, and establish your workflows from there."

## How It Works

The system manages three levels of organization:

**Projects** represent entire codebases or major initiatives. Each project contains multiple tasks and maintains overall progress tracking.

**Tasks** group related work items, similar to sprints in agile development. They define major milestones and can depend on other tasks to ensure proper sequencing.

**Todo Items** are individual units of work assigned to specific agents. They reference the files they'll modify and automatically lock those files to prevent conflicts.

When an agent requests work, the system finds the next available todo item with no blocking dependencies or file conflicts. The agent claims the work, the system locks relevant files, and other agents automatically receive different assignments. Upon completion, files unlock and dependent work becomes available.

This creates a self-organizing development environment where agents naturally coordinate without manual intervention, enabling truly scalable parallel development.

## Benefits

- **Eliminates merge conflicts** through automatic file locking
- **Prevents duplicate work** with centralized assignment tracking  
- **Maintains logical execution order** via dependency management
- **Scales to unlimited agents** without coordination overhead
- **Provides real-time progress visibility** for project managers
- **Reduces development time** through efficient parallel execution
- **Ensures consistent code quality** by maintaining project structure 