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
        # 如果没有提供容器，创建一个新的
        if main_container is None:
            main_container = st.container()
            
        # 所有UI元素都将在这个容器中创建，避免出现在侧边栏
        with main_container:
            # 检查API密钥
            if not self.serper_api_key or not self.smithery_api_key:
                st.error("无法初始化: SERPER_API_KEY 或 SMITHERY_API_KEY 未设置。")
                return False
                
            # 检查URL格式
            if not self.url.startswith("https://"):
                st.error(f"错误的URL格式: {self.url[:15]}...")
                return False
            
            # 创建标题和进度显示区域
            st.write("## MCP连接进度")
            
            # 创建简单的进度条和状态文本，避免复杂的嵌套容器
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # 显示基本连接信息
                status_text.info("开始初始化Serper MCP服务")
                base_url = self.url.split("?")[0]
                st.caption(f"连接到服务器: {base_url}")
                
                # 第一步：准备连接
                progress_bar.progress(10)
                status_text.info("正在检查连接参数...")
                await asyncio.sleep(0.3)
                
                # 第二步：建立HTTP流连接
                progress_bar.progress(30)
                status_text.info("开始HTTP流式连接...")
                
                try:
                    async with asyncio.timeout(30):
                        try:
                            # 使用streamable_http_client连接到服务器
                            async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                progress_bar.progress(50)
                                status_text.info("HTTP流式连接成功，创建MCP会话...")
                                await asyncio.sleep(0.3)
                                
                                try:
                                    # 创建MCP会话
                                    async with mcp.ClientSession(read_stream, write_stream) as session:
                                        progress_bar.progress(60)
                                        status_text.info("初始化MCP会话...")
                                        await asyncio.sleep(0.3)
                                        
                                        # 初始化MCP会话
                                        await session.initialize()
                                        
                                        # 获取可用工具列表
                                        progress_bar.progress(80)
                                        status_text.info("获取可用工具列表...")
                                        await asyncio.sleep(0.3)
                                        
                                        # 获取工具列表
                                        tools_result = await session.list_tools()
                                        self.available_tools = [t.name for t in tools_result.tools]
                                        
                                        # 查找可用的搜索工具
                                        progress_bar.progress(90)
                                        status_text.info("检测可用的搜索工具...")
                                        
                                        # 可能的搜索工具名称
                                        search_tool_candidates = [
                                            "google_search",
                                            "search", 
                                            "serper-search", 
                                            "web-search",
                                            "google-search",
                                            "serper",
                                            "scrape"
                                        ]
                                        
                                        # 尝试精确匹配
                                        for tool_name in search_tool_candidates:
                                            if tool_name in self.available_tools:
                                                self.search_tool_name = tool_name
                                                break
                                        
                                        # 如果没找到精确匹配，尝试模糊匹配
                                        if not self.search_tool_name:
                                            for tool_name in self.available_tools:
                                                if "search" in tool_name.lower():
                                                    self.search_tool_name = tool_name
                                                    break
                                        
                                        # 连接成功，更新UI
                                        progress_bar.progress(100)
                                        
                                        if self.search_tool_name:
                                            status_text.success(f"MCP连接成功! 已选择搜索工具: {self.search_tool_name}")
                                            st.success(f"可用工具: {', '.join(self.available_tools)}")
                                            return True
                                        elif "scrape" in self.available_tools:
                                            self.search_tool_name = "scrape"
                                            status_text.warning("未找到搜索工具，将使用scrape工具作为替代")
                                            st.success(f"可用工具: {', '.join(self.available_tools)}")
                                            return True
                                        else:
                                            status_text.error("MCP连接成功，但未找到可用的搜索工具!")
                                            st.warning(f"可用工具: {', '.join(self.available_tools)}")
                                            return False
                                            
                                except Exception as e:
                                    error_msg = str(e)
                                    error_type = type(e).__name__
                                    
                                    progress_bar.progress(100)
                                    if "TaskGroup" in error_msg:
                                        status_text.error("MCP会话异步任务组错误")
                                        st.error(f"MCP会话出现TaskGroup错误，这可能是由于Python版本兼容性问题或MCP服务器内部错误。错误详情: {error_msg}")
                                    else:
                                        status_text.error(f"MCP会话错误: {error_type}")
                                        st.error(f"MCP会话错误: {error_msg}")
                                    
                                    return False
                        except Exception as e:
                            error_msg = str(e)
                            error_type = type(e).__name__
                            
                            progress_bar.progress(100)
                            status_text.error(f"MCP连接失败: {error_type}")
                            
                            if "401" in error_msg:
                                st.error("API密钥验证失败。请检查SMITHERY_API_KEY是否正确。")
                            elif "404" in error_msg:
                                st.error("无法找到MCP服务器端点。请检查URL是否正确。")
                            elif "TaskGroup" in error_msg:
                                st.error("MCP连接出现TaskGroup错误，这可能是由于Python版本兼容性问题。")
                            else:
                                st.error(f"MCP连接失败: {error_msg}")
                            
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
                
                if "TaskGroup" in error_msg or "asyncio" in error_msg:
                    st.error(f"连接错误（可能与Python版本有关）: {error_msg}")
                else:
                    st.error(f"连接错误: {error_msg}")
                
                return False
    
    async def scrape_url(self, url: str, main_container=None) -> str:
        """
        抓取指定URL的内容
        
        Args:
            url: 要抓取的URL
            main_container: 用于显示进度的容器
            
        Returns:
            抓取的内容
        """
        # 如果没有提供容器，创建一个新的
        if main_container is None:
            main_container = st.container()
            
        with main_container:
            scrape_status = st.empty()
            scrape_status.info(f"正在抓取网页内容: {url}")
            
            try:
                if not self.search_tool_name or self.search_tool_name != "scrape":
                    scrape_status.error("未找到有效的抓取工具")
                    return f"无法抓取 {url} 的内容：未找到有效的抓取工具"
                
                # 抓取逻辑
                try:
                    async with asyncio.timeout(30):
                        # 使用streamable_http_client连接到服务器
                        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                            # 创建MCP会话
                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                # 初始化会话
                                await session.initialize()
                                
                                # 准备抓取参数
                                args = {"url": url}
                                
                                # 显示调用信息
                                scrape_status.info(f"抓取网页: {url}")
                                
                                # 调用工具
                                result = await session.call_tool("scrape", arguments=args)
                                
                                # 处理结果
                                scrape_status.success(f"成功抓取网页内容")
                                
                                # 返回结果
                                if hasattr(result, 'result') and isinstance(result.result, str):
                                    return result.result
                                else:
                                    return "抓取结果格式不正确"
                except Exception as e:
                    scrape_status.error(f"抓取过程中出错: {str(e)}")
                    return f"抓取 {url} 失败: {str(e)}"
            except Exception as e:
                scrape_status.error(f"抓取设置出错: {str(e)}")
                return f"抓取 {url} 失败: {str(e)}"
                
    async def search_web(self, query: str, main_container=None) -> Dict[str, Any]:
        """
        Perform a web search using the Serper MCP server.
        
        Args:
            query: The search query
            main_container: Container to display progress in
            
        Returns:
            Dictionary containing search results
        """
        # 如果没有提供容器，创建一个新的
        if main_container is None:
            main_container = st.container()
        
        # 所有UI元素都在这个容器内
        with main_container:
            # 显示搜索标题和进度条
            st.write(f"## 执行搜索: {query}")
            
            # 直接创建进度条和状态文本，不使用多层嵌套
            search_progress = st.progress(0)
            search_status = st.empty()
            search_status.info("准备搜索...")
            
            # 检查搜索工具是否可用
            if not self.search_tool_name:
                search_progress.progress(100)
                search_status.error("未找到有效的搜索工具")
                return {"error": "未找到有效的搜索工具，请确保MCP服务器提供了搜索功能", 
                        "organic": [{"title": "搜索工具不可用", "link": "", 
                        "snippet": "服务器未提供搜索工具。请检查MCP服务器配置或使用其他搜索方法。"}]}
            
            # 防止空查询
            if not query or len(query.strip()) == 0:
                search_progress.progress(100)
                search_status.error("搜索查询不能为空")
                return {"error": "搜索查询不能为空", 
                        "organic": [{"title": "空查询", "link": "", 
                        "snippet": "请提供有效的搜索查询。"}]}
            
            try:
                # 开始连接到服务器
                search_progress.progress(20)
                search_status.info("建立MCP连接...")
                await asyncio.sleep(0.3)
                
                # 实现重试逻辑
                retry_count = 0
                last_error = None
                
                while retry_count < self.max_retries:
                    try:
                        # 更新进度
                        search_progress.progress(30)
                        search_status.info("创建HTTP流式连接...")
                        
                        # 尝试连接
                        try:
                            async with asyncio.timeout(30):
                                # 使用streamable_http_client连接到服务器
                                async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                    search_progress.progress(40)
                                    search_status.info("创建MCP会话...")
                                    await asyncio.sleep(0.3)
                                    
                                    # 创建MCP会话
                                    async with mcp.ClientSession(read_stream, write_stream) as session:
                                        # 初始化会话
                                        search_progress.progress(50)
                                        search_status.info("初始化会话...")
                                        await asyncio.sleep(0.3)
                                        
                                        await session.initialize()
                                        
                                        # 执行搜索
                                        search_progress.progress(70)
                                        search_status.info(f"执行搜索: {query}")
                                        await asyncio.sleep(0.3)
                                        
                                        # 准备搜索参数
                                        tool_name = self.search_tool_name
                                        args = None
                                        
                                        # 根据工具名选择参数
                                        if tool_name == "google_search":
                                            args = {
                                                "query": query,
                                                "gl": "us",
                                                "hl": "en",
                                                "numResults": 5
                                            }
                                        elif tool_name == "search" or tool_name == "serper-search" or tool_name == "serper":
                                            args = {"query": query}
                                        elif tool_name == "scrape":
                                            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                                            args = {"url": search_url}
                                        else:
                                            args = {"query": query}
                                        
                                        # 显示调用信息
                                        search_status.info(f"调用 {tool_name} 工具，参数: {args}")
                                        
                                        # 调用工具
                                        try:
                                            result = await session.call_tool(tool_name, arguments=args)
                                        except Exception as tool_error:
                                            error_msg = str(tool_error)
                                            # 处理参数错误
                                            if "query" in error_msg.lower() and "required" in error_msg.lower():
                                                search_status.warning(f"参数错误，尝试添加gl和hl参数: {error_msg}")
                                                # 添加额外参数再试
                                                args["gl"] = "us"
                                                args["hl"] = "en"
                                                search_status.info(f"重试 {tool_name} 工具，参数: {args}")
                                                result = await session.call_tool(tool_name, arguments=args)
                                            else:
                                                raise tool_error
                                        
                                        # 处理结果
                                        search_progress.progress(90)
                                        search_status.info("处理搜索结果...")
                                        await asyncio.sleep(0.3)
                                        
                                        # 检查结果格式
                                        if hasattr(result, 'result'):
                                            search_progress.progress(95)
                                            
                                            # 标准搜索结果处理
                                            if isinstance(result.result, dict):
                                                if "organic" in result.result:
                                                    search_status.success(f"搜索成功，找到 {len(result.result['organic'])} 条结果")
                                                    
                                                    # 如果有scrape工具可用，尝试抓取前两个结果的页面内容
                                                    if "scrape" in self.available_tools and len(result.result['organic']) > 0:
                                                        search_status.info("正在抓取前两个搜索结果的页面内容...")
                                                        
                                                        try:
                                                            # 最多抓取前两个结果
                                                            pages_to_scrape = min(2, len(result.result['organic']))
                                                            for i in range(pages_to_scrape):
                                                                url = result.result['organic'][i].get('link', '')
                                                                if url and url.startswith('http'):
                                                                    search_status.info(f"抓取结果 {i+1}: {url}")
                                                                    
                                                                    # 抓取页面内容
                                                                    content = await self.scrape_url(url, main_container)
                                                                    
                                                                    # 将内容添加到搜索结果中
                                                                    result.result['organic'][i]['page_content'] = content[:15000] if len(content) > 15000 else content
                                                                    
                                                            search_status.success(f"已抓取 {pages_to_scrape} 个搜索结果的详细内容")
                                                        except Exception as e:
                                                            search_status.warning(f"抓取页面内容时出错: {str(e)}")
                                                    
                                                    # 返回结果
                                                    search_progress.progress(100)
                                                    return result.result
                                            # 处理scrape工具的结果
                                            elif self.search_tool_name == "scrape" and isinstance(result.result, str):
                                                search_status.success("网页抓取成功")
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
                                                # 处理未知结果格式
                                                search_status.warning("结果格式未知，尝试适配...")
                                                
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
                                                        search_status.success(f"搜索成功，找到 {len(organic_results)} 条结果")
                                                        return {"organic": organic_results}
                                            
                                            # 返回原始结果
                                            return result.result
                                        else:
                                            search_progress.progress(100)
                                            search_status.error("搜索结果格式不正确")
                                            return {"error": "搜索结果格式不正确，缺少result属性", 
                                                "organic": [{"title": "无效结果格式", "link": "", 
                                                "snippet": "服务器返回的结果格式无效，缺少result属性。"}]}
                        except asyncio.TimeoutError:
                            search_progress.progress(100)
                            search_status.error("搜索操作超时(30秒)")
                            raise asyncio.TimeoutError("搜索操作超时(30秒)")
                        
                        # 如果到这里，搜索成功，跳出重试循环
                        break
                    except Exception as e:
                        retry_count += 1
                        last_error = e
                        error_msg = str(e)
                        
                        # 检查是否为TaskGroup错误
                        if "TaskGroup" in error_msg:
                            search_status.warning("检测到TaskGroup错误，使用备用搜索方法...")
                            return await self._fallback_search(query, search_progress, search_status)
                        
                        # 显示重试信息
                        search_status.warning(f"搜索尝试 {retry_count}/{self.max_retries} 失败，正在重试...")
                        await asyncio.sleep(1)
                
                # 如果重试后仍有错误
                if retry_count >= self.max_retries and last_error:
                    search_progress.progress(100)
                    
                    if isinstance(last_error, asyncio.TimeoutError):
                        search_status.error("搜索操作多次尝试后仍然超时")
                        return {"error": "搜索操作超时，服务器响应时间过长",
                                "organic": [{"title": f"搜索超时: {query}", "link": "", 
                                "snippet": "多次尝试后仍然无法获取搜索结果，服务器响应时间过长。"}]}
                    else:
                        error_msg = str(last_error)
                        
                        # 如果是TaskGroup错误，使用备用搜索
                        if "TaskGroup" in error_msg:
                            search_status.warning("多次尝试后仍出现TaskGroup错误，使用备用搜索方法...")
                            return await self._fallback_search(query, search_progress, search_status)
                        
                        # 其他错误
                        search_status.error(f"多次尝试后仍然出错: {type(last_error).__name__}")
                        return {"error": f"多次尝试后搜索仍然失败: {error_msg}",
                                "organic": [{"title": f"搜索错误: {query}", "link": "", 
                                "snippet": f"多次尝试后搜索仍然失败。错误详情: {error_msg[:200]}..."}]}
            
            except Exception as e:
                # 捕获所有其他异常
                error_msg = str(e)
                search_progress.progress(100)
                
                # 如果是TaskGroup错误，使用备用搜索
                if "TaskGroup" in error_msg:
                    search_status.warning("执行Web搜索时出现TaskGroup错误，使用备用搜索方法...")
                    return await self._fallback_search(query, search_progress, search_status)
                else:
                    search_status.error(f"执行Web搜索时出错: {error_msg}")
                    return {"error": f"执行Web搜索时出错: {error_msg}", 
                            "organic": [{"title": "搜索系统错误", "link": "", 
                            "snippet": f"执行搜索时遇到系统错误: {error_msg[:200]}..."}]}
    
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
            # 使用已有的UI组件或创建新的
            if progress_bar is None or status_text is None:
                # 需要创建新的UI组件
                container = st.container()
                with container:
                    st.write("## 使用备用搜索方法")
                    progress_bar = st.progress(0)
                    status_text = st.empty()
            
            # 更新UI状态
            progress_bar.progress(30)
            status_text.info("使用备用搜索方法...")
            
            # 直接使用Serper API进行搜索
            if not self.serper_api_key:
                progress_bar.progress(100)
                status_text.error("缺少Serper API密钥")
                
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
            
            # 更新UI进度
            progress_bar.progress(50)
            status_text.info(f"直接调用Serper API搜索: {query}")
            
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
            status_text.info(f"搜索参数: query={query}, gl=us, hl=en")
            
            # 发送请求到Serper API
            response = requests.post(serper_url, headers=headers, json=payload)
            
            # 更新UI进度
            progress_bar.progress(80)
            status_text.info(f"处理备用搜索结果... (状态码: {response.status_code})")
            
            # 检查响应
            if response.status_code == 200:
                data = response.json()
                
                # 标准化结果格式
                if "organic" in data:
                    # 如果有scrape工具可用，尝试抓取前两个结果的页面内容
                    if "scrape" in self.available_tools and len(data['organic']) > 0:
                        status_text.info("正在抓取前两个搜索结果的页面内容...")
                        
                        try:
                            # 最多抓取前两个结果
                            pages_to_scrape = min(2, len(data['organic']))
                            for i in range(pages_to_scrape):
                                url = data['organic'][i].get('link', '')
                                if url and url.startswith('http'):
                                    status_text.info(f"抓取结果 {i+1}: {url}")
                                    
                                    # 创建容器以显示抓取进度
                                    scrape_container = st.container()
                                    
                                    # 抓取页面内容
                                    content = await self.scrape_url(url, scrape_container)
                                    
                                    # 将内容添加到搜索结果中
                                    data['organic'][i]['page_content'] = content[:15000] if len(content) > 15000 else content
                                    
                            status_text.success(f"已抓取 {pages_to_scrape} 个搜索结果的详细内容")
                        except Exception as e:
                            status_text.warning(f"抓取页面内容时出错: {str(e)}")
                    
                    progress_bar.progress(100)
                    status_text.success(f"备用搜索成功，找到 {len(data['organic'])} 条结果")
                    return data
                else:
                    # 创建标准格式的结果
                    formatted_results = {"organic": []}
                    
                    # 处理不同结果格式
                    if "results" in data:
                        for item in data["results"]:
                            formatted_results["organic"].append({
                                "title": item.get("title", "无标题"),
                                "link": item.get("link", ""),
                                "snippet": item.get("snippet", "无摘要")
                            })
                    
                    # 如果有scrape工具可用，尝试抓取前两个结果的页面内容
                    if "scrape" in self.available_tools and len(formatted_results['organic']) > 0:
                        status_text.info("正在抓取前两个搜索结果的页面内容...")
                        
                        try:
                            # 最多抓取前两个结果
                            pages_to_scrape = min(2, len(formatted_results['organic']))
                            for i in range(pages_to_scrape):
                                url = formatted_results['organic'][i].get('link', '')
                                if url and url.startswith('http'):
                                    status_text.info(f"抓取结果 {i+1}: {url}")
                                    
                                    # 创建容器以显示抓取进度
                                    scrape_container = st.container()
                                    
                                    # 抓取页面内容
                                    content = await self.scrape_url(url, scrape_container)
                                    
                                    # 将内容添加到搜索结果中
                                    formatted_results['organic'][i]['page_content'] = content[:15000] if len(content) > 15000 else content
                                    
                            status_text.success(f"已抓取 {pages_to_scrape} 个搜索结果的详细内容")
                        except Exception as e:
                            status_text.warning(f"抓取页面内容时出错: {str(e)}")
                    
                    progress_bar.progress(100)
                    status_text.success(f"备用搜索成功，找到 {len(formatted_results['organic'])} 条结果")
                    return formatted_results
            else:
                # 处理API错误
                progress_bar.progress(100)
                status_text.error(f"备用搜索失败: {response.status_code}")
                
                # 显示错误详情
                try:
                    error_content = response.json()
                    st.error(f"API错误: {json.dumps(error_content)}")
                except:
                    st.error(f"API响应: {response.text}")
                
                return {
                    "error": f"备用搜索API调用失败: {response.status_code}",
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
            
            # 更新UI状态
            if progress_bar and status_text:
                progress_bar.progress(100)
                status_text.error(f"备用搜索出错: {error_msg}")
            
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