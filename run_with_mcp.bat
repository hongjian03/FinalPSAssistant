@echo off
REM 设置环境变量，禁用 MCP 强制回退
set FORCE_FALLBACK=false

REM 确保使用MCP连接
echo 尝试使用HTTP方式连接MCP...
echo 启动Streamlit应用程序...
streamlit run fengao_brainstorming.py 