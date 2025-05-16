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
            # 显示初始化标题
            st.write("## MCP服务连接初始化")
            
            # 检查API密钥
            if not self.serper_api_key or not self.smithery_api_key:
                st.error("无法初始化: SERPER_API_KEY 或 SMITHERY_API_KEY 未设置。")
                return False
                
            # 检查URL格式
            if not self.url.startswith("https://"):
                st.error(f"错误的URL格式: {self.url[:15]}...")
                return False
            
            # 创建诊断信息区域
            with st.expander("MCP连接诊断信息", expanded=False):
                st.caption("连接参数:")
                st.code(f"服务器URL: {self.url.split('?')[0]}\nSerper API Key: {'已设置' if self.serper_api_key else '未设置'}\nSmithery API Key: {'已设置' if self.smithery_api_key else '未设置'}")
                st.caption("当前环境信息:")
                import platform
                import sys
                st.code(f"Python版本: {sys.version}\n操作系统: {platform.system()} {platform.version()}\nMCP客户端版本: {mcp.__version__ if hasattr(mcp, '__version__') else '未知'}")
                
                # 显示配置
                st.caption("配置信息:")
                import json
                st.code(json.dumps(self.config, indent=2))
            
            # 创建简单的进度条和状态文本
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # 显示基本连接信息
                status_text.info("开始初始化Serper MCP服务")
                
                # 第一步：准备连接
                progress_bar.progress(10)
                status_text.info("正在检查连接参数...")
                await asyncio.sleep(0.3)
                
                # 创建临时全局错误日志
                error_log_container = st.container()
                with error_log_container:
                    error_log = st.empty()
                
                # 使用异步超时机制防止连接卡住
                try:
                    async with asyncio.timeout(40):  # 增加超时时间到40秒
                        # 第二步：建立HTTP流连接
                        progress_bar.progress(30)
                        status_text.info("开始HTTP流式连接...")
                        
                        # 使用try-except分离不同阶段的错误
                        try:
                            # 尝试建立连接
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
                                        
                                        # 保存工具列表
                                        if hasattr(tools_result, 'tools'):
                                            self.available_tools = [t.name for t in tools_result.tools]
                                            
                                            # 在诊断区域显示所有工具
                                            with st.expander("可用工具", expanded=False):
                                                for tool in tools_result.tools:
                                                    st.caption(f"工具: {tool.name}")
                                                    if hasattr(tool, 'description'):
                                                        st.caption(f"描述: {tool.description}")
                                        else:
                                            status_text.warning("无法获取工具列表，tools_result没有'tools'属性")
                                            with st.expander("工具检查结果", expanded=True):
                                                st.code(f"工具结果: {str(tools_result)}")
                                            self.available_tools = []
                                        
                                        # 查找可用的搜索工具
                                        progress_bar.progress(90)
                                        status_text.info("检测可用的搜索工具...")
                                        
                                        # 可能的搜索工具名称
                                        search_tool_candidates = [
                                            "google_search",
                                            "serper-google-search",
                                            "search", 
                                            "serper-search", 
                                            "web-search",
                                            "google-search",
                                            "serper",
                                            "scrape"
                                        ]
                                        
                                        # 显示工具选择过程
                                        with st.expander("工具选择过程", expanded=False):
                                            st.write("候选搜索工具:", search_tool_candidates)
                                            st.write("可用工具:", self.available_tools)
                                        
                                        # 尝试精确匹配
                                        for tool_name in search_tool_candidates:
                                            if tool_name in self.available_tools:
                                                self.search_tool_name = tool_name
                                                with st.expander("工具选择过程", expanded=False):
                                                    st.success(f"精确匹配到搜索工具: {tool_name}")
                                                break
                                        
                                        # 如果没找到精确匹配，尝试模糊匹配
                                        if not self.search_tool_name:
                                            for tool_name in self.available_tools:
                                                if "search" in tool_name.lower() or "google" in tool_name.lower():
                                                    self.search_tool_name = tool_name
                                                    with st.expander("工具选择过程", expanded=False):
                                                        st.success(f"模糊匹配到搜索工具: {tool_name}")
                                                    break
                                        
                                        # 连接成功，更新UI
                                        progress_bar.progress(100)
                                        
                                        if self.search_tool_name:
                                            status_text.success(f"MCP连接成功! 已选择搜索工具: {self.search_tool_name}")
                                            return True
                                        elif len(self.available_tools) > 0:
                                            # 如果有任何工具可用，选择第一个
                                            self.search_tool_name = self.available_tools[0]
                                            status_text.warning(f"未找到专用搜索工具，将使用 {self.search_tool_name} 工具作为替代")
                                            return True
                                        else:
                                            status_text.error("MCP连接成功，但未找到任何可用工具!")
                                            return False
                                        
                                except Exception as e:
                                    error_msg = str(e)
                                    error_type = type(e).__name__
                                    
                                    progress_bar.progress(100)
                                    if "TaskGroup" in error_msg:
                                        status_text.error("MCP会话异步任务组错误")
                                        error_log.error(f"会话错误详情: {error_msg}")
                                        st.error(f"MCP会话出现TaskGroup错误，这可能是由于Python版本兼容性问题或MCP服务器内部错误。")
                                    else:
                                        status_text.error(f"MCP会话错误: {error_type}")
                                        error_log.error(f"会话错误详情: {error_msg}")
                                    
                                    return False
                                
                        except Exception as e:
                            error_msg = str(e)
                            error_type = type(e).__name__
                            
                            progress_bar.progress(100)
                            status_text.error(f"MCP连接失败: {error_type}")
                            error_log.error(f"连接错误详情: {error_msg}")
                            
                            if "401" in error_msg:
                                st.error("API密钥验证失败。请检查SMITHERY_API_KEY是否正确。")
                            elif "404" in error_msg:
                                st.error("无法找到MCP服务器端点。请检查URL是否正确。")
                            elif "TaskGroup" in error_msg:
                                st.error("MCP连接出现TaskGroup错误，这可能是由于Python版本兼容性问题。")
                            else:
                                st.error(f"MCP连接失败: {error_type}")
                            
                            return False
                
                except asyncio.TimeoutError:
                    progress_bar.progress(100)
                    status_text.error("连接超时(40秒)")
                    st.error("连接超时(40秒)。Serper MCP API服务器响应时间过长或不响应。")
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
            
            # 检查是否有搜索工具可用
            if not self.search_tool_name:
                scrape_status.error("未找到有效的搜索工具")
                return f"无法抓取 {url} 的内容：未找到有效的搜索工具"
            
            # 最大重试次数
            max_retries = 3
            current_retry = 0
            
            while current_retry < max_retries:
                try:
                    # 使用不同的工具尝试抓取
                    if current_retry == 0:
                        # 第一次尝试：使用当前搜索工具
                        tool_name = self.search_tool_name
                        scrape_status.info(f"尝试使用 {tool_name} 抓取 (尝试 {current_retry+1}/{max_retries})")
                    elif current_retry == 1:
                        # 第二次尝试：使用"google_search"工具
                        tool_name = "google_search"
                        scrape_status.info(f"尝试使用备用方法 google_search 抓取 (尝试 {current_retry+1}/{max_retries})")
                    else:
                        # 第三次尝试：使用"serper"或"search"工具
                        if "serper" in self.available_tools:
                            tool_name = "serper"
                        elif "search" in self.available_tools:
                            tool_name = "search"
                        else:
                            tool_name = self.search_tool_name
                        scrape_status.info(f"尝试使用备用方法 {tool_name} 抓取 (尝试 {current_retry+1}/{max_retries})")
                    
                    # 调用MCP抓取
                    try:
                        # 设置更短的超时时间避免长时间等待
                        async with asyncio.timeout(25):
                            # 使用streamable_http_client连接到服务器
                            async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                # 创建MCP会话
                                async with mcp.ClientSession(read_stream, write_stream) as session:
                                    # 初始化会话
                                    await session.initialize()
                                    
                                    # 准备参数
                                    args = None
                                    
                                    # 根据工具类型选择合适的参数
                                    if tool_name == "scrape":
                                        # 使用专门的抓取工具
                                        args = {"url": url}
                                        scrape_status.info(f"使用scrape工具抓取网页: {url}")
                                    elif "search" in tool_name.lower() or tool_name in ["google_search", "serper", "serper-search"]:
                                        # 使用搜索工具抓取特定URL的信息
                                        # 根据URL构建更精确的搜索查询
                                        domain = url.split('//')[-1].split('/')[0]
                                        path = '/'.join(url.split('/')[3:]) if len(url.split('/')) > 3 else ""
                                        search_query = f"site:{domain}"
                                        
                                        if path:
                                            # 尝试提取页面关键词用于搜索
                                            path_keywords = ' '.join(path.replace('-', ' ').replace('_', ' ').split('/'))
                                            if len(path_keywords) > 0:
                                                search_query += f" {path_keywords}"
                                                
                                        scrape_status.info(f"搜索查询: {search_query}")
                                        
                                        if tool_name == "google_search":
                                            args = {
                                                "query": search_query,
                                                "gl": "us",
                                                "hl": "en",
                                                "numResults": 3
                                            }
                                        else:
                                            args = {"query": search_query}
                                        
                                        scrape_status.info(f"使用{tool_name}工具查询网页内容")
                                    else:
                                        # 尝试使用其他工具
                                        args = {"url": url}
                                        scrape_status.info(f"尝试使用{tool_name}工具抓取网页")
                                    
                                    # 调用MCP工具
                                    result = await session.call_tool(tool_name, arguments=args)
                                    
                                    # 处理结果
                                    if hasattr(result, 'result'):
                                        # 成功获取结果
                                        scrape_status.success(f"MCP {tool_name} 成功获取内容")
                                        
                                        if isinstance(result.result, str):
                                            return result.result
                                        elif isinstance(result.result, dict):
                                            # 从搜索结果中提取内容
                                            if "organic" in result.result and len(result.result["organic"]) > 0:
                                                # 合并前3个结果的内容
                                                organic_results = result.result["organic"][:3]
                                                combined_content = ""
                                                
                                                for i, item in enumerate(organic_results):
                                                    title = item.get("title", f"结果 {i+1}")
                                                    snippet = item.get("snippet", "")
                                                    
                                                    combined_content += f"## {title}\n\n{snippet}\n\n"
                                                    
                                                    # 添加链接信息
                                                    if "link" in item:
                                                        combined_content += f"链接: {item['link']}\n\n"
                                                    
                                                    # 添加分隔符
                                                    if i < len(organic_results) - 1:
                                                        combined_content += "---\n\n"
                                                
                                                return combined_content
                                            else:
                                                # 返回JSON格式的结果
                                                return json.dumps(result.result, ensure_ascii=False, indent=2)
                                        elif isinstance(result.result, list):
                                            # 处理列表类型的结果
                                            list_content = ""
                                            for i, item in enumerate(result.result[:5]):  # 最多取前5项
                                                if isinstance(item, dict):
                                                    title = item.get("title", f"项目 {i+1}")
                                                    content = item.get("content", item.get("snippet", item.get("description", "")))
                                                    list_content += f"## {title}\n\n{content}\n\n"
                                                else:
                                                    list_content += f"## 项目 {i+1}\n\n{str(item)}\n\n"
                                            
                                            return list_content if list_content else "获取到列表结果，但内容为空"
                                        else:
                                            # 其他类型的结果转为字符串
                                            return str(result.result)
                                    else:
                                        # 没有result属性
                                        scrape_status.warning("MCP返回格式不正确")
                                        return "MCP返回结果格式不正确，缺少result属性"
                    except asyncio.TimeoutError:
                        scrape_status.warning(f"MCP抓取超时 (尝试 {current_retry+1}/{max_retries})")
                        current_retry += 1
                        continue
                    except Exception as mcp_error:
                        error_msg = str(mcp_error)
                        scrape_status.warning(f"MCP抓取出错: {error_msg[:100]}... (尝试 {current_retry+1}/{max_retries})")
                        
                        # 检查是否为TaskGroup错误，如果是则尝试其他工具
                        if "TaskGroup" in error_msg or "asyncio" in error_msg:
                            current_retry += 1
                            continue
                        else:
                            raise mcp_error
                
                except Exception as e:
                    error_msg = str(e)
                    current_retry += 1
                    
                    # 如果是最后一次尝试且失败，显示错误
                    if current_retry >= max_retries:
                        scrape_status.error(f"抓取失败: {error_msg[:200]}")
                        
                        # 返回一个简单的错误消息和URL作为备用
                        return f"无法通过MCP抓取 {url} 的内容。网页可能不存在或无法访问。\n建议访问网站手动查看内容。"
            
            # 如果所有重试都失败，返回一个友好的错误信息
            scrape_status.error("所有抓取方法都失败")
            return f"无法抓取 {url} 的内容。请尝试直接访问网站。"
    
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
            # 显示搜索标题
            st.write(f"## 搜索大学和专业信息")
            st.write(f"查询: {query}")
            
            # 直接创建进度条和状态文本
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
            
            # 创建错误日志区域
            error_container = st.container()
            with error_container:
                error_log = st.empty()
            
            # 开始搜索流程
            try:
                # 开始连接到服务器
                search_progress.progress(15)
                search_status.info("建立MCP连接...")
                
                # 最大重试次数
                max_retries = 2
                current_retry = 0
                
                # 选择搜索工具和参数
                primary_tool = self.search_tool_name
                
                # 重试循环
                while current_retry <= max_retries:
                    current_tool = primary_tool
                    search_status.info(f"尝试 {current_retry+1}/{max_retries+1}: 使用 {current_tool} 工具搜索")
                    
                    try:
                        # 使用异步超时防止卡住
                        async with asyncio.timeout(35):  # 35秒超时
                            # 使用streamable_http_client连接到服务器
                            async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                search_progress.progress(40)
                                search_status.info("创建MCP会话...")
                                
                                # 创建MCP会话
                                async with mcp.ClientSession(read_stream, write_stream) as session:
                                    # 初始化会话
                                    search_progress.progress(50)
                                    search_status.info("初始化会话...")
                                    await session.initialize()
                                    
                                    # 执行搜索
                                    search_progress.progress(70)
                                    search_status.info(f"执行搜索: {query}")
                                    
                                    # 准备搜索参数
                                    args = None
                                    
                                    # 根据工具名选择参数
                                    if current_tool == "google_search" or current_tool == "serper-google-search":
                                        args = {
                                            "query": query,
                                            "gl": "us",
                                            "hl": "en",
                                            "numResults": 5
                                        }
                                    elif current_tool == "search" or current_tool == "serper-search" or current_tool == "serper":
                                        args = {"query": query}
                                    elif current_tool == "scrape":
                                        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                                        args = {"url": search_url}
                                    else:
                                        # 通用搜索参数
                                        args = {"query": query}
                                    
                                    # 显示调用信息
                                    search_status.info(f"调用 {current_tool} 工具，参数: {args}")
                                    
                                    # 尝试调用工具
                                    try:
                                        result = await session.call_tool(current_tool, arguments=args)
                                    except Exception as tool_error:
                                        error_msg = str(tool_error)
                                        # 错误诊断和处理
                                        with error_container:
                                            st.write(f"⚠️ 工具调用错误: {error_msg[:200]}")
                                        
                                        # 处理常见参数错误
                                        if "query" in error_msg.lower() and "required" in error_msg.lower():
                                            search_status.warning(f"参数错误，尝试添加额外参数")
                                            # 添加额外参数再试
                                            args = {"query": query, "gl": "us", "hl": "en"}
                                            search_status.info(f"重试 {current_tool} 工具，参数: {args}")
                                            result = await session.call_tool(current_tool, arguments=args)
                                        else:
                                            # 如果有其他错误，重试另一个工具
                                            raise tool_error
                                    
                                    # 处理结果
                                    search_progress.progress(90)
                                    search_status.info("处理搜索结果...")
                                    
                                    # 成功获取结果
                                    if hasattr(result, 'result'):
                                        search_progress.progress(95)
                                        
                                        # 根据结果类型处理
                                        if isinstance(result.result, dict):
                                            # 标准搜索结果处理
                                            if "organic" in result.result:
                                                search_status.success(f"搜索成功，找到 {len(result.result['organic'])} 条结果")
                                                
                                                # 尝试抓取前两个结果的页面内容
                                                if len(result.result['organic']) > 0:
                                                    # 创建单独的容器用于显示抓取进度
                                                    with st.expander("网页内容抓取", expanded=False):
                                                        st.info("正在抓取搜索结果的网页内容...")
                                                        
                                                        try:
                                                            # 最多抓取前两个结果
                                                            pages_to_scrape = min(2, len(result.result['organic']))
                                                            for i in range(pages_to_scrape):
                                                                url = result.result['organic'][i].get('link', '')
                                                                if url and url.startswith('http'):
                                                                    st.write(f"抓取结果 {i+1}: {url}")
                                                                    
                                                                    # 为抓取操作创建进度指示器
                                                                    scrape_progress = st.progress(0)
                                                                    
                                                                    # 抓取页面内容
                                                                    try:
                                                                        scrape_progress.progress(30)
                                                                        content = await self.scrape_url(url, main_container)
                                                                        scrape_progress.progress(100)
                                                                        
                                                                        # 预览内容片段
                                                                        st.success(f"成功抓取页面 ({len(content)} 字符)")
                                                                        preview = content[:500] + "..." if len(content) > 500 else content
                                                                        st.caption("内容预览:")
                                                                        st.code(preview)
                                                                        
                                                                        # 将内容添加到搜索结果中
                                                                        result.result['organic'][i]['page_content'] = content
                                                                    except Exception as scrape_error:
                                                                        st.error(f"抓取错误: {str(scrape_error)[:200]}")
                                                                        scrape_progress.progress(100)
                                                            
                                                            search_status.success(f"完成页面内容抓取")
                                                        except Exception as e:
                                                            st.warning(f"抓取页面内容时出错: {str(e)[:200]}")
                                                
                                                # 搜索成功完成
                                                search_progress.progress(100)
                                                return result.result
                                            
                                            # 其他字典类型结果
                                            else:
                                                search_progress.progress(100)
                                                search_status.success("搜索完成，返回结果")
                                                return {
                                                    "organic": [
                                                        {
                                                            "title": "搜索结果",
                                                            "link": "",
                                                            "snippet": f"搜索得到的JSON结果: {json.dumps(result.result, ensure_ascii=False)[:1000]}"
                                                        }
                                                    ]
                                                }
                                                
                                        # 字符串类型结果
                                        elif isinstance(result.result, str):
                                            search_progress.progress(100)
                                            search_status.success("搜索完成")
                                            return {
                                                "organic": [
                                                    {
                                                        "title": f"搜索结果: {query}",
                                                        "link": f"https://www.google.com/search?q={query.replace(' ', '+')}",
                                                        "snippet": result.result[:1000] + "..." if len(result.result) > 1000 else result.result,
                                                        "page_content": result.result
                                                    }
                                                ]
                                            }
                                            
                                        # 列表类型结果
                                        elif isinstance(result.result, list):
                                            organic_results = []
                                            for i, item in enumerate(result.result):
                                                if isinstance(item, dict):
                                                    organic_results.append({
                                                        "title": item.get("title", f"结果 {i+1}"),
                                                        "link": item.get("link", item.get("url", "")),
                                                        "snippet": item.get("snippet", item.get("description", item.get("content", "无摘要")))
                                                    })
                                                else:
                                                    organic_results.append({
                                                        "title": f"结果 {i+1}",
                                                        "link": "",
                                                        "snippet": str(item)
                                                    })
                                            
                                            search_progress.progress(100)
                                            if organic_results:
                                                search_status.success(f"搜索成功，找到 {len(organic_results)} 条结果")
                                                return {"organic": organic_results}
                                            else:
                                                search_status.warning("搜索结果为空列表")
                                                return {"organic": [{"title": "空结果", "link": "", "snippet": "搜索未返回有效内容"}]}
                                        
                                        # 其他类型结果
                                        else:
                                            search_progress.progress(100)
                                            search_status.success("搜索完成，返回非标准格式结果")
                                            return {
                                                "organic": [
                                                    {
                                                        "title": f"搜索结果: {query}",
                                                        "link": "",
                                                        "snippet": f"类型: {type(result.result).__name__}, 内容: {str(result.result)[:1000]}"
                                                    }
                                                ]
                                            }
                                    
                                    # 结果格式不符合预期
                                    else:
                                        search_progress.progress(100)
                                        search_status.error("搜索结果格式不正确")
                                        with error_container:
                                            st.write(f"⚠️ 结果格式异常: {str(result)[:200]}")
                                        return {"error": "搜索结果格式不正确，缺少result属性", 
                                                "organic": [{"title": "无效结果格式", "link": "", "snippet": "服务器返回的结果格式无效"}]}
                    
                    except asyncio.TimeoutError:
                        search_progress.progress(100)
                        search_status.warning(f"搜索操作超时 (尝试 {current_retry+1}/{max_retries+1})")
                        current_retry += 1
                        
                        # 如果还有重试机会，尝试其他工具
                        if current_retry <= max_retries:
                            # 尝试备用搜索工具
                            if primary_tool == "google_search" and "serper" in self.available_tools:
                                primary_tool = "serper"
                            elif primary_tool != "google_search" and "google_search" in self.available_tools:
                                primary_tool = "google_search"
                            else:
                                # 尝试任何其他工具
                                other_tools = [t for t in self.available_tools if t != primary_tool]
                                if other_tools:
                                    primary_tool = other_tools[0]
                        else:
                            # 最后一次尝试失败，返回错误
                            return {
                                "error": "搜索操作多次尝试后仍然超时",
                                "organic": [{"title": f"搜索超时: {query}", "link": "", "snippet": "无法获取搜索结果，服务器响应时间过长"}]
                            }
                    
                    except Exception as e:
                        error_msg = str(e)
                        error_type = type(e).__name__
                        
                        # 记录错误日志
                        with error_container:
                            st.write(f"⚠️ 错误: {error_type} - {error_msg[:200]}")
                        
                        # 尝试切换搜索工具
                        current_retry += 1
                        search_status.warning(f"搜索错误: {error_type} (尝试 {current_retry}/{max_retries+1})")
                        
                        # 如果还有重试机会，尝试其他工具
                        if current_retry <= max_retries:
                            # 尝试备用搜索工具
                            if "TaskGroup" in error_msg:
                                search_status.info("检测到TaskGroup错误，尝试其他搜索工具")
                            
                            if primary_tool == "google_search" and "serper" in self.available_tools:
                                primary_tool = "serper"
                            elif primary_tool != "google_search" and "google_search" in self.available_tools:
                                primary_tool = "google_search"
                            else:
                                # 尝试任何其他工具
                                other_tools = [t for t in self.available_tools if t != primary_tool]
                                if other_tools:
                                    primary_tool = other_tools[0]
                        else:
                            # 最后一次尝试也失败，使用Serper API作为备用方法
                            search_status.info("所有MCP尝试都失败，使用备用搜索方法")
                            return await self._fallback_search(query, search_progress, search_status)
                
                # 如果所有重试都失败（不太可能到达这里，但以防万一）
                search_progress.progress(100)
                search_status.error("所有搜索尝试均失败")
                return {"error": "无法完成搜索请求", 
                        "organic": [{"title": "搜索失败", "link": "", "snippet": "多次尝试后仍然无法获取搜索结果"}]}
            
            except Exception as e:
                # 所有其他未捕获的异常
                search_progress.progress(100)
                search_status.error(f"搜索过程中发生意外错误: {type(e).__name__}")
                
                # 记录错误详情
                with error_container:
                    st.error(f"意外错误: {str(e)[:500]}")
                
                # 使用备用搜索方法
                return await self._fallback_search(query, search_progress, search_status)
    
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
                    if len(data['organic']) > 0:
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
                    if len(formatted_results['organic']) > 0:
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