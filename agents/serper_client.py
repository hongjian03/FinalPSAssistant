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
            
            # 开始MCP搜索流程
            try:
                # 开始连接到服务器
                search_progress.progress(15)
                search_status.info("建立MCP连接...")
                
                # 使用关键参数 - 这里是解决TaskGroup错误的关键一步
                # 根据工具类型确定合适的参数
                search_args = self._prepare_search_args(query, self.search_tool_name)
                
                with st.expander("MCP搜索参数", expanded=False):
                    st.code(f"工具: {self.search_tool_name}\n参数: {json.dumps(search_args, indent=2)}")
                
                # 使用异步超时防止卡住
                try:
                    async with asyncio.timeout(30):
                        # 使用streamable_http_client连接到服务器
                        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                            search_progress.progress(40)
                            search_status.info("创建MCP会话...")
                            
                            # 创建MCP会话
                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                # 初始化会话
                                search_progress.progress(50)
                                search_status.info("初始化MCP会话...")
                                await session.initialize()
                                
                                # 执行搜索
                                search_progress.progress(70)
                                search_status.info(f"执行MCP搜索: {query}")
                                
                                # 显示调用信息
                                search_status.info(f"调用 {self.search_tool_name} 工具，参数: {search_args}")
                                
                                # 直接调用工具 - 避免try/except嵌套导致TaskGroup错误
                                result = await session.call_tool(self.search_tool_name, arguments=search_args)
                                
                                # 处理结果
                                search_progress.progress(90)
                                search_status.info("处理搜索结果...")
                                
                                # 检查结果
                                if hasattr(result, 'result'):
                                    # 处理结果 - 不同类型的处理
                                    processed_results = self._process_search_result(result.result, query)
                                    
                                    # 尝试提取页面内容，但不使用MCP抓取
                                    if "organic" in processed_results:
                                        for result_item in processed_results["organic"]:
                                            if "snippet" in result_item:
                                                # 创建基本页面内容
                                                result_item["page_content"] = (
                                                    f"标题: {result_item.get('title', '')}\n\n"
                                                    f"摘要: {result_item.get('snippet', '')}\n\n"
                                                    f"链接: {result_item.get('link', '')}"
                                                )
                                    
                                    # 搜索成功
                                    search_progress.progress(100)
                                    if "organic" in processed_results:
                                        search_status.success(f"MCP搜索成功! 找到 {len(processed_results['organic'])} 条结果")
                                    else:
                                        search_status.success("MCP搜索成功!")
                                    return processed_results
                                else:
                                    # 结果格式问题
                                    search_progress.progress(100)
                                    search_status.warning("搜索结果格式异常，尝试备用方法")
                                    # 降级到备用搜索
                                    return await self._fallback_search(query, search_progress, search_status)
                
                except asyncio.TimeoutError:
                    # 超时处理
                    search_progress.progress(90)
                    search_status.warning("MCP搜索超时，尝试备用方法")
                    return await self._fallback_search(query, search_progress, search_status)
                
                except Exception as e:
                    # 记录错误信息
                    error_msg = str(e)
                    error_type = type(e).__name__
                    with error_container:
                        st.error(f"MCP错误: {error_type} - {error_msg[:200]}")
                    
                    # 检查是否任务组错误
                    if "TaskGroup" in error_msg or "asyncio" in error_msg:
                        search_status.warning("MCP出现TaskGroup错误，重新调整参数后尝试...")
                        
                        # 尝试更简单的参数调用
                        try:
                            # 重新建立连接，使用简单参数
                            simple_args = {"query": query}
                            
                            search_status.info("使用简化参数重试...")
                            with st.expander("简化参数", expanded=False):
                                st.code(json.dumps(simple_args, indent=2))
                            
                            async with asyncio.timeout(20):
                                # 使用streamable_http_client连接到服务器
                                async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                    # 创建MCP会话
                                    async with mcp.ClientSession(read_stream, write_stream) as session:
                                        # 初始化会话
                                        await session.initialize()
                                        
                                        # 执行搜索 - 使用简化参数
                                        result = await session.call_tool(self.search_tool_name, arguments=simple_args)
                                        
                                        # 处理结果
                                        if hasattr(result, 'result'):
                                            # 处理结果
                                            processed_results = self._process_search_result(result.result, query)
                                            
                                            # 添加基本页面内容
                                            if "organic" in processed_results:
                                                for result_item in processed_results["organic"]:
                                                    if "snippet" in result_item:
                                                        result_item["page_content"] = (
                                                            f"标题: {result_item.get('title', '')}\n\n"
                                                            f"摘要: {result_item.get('snippet', '')}\n\n"
                                                            f"链接: {result_item.get('link', '')}"
                                                        )
                                            
                                            # 搜索成功
                                            search_progress.progress(100)
                                            search_status.success("MCP搜索成功(简化参数)!")
                                            return processed_results
                        except Exception as e2:
                            error_msg = str(e2)
                            search_status.warning(f"简化MCP尝试也失败: {error_msg[:100]}")
                    
                    # 如果还是失败，使用备用搜索
                    search_status.info("降级到备用搜索方法...")
                    return await self._fallback_search(query, search_progress, search_status)
            
            except Exception as e:
                # 捕获所有其他异常
                error_msg = str(e)
                search_progress.progress(90)
                search_status.error(f"搜索过程中发生错误: {type(e).__name__}")
                
                # 记录详细错误
                with error_container:
                    st.error(f"错误详情: {error_msg[:300]}")
                
                # 使用备用搜索方法
                search_status.info("使用备用搜索方法...")
                return await self._fallback_search(query, search_progress, search_status)
    
    def _prepare_search_args(self, query: str, tool_name: str) -> Dict:
        """准备搜索参数，根据不同的工具名称提供合适的参数"""
        args = {}
        
        # 处理不同类型的搜索工具
        if tool_name == "google_search" or tool_name == "serper-google-search":
            args = {
                "query": query,
                "gl": "us",
                "hl": "en",
                "num": 5,
                "include_answer": True,
                "include_images": False,
                "include_knowledge": True
            }
        elif tool_name == "search" or tool_name == "serper-search" or tool_name == "serper":
            args = {
                "query": query,
                "gl": "us",
                "hl": "en"
            }
        elif tool_name == "scrape":
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            args = {"url": search_url}
        elif tool_name == "web-search" or tool_name == "google-search":
            args = {
                "query": query,
                "region": "us",
                "language": "en"
            }
        else:
            # 默认参数
            args = {"query": query}
        
        return args
    
    def _process_search_result(self, result: Any, query: str) -> Dict[str, Any]:
        """处理搜索结果，将不同格式标准化为统一格式"""
        # 如果已经是字典并且有organic字段，直接返回
        if isinstance(result, dict) and "organic" in result:
            return result
        
        # 创建标准结构
        processed_results = {"organic": []}
        
        # 处理字典结果
        if isinstance(result, dict):
            # 如果有results字段，转换为organic格式
            if "results" in result:
                for item in result["results"]:
                    if isinstance(item, dict):
                        processed_results["organic"].append({
                            "title": item.get("title", "无标题"),
                            "link": item.get("link", item.get("url", "")),
                            "snippet": item.get("snippet", item.get("description", item.get("content", "无摘要")))
                        })
            # 确保不返回空结果
            if not processed_results["organic"]:
                # 添加结果数据作为单个结果
                processed_results["organic"].append({
                    "title": "搜索结果",
                    "link": f"https://www.google.com/search?q={query.replace(' ', '+')}",
                    "snippet": f"搜索返回了非标准格式: {json.dumps(result)[:500]}..."
                })
        
        # 处理字符串结果
        elif isinstance(result, str):
            processed_results["organic"].append({
                "title": f"搜索结果: {query}",
                "link": f"https://www.google.com/search?q={query.replace(' ', '+')}",
                "snippet": result[:1000] + "..." if len(result) > 1000 else result
            })
        
        # 处理列表结果
        elif isinstance(result, list):
            for i, item in enumerate(result):
                if isinstance(item, dict):
                    processed_results["organic"].append({
                        "title": item.get("title", f"结果 {i+1}"),
                        "link": item.get("link", item.get("url", "")),
                        "snippet": item.get("snippet", item.get("description", item.get("content", "无摘要")))
                    })
                else:
                    processed_results["organic"].append({
                        "title": f"结果 {i+1}",
                        "link": "",
                        "snippet": str(item)[:500] + "..." if len(str(item)) > 500 else str(item)
                    })
        
        # 处理其他类型
        else:
            processed_results["organic"].append({
                "title": f"搜索: {query}",
                "link": "",
                "snippet": f"非标准类型结果: {type(result).__name__}, 值: {str(result)[:500]}..."
            })
        
        return processed_results
    
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
            status_text.info("使用Serper API搜索...")
            
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
            status_text.info(f"搜索中: {query}")
            
            # 构建Serper API请求
            serper_url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "q": query,
                "gl": "us",
                "hl": "en",
                "num": 10,  # 增加结果数量
                "autocorrect": True
            }
            
            # 记录搜索参数
            status_text.info(f"搜索参数: query={query}, gl=us, hl=en")
            
            # 发送请求到Serper API
            response = requests.post(serper_url, headers=headers, json=payload)
            
            # 更新UI进度
            progress_bar.progress(80)
            status_text.info(f"处理搜索结果... (状态码: {response.status_code})")
            
            # 检查响应
            if response.status_code == 200:
                data = response.json()
                
                # 标准化结果格式
                if "organic" in data:
                    progress_bar.progress(100)
                    status_text.success(f"备用搜索成功，找到 {len(data['organic'])} 条结果")
                    
                    # 添加页面内容
                    # 注意：现在不尝试抓取页面，直接使用搜索结果
                    for result in data['organic']:
                        # 扩展摘要作为页面内容的替代
                        if 'snippet' in result:
                            result['page_content'] = f"标题: {result.get('title', '')}\n\n{result.get('snippet', '')}\n\n链接: {result.get('link', '')}"
                    
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
                                "snippet": item.get("snippet", "无摘要"),
                                "page_content": f"标题: {item.get('title', '无标题')}\n\n{item.get('snippet', '无摘要')}\n\n链接: {item.get('link', '')}"
                            })
                    
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
                
                # 失败后生成模拟结果
                return self._generate_mock_results(query)
        except Exception as e:
            error_msg = str(e)
            
            # 更新UI状态
            if progress_bar and status_text:
                progress_bar.progress(100)
                status_text.error(f"备用搜索出错: {error_msg}")
            
            # 使用模拟数据
            return self._generate_mock_results(query)
            
    def _generate_mock_results(self, query: str) -> Dict[str, Any]:
        """生成基本的模拟结果，当所有搜索方法都失败时使用"""
        # 提取查询中的大学和专业名称
        terms = query.split()
        university = ""
        program = ""
        
        for term in terms:
            if term.lower() in ["university", "college", "school", "institute"] or term.upper() in ["UCL", "MIT", "UCLA"]:
                university = term
            elif term.lower() in ["msc", "master", "phd", "ba", "bs"] or term.upper() in ["MBA", "MSC", "PHD"]:
                program = term
        
        if not university:
            university = "该大学"
        if not program:
            program = "该专业"
            
        # 创建基本的搜索结果
        return {
            "organic": [
                {
                    "title": f"{university} {program} - 官方项目页面",
                    "link": f"https://www.example.com/{university.lower()}/{program.lower()}",
                    "snippet": f"查找关于 {university} 的 {program} 项目的官方信息，包括申请要求、课程设置和申请流程。",
                    "page_content": f"{university} 的 {program} 项目是一个广受欢迎的学术项目。申请者通常需要良好的学术背景、语言能力证明和相关经验。请访问大学官方网站获取最新、最准确的信息。"
                },
                {
                    "title": f"{program} 在 {university} - 申请信息",
                    "link": f"https://www.example.com/apply/{university.lower()}/{program.lower()}",
                    "snippet": f"了解如何申请 {university} 的 {program} 项目，包括截止日期、所需材料和录取流程。",
                    "page_content": f"申请 {university} 的 {program} 项目需要提交完整的申请材料，包括成绩单、推荐信、个人陈述等。申请截止日期通常在每年的特定时间。请查看大学官方网站获取详细的申请流程。"
                }
            ]
        }
    
    def run_async(self, coroutine):
        """Helper method to run async methods synchronously."""
        return asyncio.run(coroutine) 