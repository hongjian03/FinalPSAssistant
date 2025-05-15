import os
import json
import base64
import asyncio
from typing import Dict, Any, List, Optional
import streamlit as st
import traceback
import mcp
from mcp.client.streamable_http import streamablehttp_client

class SerperClient:
    """
    Client for interacting with the Serper MCP server for web search capabilities.
    This allows agents to search for up-to-date information from the web.
    Using the Smithery-provided HTTP streaming implementation for MCP.
    """
    
    def __init__(self):
        """Initialize the Serper MCP client with configuration from Streamlit secrets."""
        # Get API keys from Streamlit secrets
        self.serper_api_key = st.secrets.get("SERPER_API_KEY", "").strip()
        self.smithery_api_key = st.secrets.get("SMITHERY_API_KEY", "").strip()
        
        # Server config
        self.config = {
            "serperApiKey": self.serper_api_key
        }
        
        # Base64 encode the config
        try:
            self.config_b64 = base64.b64encode(json.dumps(self.config).encode()).decode()
        except Exception as e:
            self.config_b64 = ""
        
        # Create server URL with HTTP streaming API
        self.url = f"https://server.smithery.ai/@marcopesani/mcp-server-serper/mcp?config={self.config_b64}&api_key={self.smithery_api_key}"
        
        # Keep a record of tools
        self.available_tools = []
        # The correct search tool name (will be determined in initialize)
        self.search_tool_name = None
    
    async def initialize(self, main_container=None):
        """Initialize the connection to the MCP server and get available tools."""
        # Create a container for the progress display if not provided
        if main_container is None:
            main_container = st.container()
        
        # Check API keys
        if not self.serper_api_key or not self.smithery_api_key:
            with main_container:
                st.error("无法初始化: SERPER_API_KEY 或 SMITHERY_API_KEY 未设置。")
            return False
            
        # Check URL format
        if not self.url.startswith("https://"):
            with main_container:
                st.error(f"错误的URL格式: {self.url[:15]}...")
            return False
            
        try:
            with main_container:
                st.subheader("MCP连接进度")
                
                # Create progress bar and status display
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.info("开始初始化Serper MCP服务连接")
                
                # Display basic URL info
                base_url = self.url.split("?")[0]
                st.caption(f"连接到服务器: {base_url}")
                
                try:
                    # Set longer timeout
                    status_text.info("准备建立连接 (30秒超时)...")
                    progress_bar.progress(10)
                    await asyncio.sleep(0.3)
                    
                    async with asyncio.timeout(30):
                        # Connect using streamable HTTP client
                        status_text.info("开始HTTP流式连接...")
                        progress_bar.progress(30)
                        await asyncio.sleep(0.3)
                        
                        try:
                            async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                status_text.info("HTTP流式连接成功，创建MCP会话...")
                                progress_bar.progress(50)
                                await asyncio.sleep(0.3)
                                
                                async with mcp.ClientSession(read_stream, write_stream) as session:
                                    # Initialize the connection
                                    status_text.info("初始化MCP会话...")
                                    progress_bar.progress(70)
                                    await asyncio.sleep(0.3)
                                    
                                    # Initialize connection
                                    await session.initialize()
                                    
                                    # List available tools
                                    status_text.info("获取可用工具列表...")
                                    progress_bar.progress(85)
                                    await asyncio.sleep(0.3)
                                    
                                    tools_result = await session.list_tools()
                                    self.available_tools = [t.name for t in tools_result.tools]
                                    
                                    # Determine the correct search tool name
                                    search_tool_candidates = [
                                        "search", 
                                        "serper-search", 
                                        "web-search",
                                        "google-search",
                                        "serper"
                                    ]
                                    
                                    for tool_name in search_tool_candidates:
                                        if tool_name in self.available_tools:
                                            self.search_tool_name = tool_name
                                            break
                                    
                                    # Connection successful
                                    progress_bar.progress(100)
                                    status_text.success("MCP连接成功！")
                                    
                                    # Display available tools and selected search tool
                                    tools_info = f"可用工具: {', '.join(self.available_tools)}"
                                    if self.search_tool_name:
                                        tools_info += f"\n已选择搜索工具: {self.search_tool_name}"
                                    else:
                                        tools_info += "\n警告: 未找到可用的搜索工具!"
                                    
                                    st.info(tools_info)
                                    
                                    return self.search_tool_name is not None
                        except Exception as e:
                            error_type = type(e).__name__
                            progress_bar.progress(100)
                            status_text.error(f"MCP连接失败: {error_type}")
                            
                            st.error(f"MCP连接失败: {str(e)}")
                            
                            # Provide specific error information
                            if "401" in str(e) or "unauthorized" in str(e).lower():
                                st.error("API密钥验证失败。请检查SMITHERY_API_KEY是否正确。")
                            elif "404" in str(e) or "not found" in str(e).lower():
                                st.error("无法找到MCP服务器端点。请检查URL是否正确。")
                            
                            return False
                except asyncio.TimeoutError:
                    progress_bar.progress(100)
                    status_text.error("连接超时(30秒)")
                    
                    st.error("连接超时(30秒)。Serper MCP API服务器响应时间过长或不响应。")
                    return False
        except Exception as e:
            error_message = str(e)
            with main_container:
                st.error(f"初始化MCP客户端时出错: {error_message}")
            return False
    
    async def search_web(self, query: str, main_container=None) -> Dict[str, Any]:
        """
        Perform a web search using the Serper MCP server.
        
        Args:
            query: The search query
            main_container: Container to display progress in
            
        Returns:
            Dictionary containing search results
        """
        # Create a container for the progress display if not provided
        if main_container is None:
            main_container = st.container()
            
        try:
            with main_container:
                st.subheader(f"执行搜索: {query}")
                
                # Create progress bar and status display
                search_progress = st.progress(0)
                search_status = st.empty()
                search_status.info("准备搜索...")
                
                # Check if we have a valid search tool
                if not self.search_tool_name:
                    search_progress.progress(100)
                    search_status.error("未找到有效的搜索工具")
                    return {"error": "未找到有效的搜索工具，请确保MCP服务器提供了搜索功能"}
                
                # Prevent empty query
                if not query or len(query.strip()) == 0:
                    search_progress.progress(100)
                    search_status.error("搜索查询不能为空")
                    return {"error": "搜索查询不能为空"}
                
                # Connect to the server using streamable HTTP client
                search_progress.progress(20)
                search_status.info("建立MCP连接...")
                await asyncio.sleep(0.3)
                
                try:
                    async with asyncio.timeout(30):
                        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                            search_progress.progress(40)
                            search_status.info("创建MCP会话...")
                            await asyncio.sleep(0.3)
                            
                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                # Initialize the connection
                                search_progress.progress(50)
                                search_status.info("初始化会话...")
                                await asyncio.sleep(0.3)
                                
                                await session.initialize()
                                
                                # Call the web search tool
                                search_progress.progress(70)
                                search_status.info(f"执行搜索: {query}")
                                await asyncio.sleep(0.3)
                                
                                try:
                                    # Use the dynamically determined search tool name
                                    result = await session.call_tool(self.search_tool_name, arguments={
                                        "query": query,
                                        "numResults": 5
                                    })
                                    
                                    search_progress.progress(90)
                                    search_status.info("处理搜索结果...")
                                    await asyncio.sleep(0.3)
                                    
                                    if hasattr(result, 'result'):
                                        search_progress.progress(100)
                                        if "organic" in result.result and result.result["organic"]:
                                            search_status.success(f"搜索成功，找到 {len(result.result['organic'])} 条结果")
                                        else:
                                            search_status.warning("搜索完成，但未找到有机结果")
                                        return result.result
                                    else:
                                        search_progress.progress(100)
                                        search_status.error("搜索结果格式不正确")
                                        return {"error": "搜索结果格式不正确，缺少result属性"}
                                except Exception as e:
                                    search_progress.progress(100)
                                    search_status.error(f"调用{self.search_tool_name}工具时出错: {str(e)}")
                                    return {"error": f"调用{self.search_tool_name}工具时出错: {str(e)}"}
                except asyncio.TimeoutError:
                    search_progress.progress(100)
                    search_status.error("搜索操作超时(30秒)")
                    return {"error": "搜索操作超时(30秒)，服务器响应时间过长"}
                except Exception as e:
                    search_progress.progress(100)
                    search_status.error(f"MCP连接异常: {type(e).__name__}")
                    return {"error": f"MCP连接异常: {type(e).__name__}: {e}"}
        except Exception as e:
            error_msg = f"执行Web搜索时出错: {str(e)}"
            with main_container:
                st.error(error_msg)
            return {"error": error_msg}
    
    def run_async(self, coroutine):
        """Helper method to run async methods synchronously."""
        return asyncio.run(coroutine) 