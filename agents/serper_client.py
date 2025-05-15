import os
import json
import base64
import asyncio
from typing import Dict, Any, List, Optional
import streamlit as st
import traceback
import mcp
from mcp.client.streamable_http import streamablehttp_client
import requests
import time

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
        # Maximum retries for connection issues
        self.max_retries = 3
    
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
                
                # 创建专门的进度展示区域，确保进度条靠左对齐
                progress_container = st.container()
                with progress_container:
                    # Create progress bar and status display
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    status_text.info("开始初始化Serper MCP服务连接")
                
                # Display basic URL info
                base_url = self.url.split("?")[0]
                st.caption(f"连接到服务器: {base_url}")
                
                try:
                    # Set longer timeout
                    with progress_container:
                        status_text.info("准备建立连接 (30秒超时)...")
                        progress_bar.progress(10)
                    await asyncio.sleep(0.3)
                    
                    try:
                        async with asyncio.timeout(30):
                            # Connect using streamable HTTP client
                            with progress_container:
                                status_text.info("开始HTTP流式连接...")
                                progress_bar.progress(30)
                            await asyncio.sleep(0.3)
                            
                            try:
                                async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                    with progress_container:
                                        status_text.info("HTTP流式连接成功，创建MCP会话...")
                                        progress_bar.progress(50)
                                    await asyncio.sleep(0.3)
                                    
                                    try:
                                        async with mcp.ClientSession(read_stream, write_stream) as session:
                                            # Initialize the connection
                                            with progress_container:
                                                status_text.info("初始化MCP会话...")
                                                progress_bar.progress(70)
                                            await asyncio.sleep(0.3)
                                            
                                            # Initialize connection
                                            await session.initialize()
                                        
                                            # List available tools
                                            with progress_container:
                                                status_text.info("获取可用工具列表...")
                                                progress_bar.progress(85)
                                            await asyncio.sleep(0.3)
                                            
                                            tools_result = await session.list_tools()
                                            self.available_tools = [t.name for t in tools_result.tools]
                                            
                                            # Determine the correct search tool name
                                            search_tool_candidates = [
                                                "google_search",  # 添加服务器实际使用的工具名
                                                "search", 
                                                "serper-search", 
                                                "web-search",
                                                "google-search",
                                                "serper",
                                                "scrape"
                                            ]
                                            
                                            # 首先尝试精确匹配
                                            for tool_name in search_tool_candidates:
                                                if tool_name in self.available_tools:
                                                    self.search_tool_name = tool_name
                                                    break
                                            
                                            # 如果没找到精确匹配，尝试模糊匹配（包含"search"的工具名）
                                            if not self.search_tool_name:
                                                for tool_name in self.available_tools:
                                                    if "search" in tool_name.lower():
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
                                            
                                            # 如果没有找到搜索工具但有scrape工具，尝试使用它
                                            if not self.search_tool_name and "scrape" in self.available_tools:
                                                st.warning("未找到搜索工具，但发现'scrape'工具。尝试使用scrape工具作为替代...")
                                                self.search_tool_name = "scrape"
                                                return True
                                            
                                            return self.search_tool_name is not None
                                    except Exception as e:
                                        error_msg = str(e)
                                        error_type = type(e).__name__
                                        
                                        # 检查是否包含 TaskGroup 相关错误
                                        if "TaskGroup" in error_msg or "TaskGroup" in error_type:
                                            progress_bar.progress(100)
                                            status_text.error(f"MCP会话异步任务组错误")
                                            st.error(f"MCP会话出现TaskGroup错误，这可能是由于Python版本兼容性问题或MCP服务器内部错误。错误详情: {error_msg}")
                                            st.info("尝试使用Python 3.10+版本可能会解决此问题，或者MCP服务器可能暂时不可用。")
                                        else:
                                            progress_bar.progress(100)
                                            status_text.error(f"MCP会话错误: {error_type}")
                                            st.error(f"MCP会话错误: {error_msg}")
                                        
                                        return False
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
                                elif "TaskGroup" in str(e):
                                    st.error("MCP连接出现TaskGroup错误，这可能是由于Python版本兼容性问题。尝试使用Python 3.10+可能会解决此问题。")
                                
                                return False
                    except asyncio.TimeoutError:
                        progress_bar.progress(100)
                        status_text.error("连接超时(30秒)")
                        
                        st.error("连接超时(30秒)。Serper MCP API服务器响应时间过长或不响应。")
                        return False
                except Exception as e:
                    error_msg = str(e)
                    error_type = type(e).__name__
                    progress_bar.progress(100)
                    status_text.error(f"连接错误: {error_type}")
                    
                    # 检查是否与Python版本相关的错误
                    if "TaskGroup" in error_msg or "asyncio" in error_msg:
                        st.error(f"连接错误（可能与Python版本有关）: {error_msg}")
                        st.info("这可能是由于Python版本兼容性问题。尝试使用Python 3.10+可能会解决此问题。")
                    else:
                        st.error(f"连接错误: {error_msg}")
                    
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
                # 使用列布局确保进度条在左侧
                st.subheader(f"执行搜索: {query}")
                
                # 创建专门的进度展示区域，确保进度条靠左对齐
                progress_container = st.container()
                with progress_container:
                    # 创建进度条和状态文本
                    search_progress = st.progress(0)
                    search_status = st.empty()
                    search_status.info("准备搜索...")
                
                # Check if we have a valid search tool
                if not self.search_tool_name:
                    with progress_container:
                        search_progress.progress(100)
                        search_status.error("未找到有效的搜索工具")
                    return {"error": "未找到有效的搜索工具，请确保MCP服务器提供了搜索功能", 
                            "organic": [{"title": "搜索工具不可用", "link": "", 
                            "snippet": "服务器未提供搜索工具。请检查MCP服务器配置或使用其他搜索方法。"}]}
                
                # Prevent empty query
                if not query or len(query.strip()) == 0:
                    with progress_container:
                        search_progress.progress(100)
                        search_status.error("搜索查询不能为空")
                    return {"error": "搜索查询不能为空", 
                            "organic": [{"title": "空查询", "link": "", 
                            "snippet": "请提供有效的搜索查询。"}]}
                
                # Connect to the server using streamable HTTP client
                with progress_container:
                    search_progress.progress(20)
                    search_status.info("建立MCP连接...")
                await asyncio.sleep(0.3)
                
                # Implement retry logic for connection issues
                retry_count = 0
                last_error = None
                
                while retry_count < self.max_retries:
                    try:
                        try:
                            async with asyncio.timeout(30):
                                try:
                                    async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                        with progress_container:
                                            search_progress.progress(40)
                                            search_status.info("创建MCP会话...")
                                        await asyncio.sleep(0.3)
                                        
                                        try:
                                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                                # Initialize the connection
                                                with progress_container:
                                                    search_progress.progress(50)
                                                    search_status.info("初始化会话...")
                                                await asyncio.sleep(0.3)
                                                
                                                try:
                                                    await session.initialize()
                                                
                                                    # Call the web search tool
                                                    with progress_container:
                                                        search_progress.progress(70)
                                                        search_status.info(f"执行搜索: {query}")
                                                        await asyncio.sleep(0.3)
                                                        
                                                    try:
                                                        # 根据工具名称选择参数
                                                        tool_name = self.search_tool_name
                                                        args = None
                                                        
                                                        # 对于不同的工具使用不同的参数格式
                                                        if tool_name == "google_search":
                                                            # google_search需要gl和hl参数
                                                            args = {
                                                                "query": query,
                                                                "gl": "us",
                                                                "hl": "en",
                                                                "numResults": 5
                                                            }
                                                        elif tool_name == "search" or tool_name == "serper-search" or tool_name == "serper":
                                                            # 其他搜索工具可能只需要query
                                                            args = {
                                                                "query": query
                                                            }
                                                        elif tool_name == "scrape":
                                                            # scrape工具使用url参数
                                                            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                                                            args = {"url": search_url}
                                                        else:
                                                            # 默认尝试只提供query
                                                            args = {"query": query}
                                                        
                                                        # 记录调用信息
                                                        with progress_container:
                                                            search_status.info(f"调用 {tool_name} 工具，参数: {args}")
                                                            st.caption("如果搜索失败，可能需要额外的参数，将自动尝试不同参数组合")
                                                        
                                                        # 调用工具
                                                        try:
                                                            result = await session.call_tool(tool_name, arguments=args)
                                                        except Exception as tool_error:
                                                            error_msg = str(tool_error)
                                                            # 如果是参数错误，尝试添加gl和hl参数
                                                            if "query" in error_msg.lower() and "required" in error_msg.lower():
                                                                with progress_container:
                                                                    search_status.warning(f"参数错误，尝试添加gl和hl参数: {error_msg}")
                                                                # 添加额外参数再试一次
                                                                args["gl"] = "us"
                                                                args["hl"] = "en"
                                                                with progress_container:
                                                                    search_status.info(f"重试 {tool_name} 工具，参数: {args}")
                                                                result = await session.call_tool(tool_name, arguments=args)
                                                            else:
                                                                # 其他错误则直接抛出
                                                                raise tool_error
                                                        
                                                        with progress_container:
                                                            search_progress.progress(90)
                                                            search_status.info("处理搜索结果...")
                                                        await asyncio.sleep(0.3)
                                                        
                                                        # 处理不同工具的结果格式
                                                        if hasattr(result, 'result'):
                                                            with progress_container:
                                                                search_progress.progress(100)
                                                            
                                                                # 标准搜索结果处理 (google_search 工具)
                                                                if isinstance(result.result, dict):
                                                                    if "organic" in result.result:
                                                                        with progress_container:
                                                                            search_status.success(f"搜索成功，找到 {len(result.result['organic'])} 条结果")
                                                                        # 格式化和增强搜索结果的显示
                                                                        results = result.result
                                                                        # 确保结果格式一致
                                                                        if "organic" in results:
                                                                            for item in results["organic"]:
                                                                                # 确保有摘要信息
                                                                                if "snippet" not in item and "description" in item:
                                                                                    item["snippet"] = item["description"]
                                                                                # 添加结果评分字段
                                                                                if "score" not in item:
                                                                                    item["score"] = 1.0
                                                                    # google_search 可能返回不同的响应格式
                                                                    elif "results" in result.result:
                                                                        # 重新格式化以保持一致性
                                                                        formatted_results = {"organic": []}
                                                                        for item in result.result["results"]:
                                                                            formatted_item = {
                                                                                "title": item.get("title", "无标题"),
                                                                                "link": item.get("link", ""),
                                                                                "snippet": item.get("snippet", item.get("description", "无摘要"))
                                                                            }
                                                                            formatted_results["organic"].append(formatted_item)
                                                                        search_status.success(f"搜索成功，找到 {len(formatted_results['organic'])} 条结果")
                                                                        result.result = formatted_results
                                                                # scrape工具结果处理
                                                                elif self.search_tool_name == "scrape" and isinstance(result.result, str):
                                                                    with progress_container:
                                                                        search_status.success("网页抓取成功")
                                                                    # 为scrape工具创建一个类似搜索结果的格式
                                                                    return {
                                                                        "organic": [
                                                                            {
                                                                                "title": f"抓取结果: {query}",
                                                                                "link": f"https://www.google.com/search?q={query.replace(' ', '+')}",
                                                                                "snippet": result.result[:500] + "..." if len(result.result) > 500 else result.result
                                                                            }
                                                                        ]
                                                                    }
                                                                else:
                                                                    # 尝试从任何未知格式创建统一的返回结构
                                                                    with progress_container:
                                                                        search_status.warning("搜索完成，但返回了意外格式的结果，尝试适配...")
                                                                        
                                                                        # 如果结果是字符串，转换为有用的结构
                                                                        if isinstance(result.result, str):
                                                                            return {
                                                                                "organic": [
                                                                                    {
                                                                                        "title": f"搜索结果: {query}",
                                                                                        "link": f"https://www.google.com/search?q={query.replace(' ', '+')}",
                                                                                        "snippet": result.result[:500] + "..." if len(result.result) > 500 else result.result
                                                                                    }
                                                                                ]
                                                                            }
                                                                        # 如果结果是列表，转换为有用的结构
                                                                        elif isinstance(result.result, list):
                                                                            organic_results = []
                                                                            for i, item in enumerate(result.result):
                                                                                if isinstance(item, dict):
                                                                                    organic_results.append({
                                                                                        "title": item.get("title", f"结果 {i+1}"),
                                                                                        "link": item.get("link", item.get("url", "")),
                                                                                        "snippet": item.get("snippet", item.get("description", item.get("content", "无摘要")))
                                                                                    })
                                                                            if organic_results:
                                                                                with progress_container:
                                                                                    search_status.success(f"搜索成功，找到 {len(organic_results)} 条结果")
                                                                                return {"organic": organic_results}
                                                            
                                                            return result.result
                                                        else:
                                                            with progress_container:
                                                                search_progress.progress(100)
                                                                search_status.error("搜索结果格式不正确")
                                                            return {"error": "搜索结果格式不正确，缺少result属性", 
                                                                    "organic": [{"title": "无效结果格式", "link": "", 
                                                                    "snippet": "服务器返回的结果格式无效，缺少result属性。"}]}
                                                    except Exception as e:
                                                        error_msg = str(e)
                                                        with progress_container:
                                                            search_progress.progress(100)
                                                        
                                                        # 检查是否存在TaskGroup相关错误或参数错误
                                                        if "TaskGroup" in error_msg:
                                                            with progress_container:
                                                                search_status.warning(f"MCP出现TaskGroup错误，尝试备用搜索方法...")
                                                                st.info("正在使用备用搜索方法...")
                                                            # 使用备用的搜索方法
                                                            return await self._fallback_search(query, search_progress, search_status)
                                                        elif "query" in error_msg.lower() and "required" in error_msg.lower():
                                                            with progress_container:
                                                                search_status.warning(f"API参数错误: {error_msg}，尝试备用搜索方法...")
                                                                st.info("正在使用备用搜索方法...")
                                                            # 使用备用的搜索方法
                                                            return await self._fallback_search(query, search_progress, search_status)
                                                        else:
                                                            with progress_container:
                                                                search_status.error(f"调用{self.search_tool_name}工具时出错")
                                                                st.error(f"调用{self.search_tool_name}工具出错: {error_msg}")
                                                            raise e
                                                except Exception as e:
                                                    error_msg = str(e)
                                                    with progress_container:
                                                        search_progress.progress(100)
                                                    
                                                        # 检查是否存在TaskGroup相关错误或参数错误
                                                        if "TaskGroup" in error_msg:
                                                            with progress_container:
                                                                search_status.warning(f"MCP会话初始化时出现TaskGroup错误，尝试备用搜索方法...")
                                                                st.info("正在使用备用搜索方法...")
                                                            # 使用备用的搜索方法
                                                            return await self._fallback_search(query, search_progress, search_status)
                                                        elif "query" in error_msg.lower() and "required" in error_msg.lower():
                                                            with progress_container:
                                                                search_status.warning(f"API参数错误: {error_msg}，尝试备用搜索方法...")
                                                                st.info("正在使用备用搜索方法...")
                                                            # 使用备用的搜索方法
                                                            return await self._fallback_search(query, search_progress, search_status)
                                                        else:
                                                            with progress_container:
                                                                search_status.error(f"MCP会话初始化失败")
                                                                st.error(f"MCP会话初始化失败: {error_msg}")
                                                            raise e
                                        except Exception as e:
                                            error_msg = str(e)
                                            with progress_container:
                                                search_progress.progress(100)
                                            
                                                # 检查是否存在TaskGroup相关错误
                                                if "TaskGroup" in error_msg:
                                                    with progress_container:
                                                        search_status.warning(f"MCP会话创建时出现TaskGroup错误，尝试备用搜索方法...")
                                                        st.info("正在使用备用搜索方法...")
                                                    # 使用备用的搜索方法
                                                    return await self._fallback_search(query, search_progress, search_status)
                                                else:
                                                    with progress_container:
                                                        search_status.error(f"MCP会话创建失败")
                                                        st.error(f"MCP会话创建失败: {error_msg}")
                                                    raise e
                                except Exception as e:
                                    error_msg = str(e)
                                    with progress_container:
                                        search_progress.progress(100)
                                    
                                    # 检查是否存在TaskGroup相关错误
                                    if "TaskGroup" in error_msg:
                                        with progress_container:
                                            search_status.warning(f"HTTP流连接时出现TaskGroup错误，尝试备用搜索方法...")
                                            st.info("正在使用备用搜索方法...")
                                            # 使用备用的搜索方法
                                            return await self._fallback_search(query, search_progress, search_status)
                                    else:
                                        with progress_container:
                                            search_status.error(f"HTTP流连接失败")
                                            st.error(f"HTTP流连接失败: {error_msg}")
                                            raise e
                        except asyncio.TimeoutError:
                            search_progress.progress(100)
                            search_status.error(f"搜索操作超时(30秒)")
                            raise asyncio.TimeoutError("搜索操作超时(30秒)")
                        # If we get here, search was successful, break retry loop
                        break
                    except Exception as e:
                        retry_count += 1
                        last_error = e
                        error_msg = str(e)
                        error_type = type(e).__name__
                        
                        # 检查是否为TaskGroup错误，如果是，使用备用搜索方法
                        if "TaskGroup" in error_msg:
                            search_status.warning(f"检测到TaskGroup错误，使用备用搜索方法...")
                            return await self._fallback_search(query, search_progress, search_status)
                        
                        search_status.warning(f"搜索尝试 {retry_count}/{self.max_retries} 失败，正在重试...")
                        await asyncio.sleep(1)  # Wait before retrying
                
                # If we've exhausted retries and still have an error
                if retry_count >= self.max_retries and last_error:
                    search_progress.progress(100)
                    if isinstance(last_error, asyncio.TimeoutError):
                        search_status.error("搜索操作多次尝试后仍然超时")
                        return {"error": "搜索操作超时，服务器响应时间过长", 
                                "organic": [{"title": f"搜索超时: {query}", "link": "", 
                                "snippet": "多次尝试后仍然无法获取搜索结果，服务器响应时间过长。请稍后再试或使用不同的查询。"}]}
                    else:
                        error_msg = str(last_error)
                        error_type = type(last_error).__name__
                        
                        # 如果是TaskGroup错误，使用备用搜索方法
                        if "TaskGroup" in error_msg:
                            search_status.warning(f"多次尝试后仍出现TaskGroup错误，使用备用搜索方法...")
                            return await self._fallback_search(query, search_progress, search_status)
                            
                        search_status.error(f"多次尝试后仍然出错: {error_type}")
                        
                        return {"error": f"多次尝试后搜索仍然失败: {error_msg}",
                                "organic": [{"title": f"搜索错误: {query}", "link": "", 
                                "snippet": f"多次尝试后搜索仍然失败。错误类型: {error_type}。错误详情: {error_msg[:200]}..."}]}
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            with main_container:
                if "TaskGroup" in error_msg:
                    search_status = st.empty()
                    search_progress = st.progress(0)
                    search_status.warning(f"执行Web搜索时出现TaskGroup错误，使用备用搜索方法...")
                    # 使用备用搜索方法
                    return await self._fallback_search(query, search_progress, search_status)
                else:
                    st.error(f"执行Web搜索时出错: {error_msg}")
            
            return {"error": f"执行Web搜索时出错: {error_msg}", 
                    "organic": [{"title": "搜索系统错误", "link": "", 
                    "snippet": f"执行搜索时遇到系统错误: {error_type}: {error_msg[:200]}..."}]}
    
    async def _fallback_search(self, query: str, progress_bar=None, status_text=None) -> Dict[str, Any]:
        """
        备用搜索方法，直接使用Serper API而不通过MCP，避免TaskGroup错误。
        
        Args:
            query: 搜索查询
            progress_bar: 进度条组件
            status_text: 状态文本组件
            
        Returns:
            搜索结果字典
        """
        try:
            # 使用已有的进度组件或创建新的
            parent_container = None
            local_progress_bar = progress_bar
            local_status_text = status_text
            
            # 如果未提供进度组件，创建新的
            if not progress_bar or not status_text:
                parent_container = st.container()
                with parent_container:
                    st.subheader(f"执行备用搜索: {query}")
                    progress_container = st.container()
                    with progress_container:
                        local_progress_bar = st.progress(0)
                        local_status_text = st.empty()
                        local_status_text.info("准备使用备用搜索方法...")
            
            # 使用进度组件进行进度更新
            if local_progress_bar and local_status_text:
                local_progress_bar.progress(30)
                local_status_text.info("使用备用搜索方法...")
            
            # 直接使用Serper API进行搜索
            if not self.serper_api_key:
                if local_progress_bar and local_status_text:
                    local_progress_bar.progress(100)
                    local_status_text.error("缺少Serper API密钥")
                
                return {
                    "error": "缺少Serper API密钥，无法执行备用搜索",
                    "organic": [
                        {
                            "title": f"无法搜索: {query}",
                            "link": "",
                            "snippet": "系统缺少Serper API密钥，无法执行备用搜索。请检查配置。"
                        }
                    ]
                }
            
            # 更新UI
            if local_progress_bar and local_status_text:
                local_progress_bar.progress(50)
                local_status_text.info(f"直接调用Serper API搜索: {query}")
            
            # 构建Serper API请求
            serper_url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "q": query,
                "gl": "us",
                "hl": "en"
            }
            
            # 记录搜索参数
            if local_progress_bar and local_status_text:
                local_status_text.info(f"搜索参数: query={query}, gl=us, hl=en")
            
            # 发送请求到Serper API
            response = requests.post(serper_url, headers=headers, json=payload)
            
            # 更新UI
            if local_progress_bar and local_status_text:
                local_progress_bar.progress(80)
                local_status_text.info(f"处理备用搜索结果... (状态码: {response.status_code})")
            
            # 检查响应
            if response.status_code == 200:
                data = response.json()
                
                # 标准化结果格式
                if "organic" in data:
                    # 更新UI
                    if local_progress_bar and local_status_text:
                        local_progress_bar.progress(100)
                        local_status_text.success(f"备用搜索成功，找到 {len(data['organic'])} 条结果")
                    
                    return data
                else:
                    # 创建一个标准格式的结果
                    formatted_results = {"organic": []}
                    
                    # 处理可能的不同结果格式
                    if "results" in data:
                        for item in data["results"]:
                            formatted_results["organic"].append({
                                "title": item.get("title", "无标题"),
                                "link": item.get("link", ""),
                                "snippet": item.get("snippet", "无摘要")
                            })
                    
                    # 更新UI
                    if local_progress_bar and local_status_text:
                        local_progress_bar.progress(100)
                        local_status_text.success(f"备用搜索成功，找到 {len(formatted_results['organic'])} 条结果")
                    
                    return formatted_results
            else:
                # 处理API错误
                if local_progress_bar and local_status_text:
                    local_progress_bar.progress(100)
                    local_status_text.error(f"备用搜索失败: {response.status_code}")
                    
                    # 显示响应内容以帮助调试
                    try:
                        error_content = response.json()
                        st.error(f"API错误: {json.dumps(error_content)}")
                    except:
                        st.error(f"API响应: {response.text}")
                
                return {
                    "error": f"备用搜索API调用失败: {response.status_code} - {response.text}",
                    "organic": [
                        {
                            "title": f"搜索失败: {query}",
                            "link": "",
                            "snippet": f"备用搜索请求失败，状态码: {response.status_code}。请尝试其他搜索方法。"
                        }
                    ]
                }
        except Exception as e:
            error_msg = str(e)
            
            # 更新UI
            if local_progress_bar and local_status_text:
                local_progress_bar.progress(100)
                local_status_text.error(f"备用搜索出错: {error_msg}")
            
            # 使用模拟数据
            return {
                "error": f"备用搜索方法出错: {error_msg}",
                "organic": [
                    {
                        "title": f"搜索查询: {query}",
                        "link": f"https://www.google.com/search?q={query.replace(' ', '+')}",
                        "snippet": "由于搜索功能暂时不可用，请直接访问Google搜索此查询。备用搜索方法也失败了。"
                    }
                ]
            }
    
    def run_async(self, coroutine):
        """Helper method to run async methods synchronously."""
        return asyncio.run(coroutine) 