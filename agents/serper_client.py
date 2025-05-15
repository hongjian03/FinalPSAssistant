import os
import json
import base64
import asyncio
from typing import Dict, Any, List, Optional
import streamlit as st
import traceback
import mcp
from mcp.client.websocket import websocket_client
import websockets

class SerperClient:
    """
    Client for interacting with the Serper MCP server for web search capabilities.
    This allows the consulting assistant to search for up-to-date information about UCL programs.
    """
    
    def __init__(self):
        """Initialize the Serper MCP client with configuration from Streamlit secrets."""
        # Get API keys from Streamlit secrets - 确保精确匹配密钥名称
        self.serper_api_key = st.secrets.get("SERPER_API_KEY", "").strip()
        self.smithery_api_key = st.secrets.get("SMITHERY_API_KEY", "").strip()
        
        # 添加API密钥检查调试信息
        if not self.serper_api_key:
            st.error("SERPER_API_KEY 未设置或为空。请在 .streamlit/secrets.toml 中正确配置此密钥。")
        
        if not self.smithery_api_key:
            st.error("SMITHERY_API_KEY 未设置或为空。请在 .streamlit/secrets.toml 中正确配置此密钥。")
        
        # 显示密钥前几位字符（安全地显示部分密钥以确认有值）
        if len(self.serper_api_key) > 4:
            st.info(f"SERPER_API_KEY 已设置 (开头为: {self.serper_api_key[:4]}...)")
        
        if len(self.smithery_api_key) > 4:
            st.info(f"SMITHERY_API_KEY 已设置 (开头为: {self.smithery_api_key[:4]}...)")
            
        # 显示MCP版本信息
        try:
            st.info(f"MCP包版本: {mcp.__version__}")
        except:
            st.warning("无法获取MCP包版本。请确保已安装正确版本的MCP。")
        
        # 显示WebSockets版本信息
        try:
            st.info(f"WebSockets包版本: {websockets.__version__}")
        except:
            st.warning("无法获取WebSockets包版本。请确保已安装正确版本的WebSockets。")
        
        # Server config
        self.config = {
            "serperApiKey": self.serper_api_key
        }
        
        # Base64 encode the config - 添加错误处理
        try:
            self.config_b64 = base64.b64encode(json.dumps(self.config).encode()).decode()
        except Exception as e:
            st.error(f"配置序列化错误: {str(e)}")
            self.config_b64 = ""
        
        # Create server URL - 使用最新的正确URL格式
        self.url = f"wss://server.smithery.ai/@marcopesani/mcp-server-serper/ws?config={self.config_b64}&api_key={self.smithery_api_key}"
        
        # Keep a record of tools
        self.available_tools = []
    
    async def initialize(self):
        """Initialize the connection to the MCP server and get available tools."""
        # 检查API密钥是否设置
        if not self.serper_api_key or not self.smithery_api_key:
            st.error("无法初始化: SERPER_API_KEY 或 SMITHERY_API_KEY 未设置。")
            return False
            
        # 检查URL格式
        if not self.url.startswith("wss://"):
            st.error(f"错误的URL格式: {self.url[:15]}...")
            return False
            
        try:
            # 添加连接状态指示
            with st.status("正在连接到Serper API...") as status:
                status.write("正在准备websocket连接...")
                
                # 显示完整URL信息（不包括配置和API密钥）
                base_url = self.url.split("?")[0]
                status.write(f"连接到服务器: {base_url}")
                
                # 使用固定的连接参数
                connection_kwargs = {
                    "max_size": 10 * 1024 * 1024,  # 10MB 最大消息大小
                    "ping_interval": None,  # 禁用ping以避免超时问题
                    "ping_timeout": None,
                    "close_timeout": 20,  # 增加关闭超时
                    "max_queue": 32,  # 增加队列大小
                    "read_limit": 2**18,  # 增加读取限制
                    "write_limit": 2**18,  # 增加写入限制
                }
                
                try:
                    # 设置更长的超时时间
                    status.write("开始建立连接 (30秒超时)...")
                    async with asyncio.timeout(30):  # 增加超时时间到30秒
                        # Connect to the server using websocket client
                        status.write(f"开始WebSocket连接...")
                        
                        # 尝试创建WebSocket连接
                        try:
                            async with websocket_client(self.url, **connection_kwargs) as streams:
                                status.write("WebSocket连接成功，创建MCP会话...")
                                async with mcp.ClientSession(*streams) as session:
                                    # Initialize the connection
                                    status.write("初始化MCP会话...")
                                    await session.initialize()
                                    
                                    # List available tools
                                    status.write("获取可用工具列表...")
                                    tools_result = await session.list_tools()
                                    self.available_tools = [t.name for t in tools_result.tools]
                                    st.success(f"成功连接到Serper API。可用工具: {', '.join(self.available_tools)}")
                                    return True
                        except websockets.exceptions.InvalidStatusCode as e:
                            status.error(f"无效的WebSocket状态码: {e}")
                            st.error(f"WebSocket连接失败，状态码: {e}")
                            if "401" in str(e):
                                st.error("401未授权错误 - API密钥验证失败。请检查SMITHERY_API_KEY是否正确。")
                            return False
                        except websockets.exceptions.ConnectionClosed as e:
                            status.error(f"WebSocket连接被关闭: {e}")
                            st.error(f"WebSocket连接被过早关闭: {e}")
                            return False
                        except Exception as e:
                            status.error(f"WebSocket连接异常: {type(e).__name__}: {e}")
                            st.error(f"无法建立WebSocket连接: {type(e).__name__}: {e}")
                            return False
                except asyncio.TimeoutError:
                    st.error("连接超时(30秒)。Serper API服务器响应时间过长或不响应。")
                    return False
        except Exception as e:
            error_message = str(e)
            traceback_str = traceback.format_exc()
            st.error(f"初始化Serper MCP客户端时出错: {error_message}")
            st.error(f"错误堆栈: {traceback_str}")
            
            # 提供更具体的错误信息
            if "unauthorized" in error_message.lower() or "401" in error_message:
                st.error("API密钥验证失败。请检查SERPER_API_KEY和SMITHERY_API_KEY是否正确。")
            elif "connect" in error_message.lower() or "connection" in error_message.lower():
                st.error("无法连接到Serper API服务器。请检查网络连接。")
            elif "not found" in error_message.lower() or "404" in error_message:
                st.error("找不到API端点。请检查URL路径是否正确。")
            return False
    
    async def search_web(self, query: str) -> Dict[str, Any]:
        """
        Perform a web search using the Serper MCP server.
        
        Args:
            query: The search query
            
        Returns:
            Dictionary containing search results
        """
        try:
            with st.status(f"搜索: {query}") as status:
                # 防止查询为空
                if not query or len(query.strip()) == 0:
                    status.error("搜索查询不能为空")
                    return {"error": "搜索查询不能为空"}
                
                # 使用固定的连接参数
                connection_kwargs = {
                    "max_size": 10 * 1024 * 1024,  # 10MB 最大消息大小
                    "ping_interval": None,  # 禁用ping以避免超时问题
                    "ping_timeout": None,
                    "close_timeout": 20,  # 增加关闭超时
                    "max_queue": 32,  # 增加队列大小
                    "read_limit": 2**18,  # 增加读取限制
                    "write_limit": 2**18,  # 增加写入限制
                }
                
                # Connect to the server using websocket client
                status.write("建立WebSocket连接...")
                try:
                    async with asyncio.timeout(30):  # 增加超时时间到30秒
                        async with websocket_client(self.url, **connection_kwargs) as streams:
                            status.write("创建MCP会话...")
                            async with mcp.ClientSession(*streams) as session:
                                # Initialize the connection
                                status.write("初始化会话...")
                                await session.initialize()
                                
                                # Call the web search tool
                                status.write(f"调用web-search工具搜索: {query}")
                                try:
                                    result = await session.call_tool("web-search", arguments={
                                        "query": query,
                                        "numResults": 5
                                    })
                                    
                                    status.write("搜索完成，处理结果...")
                                    if hasattr(result, 'result'):
                                        if "organic" in result.result and result.result["organic"]:
                                            status.success(f"搜索成功，找到 {len(result.result['organic'])} 条结果")
                                        else:
                                            status.warning("搜索完成，但未找到有机结果")
                                        return result.result
                                    else:
                                        status.error("搜索结果格式不正确")
                                        return {"error": "搜索结果格式不正确，缺少result属性"}
                                except Exception as e:
                                    status.error(f"调用web-search工具时出错: {str(e)}")
                                    return {"error": f"调用web-search工具时出错: {str(e)}"}
                except asyncio.TimeoutError:
                    status.error("搜索操作超时(30秒)")
                    return {"error": "搜索操作超时(30秒)，服务器响应时间过长"}
                except Exception as e:
                    status.error(f"WebSocket连接异常: {type(e).__name__}: {e}")
                    return {"error": f"WebSocket连接异常: {type(e).__name__}: {e}"}
        except Exception as e:
            error_msg = f"执行Web搜索时出错: {str(e)}"
            traceback_str = traceback.format_exc()
            st.error(error_msg)
            st.error(f"错误堆栈: {traceback_str}")
            return {"error": error_msg}
    
    async def search_ucl_programs(self, keywords: List[str]) -> List[Dict[str, str]]:
        """
        Search for UCL programs using the web search tool.
        
        Args:
            keywords: List of keywords to search for
            
        Returns:
            List of program information dictionaries
        """
        try:
            # Construct search query
            search_query = f"UCL University College London postgraduate programs {' '.join(keywords)}"
            
            # Perform search
            search_results = await self.search_web(search_query)
            
            # Check for errors
            if "error" in search_results:
                return [{"error": search_results["error"]}]
            
            # Process actual search results
            programs = []
            
            # Extract relevant information from search results
            if "organic" in search_results:
                for result in search_results["organic"][:5]:
                    programs.append({
                        "title": result.get("title", "无标题"),
                        "url": result.get("link", "无链接"),
                        "description": result.get("snippet", "无描述")
                    })
            
            # Return real search results
            return programs
            
        except Exception as e:
            error_msg = f"搜索UCL项目时出错: {str(e)}"
            st.error(error_msg)
            return [{"error": error_msg}]
    
    def run_async(self, coroutine):
        """Helper method to run async methods synchronously."""
        return asyncio.run(coroutine) 