@echo off
setlocal
set "MCP_NODE=%CODEX_MCP_NODE_PATH%"
if not defined MCP_NODE set "MCP_NODE=node"
"%MCP_NODE%" "%~1"
