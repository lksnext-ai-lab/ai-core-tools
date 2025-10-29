# External MCP Server Setup Guide

## Quick Setup for External MCP Servers

This guide explains how to configure your external MCP server to work with iaCoreTools authentication.

## Prerequisites

- FastMCP >= 0.3.0

## Installation

```bash
pip install fastmcp>=0.3.0 python-dotenv
```

## Configuration Steps

### 1. Get JWT Secret from iaCoreTools Admin

### 2. Create `.env` File

Create a `.env` file in your MCP server project root:

```bash
JWT_SECRET=your-secret-key-from-iacore-admin
```

**Important:** Replace `your-secret-key-from-iacore-admin` with the actual secret provided by the iaCoreTools administrator.

### 3. Configure Your MCP Server

Update your main MCP server file adding the following code:

```python
from fastmcp.server.auth.providers.jwt import JWTVerifier
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET")

# Create FastMCP server with JWT authentication
mcp = FastMCP(
    "your-server-name",    
    auth=JWTVerifier(
        public_key=JWT_SECRET,  # For HS256, this is the shared secret
        algorithm="HS256"       # Must match iaCoreTools (HS256)
    )
)
```



Expected result:
- ✅ **200 OK** - Authentication working correctly
- ❌ **401 Unauthorized** - JWT secret mismatch or invalid token

## Troubleshooting

### 401 Unauthorized Error

**Problem:** Server returns 401 when iaCoreTools connects

**Solutions:**
1. Verify JWT_SECRET matches exactly with iaCoreTools
2. Ensure algorithm is "HS256"
3. Check that .env file is in the correct directory
4. Verify dotenv is loading correctly

```python
# Add this to debug:
print(f"JWT Secret loaded: {JWT_SECRET[:20]}..." if JWT_SECRET else "NOT FOUND")
```
