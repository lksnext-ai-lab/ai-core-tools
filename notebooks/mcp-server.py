# math_server.py
from typing import List
from fastmcp import FastMCP

mcp = FastMCP("Weather",  )



@mcp.tool()
async def get_weather(location: str) -> str:
    """Get weather for location."""
    print(location)
    return f"It's always sunny in {location}"

if __name__ == "__main__":
    mcp.mount("/api", transport="sse")
    
    mcp.run(transport="sse")
