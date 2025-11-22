#!/usr/bin/env python3
"""
Example: Using Version Tools in an Agent

This script demonstrates how to create an agent that can manage versions
using the version tools provided by the version bumper module.
"""

from tools.versionTools import VERSION_TOOLS
from langchain_core.tools import BaseTool
from typing import List

def example_add_version_tools_to_agent():
    """
    Example of adding version tools to an agent's tool list.
    
    In practice, this would be done in the create_agent function
    or through the agent configuration UI.
    """
    
    # Start with existing agent tools
    agent_tools: List[BaseTool] = []
    
    # ... add other agent-specific tools ...
    
    # Add version management tools
    agent_tools.extend(VERSION_TOOLS)
    
    print("Version tools added to agent:")
    for tool in VERSION_TOOLS:
        print(f"  - {tool.name}: {tool.description[:80]}...")
    
    return agent_tools

def example_version_tool_usage():
    """
    Example of how an agent would use version tools in conversation.
    """
    
    examples = [
        {
            "user_query": "What's the current version?",
            "agent_action": "get_project_version",
            "expected_response": "The current version is 0.3.7"
        },
        {
            "user_query": "I fixed a bug, please bump the patch version",
            "agent_action": "bump_version_patch",
            "expected_response": "Version bumped from 0.3.7 to 0.3.8"
        },
        {
            "user_query": "We're releasing a new feature, bump the minor version",
            "agent_action": "bump_version_minor",
            "expected_response": "Version bumped from 0.3.8 to 0.4.0"
        },
        {
            "user_query": "Time for version 1.0! Bump the major version",
            "agent_action": "bump_version_major",
            "expected_response": "Version bumped from 0.4.0 to 1.0.0"
        }
    ]
    
    print("\nExample Agent Interactions:")
    print("=" * 70)
    for i, example in enumerate(examples, 1):
        print(f"\nExample {i}:")
        print(f"  User: {example['user_query']}")
        print(f"  Agent uses: {example['agent_action']}")
        print(f"  Agent: {example['expected_response']}")
    print("=" * 70)

def example_system_prompt():
    """
    Example system prompt for a version management agent.
    """
    
    system_prompt = """
You are a version management assistant for the Mattin AI Core Tools project.
You help manage semantic versioning (MAJOR.MINOR.PATCH) for the project.

Your capabilities:
1. Check the current project version
2. Bump the patch version (for bug fixes)
3. Bump the minor version (for new features)
4. Bump the major version (for breaking changes)

Guidelines:
- Always check the current version before bumping
- Ask for confirmation unless the user is explicit about the bump type
- Explain what the version bump means (patch/minor/major)
- Report both old and new versions after a bump

Semantic versioning rules:
- PATCH (x.x.X): Bug fixes and small improvements
- MINOR (x.X.0): New features, backward-compatible
- MAJOR (X.0.0): Breaking changes, incompatible API changes
"""
    
    return system_prompt

if __name__ == "__main__":
    print("Version Bumper Agent - Usage Examples")
    print("=" * 70)
    
    # Example 1: Adding tools
    print("\n1. Adding Version Tools to Agent:")
    print("-" * 70)
    tools = example_add_version_tools_to_agent()
    
    # Example 2: Usage scenarios
    example_version_tool_usage()
    
    # Example 3: System prompt
    print("\n2. Recommended System Prompt:")
    print("-" * 70)
    print(example_system_prompt())
    
    print("\nTo integrate this in the Mattin AI system:")
    print("1. Create a new agent via the UI or API")
    print("2. Set the system prompt to include version management instructions")
    print("3. Add version tools to the agent's tool list")
    print("4. The agent will be able to manage versions through conversation")
