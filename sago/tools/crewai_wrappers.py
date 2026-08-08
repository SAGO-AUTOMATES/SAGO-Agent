"""CrewAI Tool Wrappers - Convert Sago tools to CrewAI format."""

from __future__ import annotations

from typing import Any

from crewai.tools import tool as crewai_tool
from pydantic import Field


def create_crewai_tool(sago_tool_class: type) -> Any:
    """Create a CrewAI tool from a Sago tool class.
    
    Args:
        sago_tool_class: A Sago tool class that inherits from BaseTool.
        
    Returns:
        A CrewAI-compatible tool instance.
    """
    tool_instance = sago_tool_class()
    
    @crewai_tool(tool_instance.name)
    def wrapped_tool(**kwargs: Any) -> str:
        """Wrapped Sago tool."""
        return tool_instance.run(**kwargs)
    
    # Update metadata
    wrapped_tool.description = tool_instance.description
    return wrapped_tool


# Pre-built CrewAI tools for common operations
@crewai_tool("write_file")
def write_file_tool(file_path: str, content: str) -> str:
    """Write content to a file. Creates the file if it doesn't exist, overwrites if it does.
    
    Args:
        file_path: Path to the file to write.
        content: Content to write to the file.
    
    Returns:
        Success or error message.
    """
    from sago.tools.file.write_file import WriteFileTool
    tool = WriteFileTool()
    return tool.run(file_path=file_path, content=content)


@crewai_tool("read_file")
def read_file_tool(file_path: str) -> str:
    """Read the contents of a file.
    
    Args:
        file_path: Path to the file to read.
    
    Returns:
        File contents or error message.
    """
    from sago.tools.file.read_file import ReadFileTool
    tool = ReadFileTool()
    return tool.run(file_path=file_path)


@crewai_tool("execute_shell")
def execute_shell_tool(command: str) -> str:
    """Execute a shell command and return the output.
    
    Args:
        command: Shell command to execute.
    
    Returns:
        Command output or error message.
    """
    from sago.tools.shell.execute import ExecuteShellTool
    tool = ExecuteShellTool()
    return tool.run(command=command)


@crewai_tool("edit_file")
def edit_file_tool(file_path: str, old_text: str, new_text: str) -> str:
    """Edit a file by replacing text.
    
    Args:
        file_path: Path to the file to edit.
        old_text: Text to find and replace.
        new_text: Text to replace with.
    
    Returns:
        Success or error message.
    """
    from sago.tools.file.edit_file import EditFileTool
    tool = EditFileTool()
    return tool.run(file_path=file_path, old_text=old_text, new_text=new_text)


@crewai_tool("directory_scanner")
def directory_scanner_tool(directory_path: str) -> str:
    """Scan a directory and return information about files and structure.
    
    Args:
        directory_path: Path to the directory to scan.
    
    Returns:
        Directory information as JSON.
    """
    from sago.tools.file.directory_scanner import DirectoryScanner
    tool = DirectoryScanner()
    result = tool.run(directory_path=directory_path)
    return str(result)


# Tool registry for easy access
CREWAI_TOOLS = {
    "write_file": write_file_tool,
    "read_file": read_file_tool,
    "execute_shell": execute_shell_tool,
    "edit_file": edit_file_tool,
    "directory_scanner": directory_scanner_tool,
}


def get_crewai_tool(tool_name: str) -> Any | None:
    """Get a CrewAI tool by name.
    
    Args:
        tool_name: Name of the tool.
        
    Returns:
        CrewAI tool or None if not found.
    """
    return CREWAI_TOOLS.get(tool_name)
