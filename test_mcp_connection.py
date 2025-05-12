"""
MCP连接测试脚本
"""

import asyncio
import logging
import json
import sys
import os
import traceback

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    # 1. 导入必要模块
    try:
        import mcp
        from smithery import websocket_client
        logger.info("✅ 成功导入MCP和Smithery模块")
        logger.info(f"MCP版本: {getattr(mcp, '__version__', '未知')}")
        logger.info(f"MCP模块路径: {getattr(mcp, '__file__', '未知')}")
    except ImportError as e:
        logger.error(f"❌ 导入MCP或Smithery模块失败: {str(e)}")
        return False
    
    # 2. 获取API密钥
    try:
        # 尝试从命令行参数获取
        if len(sys.argv) > 1 and sys.argv[1].startswith("sm-"):
            smithery_api_key = sys.argv[1]
            logger.info("✅ 从命令行参数获取API密钥")
        # 尝试从环境变量获取
        elif "SMITHERY_API_KEY" in os.environ:
            smithery_api_key = os.environ["SMITHERY_API_KEY"]
            logger.info("✅ 从环境变量获取API密钥")
        else:
            # 从用户输入获取
            smithery_api_key = input("请输入Smithery API密钥 (以sm-开头): ")
        
        if not smithery_api_key or not smithery_api_key.startswith("sm-"):
            logger.warning("⚠️ API密钥格式可能不正确，应该以'sm-'开头")
        
        logger.info(f"API密钥长度: {len(smithery_api_key)}")
    except Exception as e:
        logger.error(f"❌ 获取API密钥失败: {str(e)}")
        return False
    
    # 3. 测试基本HTTP连接
    try:
        import requests
        test_url = "https://server.smithery.ai/health"
        logger.info(f"测试HTTP连接: {test_url}")
        
        response = requests.get(test_url)
        logger.info(f"HTTP响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            logger.info("✅ 基本HTTP连接测试成功")
        else:
            logger.error(f"❌ 基本HTTP连接测试失败: {response.text}")
    except Exception as e:
        logger.error(f"❌ HTTP请求失败: {str(e)}")
    
    # 4. 尝试WebSocket连接
    try:
        import websockets
        logger.info("测试基本WebSocket连接...")
        
        async with websockets.connect("wss://echo.websocket.org") as ws:
            test_message = "Hello WebSocket"
            logger.info(f"发送消息: {test_message}")
            await ws.send(test_message)
            response = await ws.recv()
            logger.info(f"收到响应: {response}")
            
            if response == test_message:
                logger.info("✅ 基本WebSocket连接测试成功")
            else:
                logger.error(f"❌ 基本WebSocket连接测试失败: 返回'{response}'而不是'{test_message}'")
    except Exception as e:
        logger.error(f"❌ WebSocket连接测试失败: {str(e)}")
        logger.error(traceback.format_exc())
    
    # 5. 使用MCP和WebSocket客户端连接Smithery
    try:
        logger.info("测试MCP连接...")
        test_url = f"https://server.smithery.ai/@smithery/ping-test-service/mcp?api_key={smithery_api_key}"
        logger.info(f"连接到: {test_url[:50]}..." + "***" + test_url[-10:])  # 隐藏API密钥
        
        try:
            logger.info("建立WebSocket连接...")
            async with websocket_client(test_url) as (read_stream, write_stream, raw_ws):
                logger.info("✅ WebSocket连接已建立")
                
                try:
                    logger.info("创建MCP客户端会话...")
                    async with mcp.ClientSession(read_stream, write_stream) as session:
                        logger.info("✅ MCP客户端会话已创建")
                        
                        try:
                            logger.info("初始化MCP会话...")
                            await session.initialize()
                            logger.info("✅ MCP会话初始化成功")
                            
                            try:
                                logger.info("执行ping请求...")
                                response = await session.request("ping", {})
                                logger.info(f"✅ Ping响应: {response}")
                                logger.info("MCP连接测试全部成功！")
                                return True
                            except Exception as e:
                                logger.error(f"❌ Ping请求失败: {str(e)}")
                                logger.error(traceback.format_exc())
                        except Exception as e:
                            logger.error(f"❌ MCP会话初始化失败: {str(e)}")
                            logger.error(traceback.format_exc())
                except Exception as e:
                    logger.error(f"❌ 创建MCP客户端会话失败: {str(e)}")
                    logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"❌ 建立WebSocket连接失败: {str(e)}")
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"❌ MCP连接测试失败: {str(e)}")
        logger.error(traceback.format_exc())
    
    return False

if __name__ == "__main__":
    logger.info("开始测试MCP连接...")
    result = asyncio.run(main())
    if result:
        logger.info("🎉 全部测试成功，MCP连接正常工作！")
        sys.exit(0)
    else:
        logger.error("❌ 测试失败，MCP连接存在问题")
        sys.exit(1)