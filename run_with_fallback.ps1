# 设置环境变量来强制使用MCP替代实现
$env:FORCE_FALLBACK = "true"
Write-Host "MCP fallback mode enabled." -ForegroundColor Green
Write-Host "Starting Streamlit application..." -ForegroundColor Cyan
streamlit run fengao_brainstorming.py 