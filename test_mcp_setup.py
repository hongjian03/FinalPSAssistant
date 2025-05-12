"""
MCP配置诊断工具
"""

import sys
import os
import traceback

def check_mcp_installation():
    print("=== MCP安装检测 ===")
    
    try:
        import mcp
        print(f"✅ MCP模块已安装，版本：{getattr(mcp, '__version__', '未知')}")
        print(f"📁 MCP模块路径：{getattr(mcp, '__file__', '未知')}")
        
        # 检查可用API
        mcp_apis = [x for x in dir(mcp) if not x.startswith("_")]
        print(f"📋 MCP可用API: {', '.join(mcp_apis)}")
        
        # 检查create_client函数是否存在
        if "create_client" in mcp_apis:
            print("✅ create_client API可用")
        else:
            print("❌ create_client API不可用，请更新MCP到最新版本")
            print("   建议执行: pip install -U mcp")
        
        # 检查client模块
        if hasattr(mcp, "client"):
            client_apis = [x for x in dir(mcp.client) if not x.startswith("_")]
            print(f"📋 client模块API: {', '.join(client_apis)}")
            
            # 检查streamable_http模块
            try:
                from mcp.client.streamable_http import streamablehttp_client
                print("✅ streamablehttp_client可用")
            except ImportError:
                print("❌ streamablehttp_client不可用")
                print("   这可能是因为MCP版本太旧或太新")
            
            # 检查ClientSession类
            if "ClientSession" in client_apis:
                print("✅ ClientSession类可用")
            else:
                print("❌ ClientSession类不可用")
                print("   MCP版本可能不兼容，请检查API文档")
    except ImportError as e:
        print(f"❌ MCP模块未安装: {str(e)}")
        print("   请执行: pip install mcp")
        return False
    
    return True

def check_smithery_installation():
    print("\n=== Smithery安装检测 ===")
    
    try:
        import smithery
        print(f"✅ Smithery模块已安装，版本：{getattr(smithery, '__version__', '未知')}")
        print(f"📁 Smithery模块路径：{getattr(smithery, '__file__', '未知')}")
        
        # 检查websocket_client是否可用
        try:
            from smithery import websocket_client
            print("✅ websocket_client可用")
        except ImportError:
            print("❌ websocket_client不可用")
            print("   这可能是因为Smithery版本不兼容")
        
        # 检查Smithery模块内容
        print(f"📋 Smithery API: {', '.join([x for x in dir(smithery) if not x.startswith('_')])}")
    except ImportError as e:
        print(f"❌ Smithery模块未安装: {str(e)}")
        print("   请执行: pip install smithery")
        return False
    
    return True

def check_api_keys():
    print("\n=== API密钥检测 ===")
    
    # 检查环境变量中的API密钥
    smithery_api_key = os.environ.get("SMITHERY_API_KEY", "")
    if smithery_api_key:
        print("✅ 环境变量中存在SMITHERY_API_KEY")
        if not smithery_api_key.startswith("sm-"):
            print("⚠️ 警告: API密钥格式可能不正确，标准格式应以'sm-'开头")
    else:
        print("❌ 环境变量中不存在SMITHERY_API_KEY")
        print("   可以通过设置环境变量提供API密钥: ")
        print("   - Windows (CMD): set SMITHERY_API_KEY=your-key-here")
        print("   - Windows (PowerShell): $env:SMITHERY_API_KEY=\"your-key-here\"")
        print("   - Linux/macOS: export SMITHERY_API_KEY=your-key-here")
    
    return True

def test_mcp_connection():
    print("\n=== MCP连接测试 ===")
    
    try:
        # 导入必要模块
        import mcp
        import asyncio
        
        # 检查API密钥
        smithery_api_key = os.environ.get("SMITHERY_API_KEY", "")
        if not smithery_api_key:
            print("❌ 缺少Smithery API密钥，无法进行连接测试")
            return False
        
        async def test_connection():
            try:
                print("🔄 正在连接到Smithery服务器...")
                
                # 使用ping测试服务
                url = f"https://server.smithery.ai/@smithery/ping-test-service/mcp?api_key={smithery_api_key}"
                print(f"🔗 URL: {url[:50]}...")  # 只显示部分URL，隐藏API密钥
                
                # 判断mcp版本，选择合适的连接方式
                if hasattr(mcp, "create_client"):
                    # 使用新API (MCP 1.7.0+)
                    print("🔄 使用mcp.create_client()建立连接...")
                    try:
                        client = await mcp.create_client(url)
                        print("✅ 连接成功")
                        
                        print("🔄 列出可用工具...")
                        tools = await client.list_tools()
                        print(f"✅ 可用工具: {', '.join([t.name for t in tools.tools])}")
                        
                        print("🔄 执行ping请求...")
                        result = await client.request("ping", {})
                        print(f"✅ ping结果: {result}")
                        
                        await client.close()
                        print("✅ 连接测试成功")
                        return True
                    except Exception as e:
                        print(f"❌ 使用create_client连接失败: {str(e)}")
                        traceback.print_exc()
                else:
                    # 尝试使用旧API
                    try:
                        from mcp.client.streamable_http import streamablehttp_client
                        from mcp import ClientSession
                        
                        print("🔄 使用streamablehttp_client和ClientSession建立连接...")
                        async with streamablehttp_client(url) as (read_stream, write_stream, _):
                            print("✅ HTTP连接成功")
                            
                            async with ClientSession(read_stream, write_stream) as session:
                                print("✅ MCP会话创建成功")
                                
                                print("🔄 初始化会话...")
                                await session.initialize()
                                print("✅ 会话初始化成功")
                                
                                print("🔄 执行ping请求...")
                                result = await session.request("ping", {})
                                print(f"✅ ping结果: {result}")
                                
                                print("✅ 连接测试成功")
                                return True
                    except Exception as e:
                        print(f"❌ 使用旧API连接失败: {str(e)}")
                        traceback.print_exc()
            
            except Exception as e:
                print(f"❌ 连接测试失败: {str(e)}")
                traceback.print_exc()
                return False
        
        # 运行异步测试函数
        success = asyncio.run(test_connection())
        return success
    
    except Exception as e:
        print(f"❌ 连接测试出错: {str(e)}")
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=== MCP配置诊断工具 ===")
    print("该工具将帮助您诊断MCP连接问题\n")
    
    mcp_installed = check_mcp_installation()
    smithery_installed = check_smithery_installation()
    api_keys_available = check_api_keys()
    
    if mcp_installed and smithery_installed and api_keys_available:
        print("\n所有依赖项检查完成，现在进行连接测试")
        connection_successful = test_mcp_connection()
        
        if connection_successful:
            print("\n✅✅✅ MCP配置正常 ✅✅✅")
            print("您可以正常使用MCP功能")
        else:
            print("\n❌❌❌ MCP连接测试失败 ❌❌❌")
            print("检查以下可能的原因:")
            print(" 1. API密钥可能无效或过期")
            print(" 2. 网络连接问题")
            print(" 3. MCP或Smithery版本可能不兼容")
            print(" 4. Smithery服务器可能暂时不可用")
            
            print("\n您可以尝试以下解决方案:")
            print(" 1. 更新MCP和Smithery到最新版本: pip install -U mcp smithery")
            print(" 2. 检查API密钥是否正确")
            print(" 3. 检查网络连接")
            print(" 4. 临时使用备用实现 (设置环境变量 FORCE_FALLBACK=true)")
    else:
        print("\n❌ 依赖项检查失败，请先解决以上问题")
    
if __name__ == "__main__":
    main() 