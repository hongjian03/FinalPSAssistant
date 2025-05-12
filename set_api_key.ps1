# 设置Smithery API密钥环境变量
# 注意：实际使用时请替换为真实的API密钥
$env:SMITHERY_API_KEY = "sm-your-actual-api-key-here"

# 显示确认信息
Write-Host "已设置Smithery API密钥环境变量" -ForegroundColor Green

# 启动Streamlit应用
Write-Host "正在启动PS助手平台..." -ForegroundColor Cyan
streamlit run fengao_brainstorming.py 