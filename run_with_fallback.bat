@echo off
REM 设置环境变量来强制使用MCP替代实现
set FORCE_FALLBACK=true

REM 确保使用MCP替代实现
echo MCP fallback mode enabled.
echo Starting Streamlit application...
streamlit run fengao_brainstorming.py 