import mcp
import json
import base64
import asyncio
import os
import sys

# 尝试从环境变量或命令行获取API密钥
if len(sys.argv) > 1:
    smithery_api_key = sys.argv[1]
    print("使用命令行参数的API密钥")
elif "SMITHERY_API_KEY" in os.environ:
    smithery_api_key = os.environ["SMITHERY_API_KEY"]
    print("使用环境变量的API密钥")
else:
    smithery_api_key = input("请输入您的Smithery API密钥: ")

# 准备配置
config = {
    "serperApiKey": "your-serper-api-key"  # 此处可以留空，仅进行连接测试
}

# 编码配置为base64
config_b64 = base64.b64encode(json.dumps(config).encode()).decode()

# 创建服务器URL
url = f"https://server.smithery.ai/@smithery/ping-test-service/mcp?api_key={smithery_api_key}"
print(f"连接到: {url[:50]}...")  # 只显示URL前缀，不显示API密钥

async def main():
    try:
        print("正在连接到Smithery服务器...")
        # 使用标准的WebSocket连接方式
        client_session = await mcp.create_client(url)
        print("MCP客户端已创建")
        
        # 初始化连接
        print("正在初始化MCP会话...")
        tools = await client_session.list_tools()
        print(f"可用工具: {', '.join([t.name for t in tools.tools])}")
        
        # 尝试发送ping请求
        print("正在发送ping请求...")
        ping_result = await client_session.request("ping", {})
        print(f"Ping结果: {ping_result}")
        
        # 关闭会话
        await client_session.close()
        print("\n✅ MCP连接测试成功！")
        return True
    except Exception as e:
        print(f"MCP连接错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n❌ MCP连接测试失败！")
    return False

if __name__ == "__main__":
    result = asyncio.run(main())
    if not result:
        sys.exit(1) 