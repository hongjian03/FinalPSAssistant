import os
import json
import base64
import asyncio
import re  # 添加re模块的导入
from typing import Dict, Any, List, Optional
import streamlit as st
import traceback
import mcp
from mcp.client.streamable_http import streamablehttp_client
import requests
import time
import aiohttp

# 导入Jina Reader配置
try:
    from config.jina_config import get_jina_config
    JINA_CONFIG = get_jina_config()
except ImportError:
    # 默认配置
    JINA_CONFIG = {
        "base_url": "https://r.jina.ai/",
        "request": {
            "timeout": 25,
            "max_retries": 2,
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/markdown,text/plain,*/*;q=0.9",
                "Cache-Control": "no-cache"
            }
        },
        "features": {
            "use_as_primary": True,
            "fallback_to_direct": True
        }
    }

class SerperClient:
    """
    A client for interacting with the Serper API.
    
    This client connects to an MCP server to use Serper's tools for web search and content extraction.
    """
    
    def __init__(self):
        """
        Initialize the SerperClient.
        """
        # Serper MCP server URL
        self.url = "wss://mcp.serper.dev"
        
        # Alternatively, can use the Deepinfra MCP server
        # self.url = "wss://mcp.deepinfra.com"
        
        # Available tools on the server
        self.available_tools = []
        
        # Search and scrape tools to be selected
        self.search_tool_name = None
        self.scrape_tool_name = None
        
        # Jina Reader API URL for web scraping
        self.jina_reader_url = "https://r.jina.ai/"
        
        # Track MCP connection failures for fallback strategies
        self.mcp_scraping_failures = 0
        
        # 一律使用Jina Reader作为抓取方法
        self.use_jina_as_primary = True
        
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
        # The correct scrape tool name (will be determined in initialize)
        self.scrape_tool_name = None
        # Maximum retries for connection issues
        self.max_retries = 3
        
        # 添加缓存
        self.search_cache = {}  # 搜索结果缓存
        self.scrape_cache = {}  # 网页内容抓取缓存
        self.cache_enabled = True  # 是否启用缓存
    
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
            
            # 创建临时全局错误日志
            error_log_container = st.container()
            with error_log_container:
                error_log = st.empty()
            
            # 可能的搜索工具名称
            search_tool_candidates = [
                "google_search",
                "serper-google-search",
                "search", 
                "serper-search", 
                "web-search",
                "google-search",
                "serper"
            ]
            
            # 可能的抓取工具名称
            scrape_tool_candidates = [
                "scrape",
                "web-scrape",
                "scrape-url",
                "url-scrape",
                "webpage-scrape",
                "extract"
            ]
            
            # 显示基本连接信息
            status_text.info("开始初始化Serper MCP服务")
            
            # 第一步：准备连接
            progress_bar.progress(10)
            status_text.info("正在检查连接参数...")
            await asyncio.sleep(0.3)
            
            # 尝试多次连接以减少TaskGroup错误的影响
            max_attempts = 5  # 增加最大尝试次数
            current_attempt = 0
            last_error = None
            
            while current_attempt < max_attempts:
                current_attempt += 1
                progress_bar.progress(20 + current_attempt * 5)
                status_text.info(f"尝试连接 MCP 服务 (尝试 {current_attempt}/{max_attempts})...")
                
                try:
                    # 使用超时
                    async with asyncio.timeout(30):
                        # 建立HTTP连接
                        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                            progress_bar.progress(40)
                            status_text.info("HTTP连接已建立，初始化MCP会话...")
                            
                            # 创建会话
                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                # 初始化
                                await session.initialize()
                                progress_bar.progress(60)
                                status_text.info("MCP会话已初始化，获取工具列表...")
                                
                                # 获取工具列表
                                try:
                                    # 较短的超时用于工具列表获取
                                    async with asyncio.timeout(15):  # 增加超时时间
                                        tools_result = await session.list_tools()
                                        
                                        # 成功获取工具列表
                                        if hasattr(tools_result, 'tools'):
                                            # 保存所有可用工具
                                            self.available_tools = [t.name for t in tools_result.tools]
                                            progress_bar.progress(80)
                                            status_text.info("已获取工具列表，正在查找搜索和抓取工具...")
                                            
                                            # 显示工具信息
                                            with st.expander("可用工具", expanded=False):
                                                for tool in tools_result.tools:
                                                    st.caption(f"工具: {tool.name}")
                                                    if hasattr(tool, 'description'):
                                                        st.caption(f"描述: {tool.description}")
                                            
                                            # 查找搜索工具
                                            search_tool_name = None
                                            for tool_name in search_tool_candidates:
                                                if tool_name in self.available_tools:
                                                    search_tool_name = tool_name
                                                    break
                                            
                                            # 查找抓取工具
                                            scrape_tool_name = None
                                            for tool_name in scrape_tool_candidates:
                                                if tool_name in self.available_tools:
                                                    scrape_tool_name = tool_name
                                                    break
                                            
                                            # 如果没找到，尝试模糊匹配
                                            if not search_tool_name:
                                                for tool_name in self.available_tools:
                                                    if "search" in tool_name.lower() or "google" in tool_name.lower():
                                                        search_tool_name = tool_name
                                                        break
                                            
                                            if not scrape_tool_name:
                                                for tool_name in self.available_tools:
                                                    if "scrape" in tool_name.lower() or "extract" in tool_name.lower():
                                                        scrape_tool_name = tool_name
                                                        break
                                            
                                            # 保存找到的工具名称
                                            self.search_tool_name = search_tool_name
                                            self.scrape_tool_name = scrape_tool_name
                                            
                                            # 检查是否找到工具
                                            if self.search_tool_name and self.scrape_tool_name:
                                                progress_bar.progress(100)
                                                status_text.success(f"MCP连接成功! 已选择搜索工具: {self.search_tool_name}, 抓取工具: {self.scrape_tool_name}")
                                                return True
                                            elif self.search_tool_name:
                                                progress_bar.progress(100)
                                                status_text.success(f"MCP连接成功! 已选择搜索工具: {self.search_tool_name}")
                                                # 如果没有专门的抓取工具，将搜索工具也设为抓取工具
                                                self.scrape_tool_name = self.search_tool_name
                                                return True
                                            elif len(self.available_tools) > 0:
                                                # 没找到搜索工具，使用第一个可用的
                                                self.search_tool_name = self.available_tools[0]
                                                self.scrape_tool_name = self.available_tools[0]
                                                progress_bar.progress(100)
                                                status_text.warning(f"未找到专用工具，将使用 {self.search_tool_name} 作为替代")
                                                return True
                                            else:
                                                raise Exception("未找到任何可用工具")
                                        else:
                                            # tools_result没有tools属性
                                            raise Exception("工具列表格式不正确")
                                except Exception as tool_error:
                                    # 记录错误并尝试下一次
                                    last_error = tool_error
                                    if "TaskGroup" in str(tool_error) and current_attempt < max_attempts:
                                        status_text.warning(f"获取工具列表时出现TaskGroup错误，将重试... ({current_attempt}/{max_attempts})")
                                        await asyncio.sleep(1)
                                        continue
                                    else:
                                        raise tool_error  # 重新抛出以便被外层捕获
                except Exception as e:
                    # 记录所有错误
                    last_error = e
                    error_msg = str(e)
                    
                    # 针对TaskGroup错误特殊处理
                    if "TaskGroup" in error_msg and current_attempt < max_attempts:
                        # TaskGroup错误，尝试重试
                        status_text.warning(f"发生TaskGroup错误，重试中... ({current_attempt}/{max_attempts})")
                        await asyncio.sleep(1 + current_attempt * 0.5)  # 逐渐增加等待时间
                        continue
                    elif "timeout" in error_msg.lower() and current_attempt < max_attempts:
                        # 超时错误，尝试重试
                        status_text.warning(f"连接超时，重试中... ({current_attempt}/{max_attempts})")
                        await asyncio.sleep(1 + current_attempt * 0.5)
                        continue
                    elif "connection" in error_msg.lower() and current_attempt < max_attempts:
                        # 连接错误，尝试重试
                        status_text.warning(f"连接错误，重试中... ({current_attempt}/{max_attempts})")
                        await asyncio.sleep(1 + current_attempt * 0.5)
                        continue
                    else:
                        # 记录详细错误信息
                        with st.expander("错误详情", expanded=False):
                            st.code(f"错误类型: {type(e).__name__}\n错误消息: {error_msg}\n\n{traceback.format_exc()}")
                        
                        if current_attempt >= max_attempts:
                            break
                        else:
                            status_text.warning(f"连接出错: {type(e).__name__}, 重试中... ({current_attempt}/{max_attempts})")
                            await asyncio.sleep(0.5)
                            continue
            
            # 所有尝试都失败，使用默认设置
            progress_bar.progress(90)
            
            # 记录最后的错误
            if last_error:
                error_log.warning(f"最后一次错误: {str(last_error)[:200]}")
                
            # 设置默认搜索工具
            self.search_tool_name = search_tool_candidates[0]
            self.scrape_tool_name = scrape_tool_candidates[0]
            self.available_tools = [self.search_tool_name, self.scrape_tool_name]
            
            progress_bar.progress(100)
            status_text.warning(f"无法完美连接MCP服务，使用默认搜索工具: {self.search_tool_name}, 抓取工具: {self.scrape_tool_name}")
            
            return True
    
    async def scrape_url(self, url: str, main_container=None) -> str:
        """
        抓取指定URL的内容，直接使用Jina Reader API
        
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
            scrape_progress = st.progress(0)
            scrape_status.info(f"正在抓取网页内容: {url}")
            
            # 使用配置中的设置决定使用哪种抓取方法
            if JINA_CONFIG["features"]["use_as_primary"]:
                scrape_status.info("直接使用Jina Reader抓取内容...")
                return await self.jina_reader_scrape(url, main_container)
            
            # 如果配置为不使用Jina作为主要方法，则按老逻辑执行（下面的代码基本不会执行）
            # 检查是否有抓取工具可用
            if not hasattr(self, 'scrape_tool_name') or not self.scrape_tool_name:
                scrape_status.warning("未找到有效的抓取工具，将使用直接抓取方法")
                return await self.direct_scrape(url, main_container)
            
            # 最大重试次数
            max_retries = 3
            current_retry = 0
            
            # 保存最后一个错误消息用于诊断
            last_error = None
            
            while current_retry < max_retries:
                scrape_progress.progress(10 + current_retry * 10)
                scrape_status.info(f"尝试使用MCP抓取URL内容 (尝试 {current_retry+1}/{max_retries})")
                
                try:
                    # 设置连接超时
                    async with asyncio.timeout(30):
                        # 使用streamable_http_client连接到服务器
                        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                            scrape_progress.progress(30 + current_retry * 10)
                            scrape_status.info("创建MCP会话...")
                            
                            # 创建MCP会话
                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                # 初始化会话
                                await session.initialize()
                                scrape_progress.progress(50 + current_retry * 10)
                                
                                # 准备抓取参数
                                args = {"url": url}
                                scrape_status.info(f"正在使用 {self.scrape_tool_name} 抓取URL: {url}")
                                
                                # 调用抓取工具
                                try:
                                    # 设置工具调用超时
                                    async with asyncio.timeout(25):
                                        result = await session.call_tool(self.scrape_tool_name, arguments=args)
                                        
                                        # 处理结果
                                        if hasattr(result, 'result'):
                                            # 成功获取结果
                                            scrape_status.success("成功抓取网页内容")
                                            scrape_progress.progress(100)
                                            
                                            if isinstance(result.result, str):
                                                # 直接返回字符串结果
                                                return result.result
                                            elif isinstance(result.result, dict):
                                                # 提取字典结果中的内容
                                                if "content" in result.result:
                                                    return result.result["content"]
                                                elif "text" in result.result:
                                                    return result.result["text"]
                                                else:
                                                    # 将整个字典格式化为文本
                                                    formatted_result = []
                                                    
                                                    # 添加标题
                                                    if "title" in result.result:
                                                        formatted_result.append(f"# {result.result['title']}")
                                                    
                                                    # 添加内容或摘要
                                                    for key in ["body", "snippet", "html", "description"]:
                                                        if key in result.result and result.result[key]:
                                                            formatted_result.append(str(result.result[key]))
                                                    
                                                    # 添加URL
                                                    formatted_result.append(f"\n来源: {url}")
                                                    
                                                    # 返回格式化文本
                                                    return "\n\n".join(formatted_result)
                                            else:
                                                # 其他类型结果转为字符串
                                                return str(result.result)
                                        else:
                                            # 抓取结果没有预期的result属性
                                            if hasattr(result, 'error') and result.error:
                                                # 有明确的错误信息
                                                last_error = f"抓取错误: {result.error}"
                                                scrape_status.warning(f"抓取工具返回错误: {result.error}")
                                            else:
                                                # 没有明确错误信息
                                                last_error = "抓取结果格式不正确"
                                                scrape_status.warning("抓取结果格式不正确")
                                            
                                            # 增加重试计数
                                            current_retry += 1
                                            # 增加MCP失败计数
                                            self.mcp_scraping_failures += 1
                                            
                                            if current_retry < max_retries:
                                                await asyncio.sleep(1)
                                                continue
                                            else:
                                                # 所有重试都失败，检查是否可以使用Jina Reader
                                                if self.use_jina_as_primary and self.mcp_scraping_failures >= 2:
                                                    scrape_status.warning("MCP抓取多次失败，尝试使用Jina Reader抓取")
                                                    return await self.jina_reader_scrape(url, main_container)
                                                else:
                                                    # 否则回退到直接抓取
                                                    scrape_status.warning("MCP抓取多次失败，切换到直接抓取")
                                                    return await self.direct_scrape(url, main_container)
                                except asyncio.TimeoutError:
                                    # 工具调用超时
                                    last_error = "工具调用超时"
                                    scrape_status.warning(f"抓取工具调用超时 (尝试 {current_retry+1}/{max_retries})")
                                    current_retry += 1
                                    self.mcp_scraping_failures += 1
                                    
                                    if current_retry < max_retries:
                                        await asyncio.sleep(1)
                                        continue
                                    else:
                                        # 所有重试都失败，检查是否可以使用Jina Reader
                                        if self.use_jina_as_primary and self.mcp_scraping_failures >= 2:
                                            scrape_status.warning("MCP抓取多次超时，尝试使用Jina Reader抓取")
                                            return await self.jina_reader_scrape(url, main_container)
                                        else:
                                            # 否则回退到直接抓取
                                            scrape_status.warning("MCP抓取多次超时，切换到直接抓取")
                                            return await self.direct_scrape(url, main_container)
                                except Exception as tool_error:
                                    # 工具调用异常
                                    error_msg = str(tool_error)
                                    last_error = error_msg
                                    
                                    # 特殊处理TaskGroup错误
                                    if "TaskGroup" in error_msg or "asyncio" in error_msg:
                                        scrape_status.warning(f"抓取工具出现TaskGroup错误 (尝试 {current_retry+1}/{max_retries})")
                                    else:
                                        scrape_status.warning(f"抓取工具错误: {error_msg[:100]}")
                                    
                                    # 增加重试计数
                                    current_retry += 1
                                    self.mcp_scraping_failures += 1
                                    
                                    if current_retry < max_retries:
                                        await asyncio.sleep(1)
                                        continue
                                    else:
                                        # 所有重试都失败，检查是否可以使用Jina Reader
                                        if self.use_jina_as_primary and self.mcp_scraping_failures >= 2:
                                            scrape_status.warning("MCP抓取多次出错，尝试使用Jina Reader抓取")
                                            return await self.jina_reader_scrape(url, main_container)
                                        else:
                                            # 否则回退到直接抓取
                                            scrape_status.warning("MCP抓取多次出错，切换到直接抓取")
                                            return await self.direct_scrape(url, main_container)
                except (asyncio.TimeoutError, Exception) as e:
                    # 连接或会话异常
                    error_msg = str(e)
                    last_error = error_msg
                    
                    # 更新状态
                    if "TaskGroup" in error_msg or "asyncio" in error_msg:
                        scrape_status.warning(f"MCP连接出现TaskGroup错误 (尝试 {current_retry+1}/{max_retries})")
                    elif "timeout" in error_msg.lower():
                        scrape_status.warning(f"MCP连接超时 (尝试 {current_retry+1}/{max_retries})")
                    else:
                        scrape_status.warning(f"MCP连接错误: {error_msg[:100]} (尝试 {current_retry+1}/{max_retries})")
                    
                    # 增加重试计数
                    current_retry += 1
                    self.mcp_scraping_failures += 1
                    
                    if current_retry < max_retries:
                        await asyncio.sleep(1)
                        continue
                    else:
                        # 所有重试都失败，检查是否可以使用Jina Reader
                        if self.use_jina_as_primary and self.mcp_scraping_failures >= 2:
                            scrape_status.warning("MCP连接多次失败，尝试使用Jina Reader抓取")
                            return await self.jina_reader_scrape(url, main_container)
                        else:
                            # 否则回退到直接抓取
                            scrape_status.warning("MCP连接多次失败，切换到直接抓取")
                            return await self.direct_scrape(url, main_container)
            
            # 如果执行到这里，表示所有重试都已用完但没有返回结果
            # 首先尝试Jina Reader，然后再使用直接抓取作为最后手段
            if self.use_jina_as_primary and self.mcp_scraping_failures >= 2:
                scrape_status.warning("所有MCP抓取尝试均失败，尝试使用Jina Reader抓取")
                return await self.jina_reader_scrape(url, main_container)
            else:
                # 使用直接抓取作为最后手段
                scrape_status.warning("所有MCP抓取尝试均失败，切换到直接抓取")
                return await self.direct_scrape(url, main_container)
    
    async def search_web(self, query: str, main_container=None) -> Dict[str, Any]:
        """
        Perform a web search using the Serper MCP server.
        
        Args:
            query: The search query
            main_container: Container to display progress in
            
        Returns:
            Dictionary containing search results
        """
        # 检查缓存
        cache_key = query.lower().strip()  # 标准化缓存键
        if self.cache_enabled and cache_key in self.search_cache:
            # 如果提供了容器，显示缓存命中信息
            if main_container:
                with main_container:
                    st.success(f"使用缓存结果: {query}")
            return self.search_cache[cache_key]
            
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
            
        # 检查是否有MCP搜索工具
        if not self.search_tool_name:
            with main_container:
                search_status.warning("未找到MCP搜索工具，将使用备用搜索方法")
            return await self._fallback_search(query, search_progress, search_status)
        
        # 优化参数以减少错误
        optimized_args = {
            "query": query,
            "q": query,          
            "gl": "us",                 
            "hl": "en",
            "region_code": "us",
            "language": "en",
            "num_results": 5,    # 减少结果数量       
            "numResults": 5
        }
        
        # 尝试次数和当前尝试
        max_retries = 2 
        current_retry = 0
        last_error = None
        
        # 尝试使用MCP进行搜索
        while current_retry < max_retries:
            with main_container:
                search_progress.progress(20 + current_retry * 15)
                search_status.info(f"初始化搜索工具... (尝试 {current_retry+1}/{max_retries})")
            
            try:
                # 设置较短的超时时间
                async with asyncio.timeout(15):  # 减少超时时间
                    # 使用streamable_http_client连接到服务器
                    async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                        with main_container:
                            search_progress.progress(40 + current_retry * 10)
                            search_status.info("创建MCP会话...")
                        
                        # 创建MCP会话
                        async with mcp.ClientSession(read_stream, write_stream) as session:
                            # 初始化会话
                            await session.initialize()
                            
                            with main_container:
                                search_progress.progress(60 + current_retry * 5)
                                search_status.info(f"执行搜索: {query}")
                            
                            # 直接使用优化的参数调用工具
                            # 使用较短的超时
                            async with asyncio.timeout(12):
                                result = await session.call_tool(self.search_tool_name, arguments=optimized_args)
                                
                                with main_container:
                                    search_progress.progress(80)
                                    search_status.info("处理搜索结果...")
                                
                                # 处理搜索结果
                                if hasattr(result, 'result'):
                                    # 返回前将结果存入缓存
                                    formatted_results = self._standardize_mcp_results(result.result, query)
                                    
                                    with main_container:
                                        search_progress.progress(100)
                                        result_count = len(formatted_results.get('organic', []))
                                        search_status.success(f"搜索成功，找到 {result_count} 条结果")
                                    
                                    # 存入缓存并返回
                                    if self.cache_enabled:
                                        self.search_cache[cache_key] = formatted_results
                                    
                                    return formatted_results
                                else:
                                    raise Exception("无效的搜索结果格式")
                                    
            except Exception as e:
                # 记录错误
                last_error = e
                error_msg = str(e)
                
                # 对于搜索参数错误，使用备用格式
                if "query" in error_msg.lower() and "required" in error_msg.lower():
                    with main_container:
                        search_status.info(f"搜索参数调整中 (这是正常流程，请稍候...)")
                    
                    if current_retry < max_retries - 1:
                        # 使用极简参数
                        optimized_args = {
                            "q": query,
                            "gl": "us",
                            "hl": "en"
                        }
                        current_retry += 1
                        await asyncio.sleep(0.5)
                        continue
                else:
                    with main_container:
                        search_status.warning(f"搜索出错: {error_msg[:100]}")
                    
                    if current_retry < max_retries - 1:
                        current_retry += 1
                        await asyncio.sleep(0.5)
                        continue
            
            # 如果所有尝试都失败，使用备用方法
            break
        
        # 使用备用搜索方法
        with main_container:
            search_status.warning("MCP搜索失败，使用备用方法")
        
        results = await self._fallback_search(query, search_progress, search_status)
        
        # 存入缓存并返回
        if self.cache_enabled:
            self.search_cache[cache_key] = results
        
        return results
    
    async def _enrich_university_results(self, search_results: Dict[str, Any], progress_bar=None, status_text=None, main_container=None) -> Dict[str, Any]:
        """
        增强搜索结果：针对大学网站的结果，直接抓取网页内容
        
        Args:
            search_results: 原始搜索结果
            progress_bar: 进度条
            status_text: 状态文本
            main_container: 显示容器
            
        Returns:
            增强后的搜索结果
        """
        if not search_results or "organic" not in search_results or not search_results["organic"]:
            return search_results
        
        # 创建新的UI容器
        if main_container is None:
            main_container = st.container()
        
        with main_container:
            if status_text is None:
                status_text = st.empty()
            status_text.info("分析搜索结果，查找官方大学网站...")
            
            # 创建一个新的进度条来显示增强过程
            enrich_progress = st.progress(0)
            enrich_progress.progress(10)
        
        # 检查结果中是否有大学网站 - 增加更多关键词
        uni_keywords = [
            'university', 'college', 'school', 'institute', 'ucl', 'oxford', 'cambridge', 'edu', 
            'academic', 'admission', 'program', 'programme', 'degree', 'master', 'msc', 'ma', 'phd',
            'faculty', 'department', 'course', 'apply', 'application', 'enrollment'
        ]
        
        # 更多大学域名模式 - 优先考虑官方域名
        official_uni_domains = [
            '.edu/', '.ac.uk/', '.edu.au/', '.edu.cn/', '.ac.jp/', '.edu.sg/', '.edu.hk/',
            'university.edu', '.uni-', '-uni.', '.college.edu', '.sch.'
        ]
        
        # 非官方网站的关键词和域名 - 用于过滤
        unofficial_keywords = [
            'review', 'ranking', 'compare', 'forum', 'discussion', 'blog', 'student',
            'scholarship', 'rankings', 'list', 'top', 'best', 'rating'
        ]
        
        unofficial_domains = [
            'studyportals', 'timeshighereducation', 'topuniversities', 'mastersportal',
            'thestudentroom', 'reddit.com', 'quora.com', 'collegeconfidential',
            'findamasters', 'hotcoursesabroad', 'prospects.ac.uk', 'collegeprowler',
            'niche.com', 'petersons.com', 'gradschools.com', 'usnews.com'
        ]
        
        # 复制结果列表，避免直接修改原列表导致迭代问题
        results_to_process = list(search_results.get('organic', []))
        
        # 计数器和处理过的URL跟踪
        processed_count = 0
        processed_urls = set()
        max_to_process = 5  # 限制处理的大学网站数量，避免过多请求
        
        # 首先找到和处理最可能的官方大学相关URL
        university_results = []
        
        with main_container:
            status_text.info("识别官方大学网站...")
        
        # 第一步：先给所有结果评分，排序官方和非官方网站
        scored_results = []
        
        for i, result in enumerate(results_to_process):
            if "link" in result and result["link"]:
                url = result["link"]
                score = 0
                is_official = False
                is_unofficial = False
                
                # 检查是否是官方大学网站 - 给高分
                for domain in official_uni_domains:
                    if domain in url.lower():
                        score += 100
                        is_official = True
                        break
                
                # 检查是否是非官方网站 - 扣分
                for domain in unofficial_domains:
                    if domain in url.lower():
                        score -= 50
                        is_unofficial = True
                        break
                
                # 标题和摘要中的关键词检查
                title_text = result.get("title", "").lower()
                snippet_text = result.get("snippet", "").lower()
                
                # 检查官方关键词
                for keyword in uni_keywords:
                    if keyword in url.lower():
                        score += 10
                    if keyword in title_text:
                        score += 5
                    if keyword in snippet_text:
                        score += 3
                
                # 检查非官方关键词 - 扣分
                for keyword in unofficial_keywords:
                    if keyword in url.lower():
                        score -= 5
                    if 'ranking' in title_text or 'best' in title_text or 'top' in title_text:
                        score -= 10
                
                # 特殊加分：.edu域名强相关的更可能是官方
                if '.edu/' in url.lower() and not is_unofficial:
                    score += 50
                
                # 网址越短越可能是官方主页
                url_parts = url.split('/')
                if len(url_parts) <= 4: # 如 https://www.stanford.edu/
                    score += 20
                
                # 添加到评分列表
                scored_results.append((i, result, url, score, is_official, is_unofficial))
        
        # 按分数排序，高分在前
        scored_results.sort(key=lambda x: x[3], reverse=True)
        
        # 优先处理官方网站，然后是高分非官方网站
        official_count = 0
        
        with main_container:
            # 显示排序结果和诊断信息
            with st.expander("搜索结果评分", expanded=False):
                for i, result, url, score, is_official, is_unofficial in scored_results[:8]:
                    if is_official:
                        st.write(f"✓ 官方站点 ({score}分): {url}")
                    elif is_unofficial:
                        st.write(f"✗ 非官方站点 ({score}分): {url}")
                    else:
                        st.write(f"? 未确定 ({score}分): {url}")
        
        # 提取要处理的大学网站 - 优先官方，有限数量
        university_results = []
        
        # 先添加官方网站
        for i, result, url, score, is_official, is_unofficial in scored_results:
            if is_official and official_count < 3:  # 最多处理3个官方网站
                university_results.append((i, result, url))
                official_count += 1
        
        # 然后添加未确认但高分的站点，直到达到最大处理数
        if len(university_results) < max_to_process:
            for i, result, url, score, is_official, is_unofficial in scored_results:
                if not is_official and not is_unofficial and score > 30 and len(university_results) < max_to_process:
                    university_results.append((i, result, url))
        
        # 检查是否找到了合适的网站
        with main_container:
            if university_results:
                status_text.info(f"找到 {len(university_results)} 个大学相关网站，开始获取详细内容...")
            else:
                status_text.warning("未找到适合的大学网站，跳过内容增强步骤")
                enrich_progress.progress(100)
                return search_results
        
        # 创建任务列表，准备并行处理
        tasks = []
        for i, result, url in university_results:
            # 标记URL为已处理
            processed_urls.add(url)
            tasks.append((i, result, url))
        
        # 逐个处理任务
        for idx, (i, result, url) in enumerate(tasks):
            # 更新进度
            task_progress = 20 + (idx * 80 // len(tasks))
            with main_container:
                enrich_progress.progress(task_progress)
                status_text.info(f"抓取大学网站 ({idx+1}/{len(tasks)}): {url}")
            
            try:
                # 使用Jina Reader抓取网页内容
                page_content = await self.jina_reader_scrape(url, main_container)
                
                # 检查结果是否有效
                if page_content and len(page_content) > 200 and not page_content.startswith(("# 无法抓取内容", "# 抓取错误")):
                    # 存储原始page_content，以防内容转换失败可以恢复
                    original_content = search_results['organic'][i].get('page_content', '')
                    
                    # 添加到搜索结果
                    search_results['organic'][i]['page_content'] = page_content
                    search_results['organic'][i]['is_official'] = url in [r[2] for r in university_results if r[0] == i]
                    
                    # 对抓取的官方大学网站增加权重 - 移到前面
                    if i > 0:
                        # 创建副本并移到前面
                        university_entry = search_results['organic'][i].copy()
                        # 在开头插入这个结果的副本
                        search_results['organic'].insert(0, university_entry)
                    
                    processed_count += 1
                    with main_container:
                        status_text.success(f"成功抓取内容: {url}")
                else:
                    with main_container:
                        status_text.warning(f"无法有效抓取: {url}")
                        
                # 每次抓取后稍等片刻，避免连续请求导致TaskGroup错误
                await asyncio.sleep(0.5)
                
            except Exception as e:
                with main_container:
                    status_text.error(f"抓取过程中出错: {str(e)[:100]}...")
                    with st.expander("错误详情", expanded=False):
                        st.code(traceback.format_exc())
                        
                # 出错后等待略长时间，以便系统恢复
                await asyncio.sleep(1)
        
        # 重新排序搜索结果 - 官方网站优先
        # 创建新的排序结果列表
        official_results = []
        other_results = []
        
        for result in search_results['organic']:
            if result.get('is_official', False):
                official_results.append(result)
            else:
                other_results.append(result)
        
        # 重建结果列表，官方在前
        search_results['organic'] = official_results + other_results
        
        # 完成增强
        with main_container:
            enrich_progress.progress(100)
            if processed_count > 0:
                status_text.success(f"增强完成，成功抓取 {processed_count} 个大学网站内容")
            else:
                status_text.warning("未能成功抓取任何大学网站内容")
        
        return search_results
    
    def _standardize_mcp_results(self, data: Dict[str, Any], query: str) -> Dict[str, Any]:
        """
        标准化MCP搜索结果格式
        
        Args:
            data: 原始搜索结果数据
            query: 原始搜索查询
            
        Returns:
            标准化的搜索结果字典
        """
        # 如果已经是标准格式，做一些基本处理
        if "organic" in data:
            # 处理有机搜索结果
            for i, result in enumerate(data['organic']):
                # 创建页面内容，如果不存在
                if 'page_content' not in result and 'snippet' in result:
                    title = result.get('title', '未知标题')
                    snippet = result.get('snippet', '')
                    link = result.get('link', '')
                    
                    data['organic'][i]['page_content'] = (
                        f"标题: {title}\n\n"
                        f"{snippet}\n\n"
                        f"链接: {link}"
                    )
            
            # 添加知识图谱内容（如果有）
            if "knowledgeGraph" in data and len(data['organic']) > 0:
                kg = data["knowledgeGraph"]
                kg_title = kg.get("title", "")
                kg_type = kg.get("type", "")
                kg_description = kg.get("description", "")
                
                kg_content = f"## {kg_title}"
                if kg_type:
                    kg_content += f" ({kg_type})"
                kg_content += f"\n\n{kg_description}\n\n"
                
                # 添加属性
                if "attributes" in kg:
                    kg_content += "### 属性\n\n"
                    for key, value in kg["attributes"].items():
                        kg_content += f"- {key}: {value}\n"
                
                # 添加到第一个结果的页面内容
                existing_content = data['organic'][0].get('page_content', '')
                data['organic'][0]['page_content'] = kg_content + "\n\n" + existing_content
            
            return data
        
        # 转换为标准格式
        return self._convert_to_standard_format(data, query)
    
    def _convert_to_standard_format(self, data: Any, query: str) -> Dict[str, Any]:
        """
        将各种格式的搜索结果转换为标准格式
        
        Args:
            data: 任何格式的搜索结果数据
            query: 原始搜索查询
            
        Returns:
            标准化的搜索结果字典
        """
        formatted_results = {"organic": []}
        
        # 处理字典格式
        if isinstance(data, dict):
            # 如果有知识图谱，添加为第一个结果
            if "knowledgeGraph" in data:
                kg = data["knowledgeGraph"]
                kg_title = kg.get("title", "知识图谱结果")
                kg_description = kg.get("description", "")
                kg_url = kg.get("url", kg.get("siteLinks", {}).get("official", {}).get("link", ""))
                
                # 创建页面内容
                kg_content = f"## {kg_title}\n\n{kg_description}\n\n"
                
                # 添加属性
                if "attributes" in kg:
                    kg_content += "### 属性\n\n"
                    for key, value in kg["attributes"].items():
                        kg_content += f"- {key}: {value}\n"
                
                formatted_results["organic"].append({
                    "title": kg_title,
                    "link": kg_url or "",
                    "snippet": kg_description,
                    "page_content": kg_content
                })
            
            # 处理不同结果格式
            if "results" in data:
                for item in data["results"]:
                    formatted_results["organic"].append({
                        "title": item.get("title", "无标题"),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "无摘要"),
                        "page_content": f"标题: {item.get('title', '无标题')}\n\n{item.get('snippet', '无摘要')}\n\n链接: {item.get('link', '')}"
                    })
            elif "items" in data:
                for item in data["items"]:
                    formatted_results["organic"].append({
                        "title": item.get("title", "无标题"),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "无摘要"),
                        "page_content": f"标题: {item.get('title', '无标题')}\n\n{item.get('snippet', '无摘要')}\n\n链接: {item.get('link', '')}"
                    })
        # 处理列表格式
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    title = item.get("title", "无标题")
                    link = item.get("link", "")
                    snippet = item.get("snippet", item.get("description", "无内容"))
                    
                    formatted_results["organic"].append({
                        "title": title,
                        "link": link,
                        "snippet": snippet,
                        "page_content": f"标题: {title}\n\n{snippet}\n\n链接: {link}"
                    })
                else:
                    # 对于非字典项，创建简单条目
                    formatted_results["organic"].append({
                        "title": f"搜索结果 {query}",
                        "link": "",
                        "snippet": str(item),
                        "page_content": str(item)
                    })
        # 处理字符串格式
        elif isinstance(data, str):
            formatted_results["organic"].append({
                "title": f"搜索结果 {query}",
                "link": "",
                "snippet": data[:200] + "..." if len(data) > 200 else data,
                "page_content": data
            })
        # 其他格式
        else:
            formatted_results["organic"].append({
                "title": f"搜索结果 {query}",
                "link": "",
                "snippet": str(data)[:200] + "..." if len(str(data)) > 200 else str(data),
                "page_content": str(data)
            })
        
        # 如果没有结果，使用模拟结果
        if len(formatted_results["organic"]) == 0:
            return self._generate_mock_results(query)
        
        return formatted_results
    
    async def _fallback_search(self, query: str, progress_bar=None, status_text=None) -> Dict[str, Any]:
        """
        直接使用Serper API进行搜索，避开TaskGroup错误
        
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
                    st.write("## 使用Serper搜索引擎")
                    progress_bar = st.progress(0)
                    status_text = st.empty()
            
            # 更新UI状态
            progress_bar.progress(30)
            status_text.info("搜索中...")
            
            # 确保有API密钥
            if not self.serper_api_key:
                progress_bar.progress(100)
                status_text.error("缺少Serper API密钥")
                
                return {
                    "error": "缺少Serper API密钥，无法执行搜索",
                    "organic": [
                        {
                            "title": f"无法搜索: {query}",
                            "link": "",
                            "snippet": "系统缺少Serper API密钥，无法执行搜索。请检查配置。"
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
            
            # 确保包含所有必需参数：query、gl（地区代码）和hl（语言）
            payload = {
                "q": query,          # 查询词
                "gl": "us",          # 地区代码：美国
                "hl": "en",          # 语言：英语
                "num": 10,           # 结果数量
                "autocorrect": True  # 自动纠正拼写
            }
            
            # 记录搜索参数
            status_text.info(f"搜索参数: query='{query}', gl='us', hl='en'")
            
            # 最大重试次数
            max_retries = 2
            current_retry = 0
            response = None
            last_error = None
            
            # 添加重试逻辑处理临时性网络问题
            while current_retry <= max_retries:
                try:
                    # 发送请求到Serper API
                    response = requests.post(serper_url, headers=headers, json=payload, timeout=20)
                    break  # 成功获取响应，退出循环
                except requests.RequestException as e:
                    last_error = e
                    current_retry += 1
                    if current_retry <= max_retries:
                        status_text.warning(f"API请求失败，正在重试 ({current_retry}/{max_retries})...")
                        time.sleep(1)
                    else:
                        # 所有重试都失败
                        progress_bar.progress(100)
                        status_text.error(f"无法连接到Serper API: {str(e)}")
                        return self._generate_mock_results(query)
            
            # 更新UI进度
            progress_bar.progress(80)
            status_text.info(f"处理搜索结果... (状态码: {response.status_code})")
            
            # 检查响应
            if response.status_code == 200:
                data = response.json()
                
                # 标准化结果格式
                if "organic" in data:
                    # 处理有机搜索结果
                    for i, result in enumerate(data['organic']):
                        # 创建页面内容
                        if 'snippet' in result:
                            title = result.get('title', '未知标题')
                            snippet = result.get('snippet', '')
                            link = result.get('link', '')
                            
                            data['organic'][i]['page_content'] = (
                                f"标题: {title}\n\n"
                                f"{snippet}\n\n"
                                f"链接: {link}"
                            )
                    
                    # 添加知识图谱内容（如果有）
                    if "knowledgeGraph" in data:
                        kg = data["knowledgeGraph"]
                        kg_title = kg.get("title", "")
                        kg_type = kg.get("type", "")
                        kg_description = kg.get("description", "")
                        
                        kg_content = f"## {kg_title}"
                        if kg_type:
                            kg_content += f" ({kg_type})"
                        kg_content += f"\n\n{kg_description}\n\n"
                        
                        # 添加属性
                        if "attributes" in kg:
                            kg_content += "### 属性\n\n"
                            for key, value in kg["attributes"].items():
                                kg_content += f"- {key}: {value}\n"
                        
                        # 添加到第一个结果的页面内容
                        if len(data['organic']) > 0:
                            existing_content = data['organic'][0].get('page_content', '')
                            data['organic'][0]['page_content'] = kg_content + "\n\n" + existing_content
                    
                    progress_bar.progress(100)
                    status_text.success(f"搜索成功，找到 {len(data['organic'])} 条结果")
                    return data
                else:
                    # 创建标准格式的结果
                    formatted_results = {"organic": []}
                    
                    # 如果有知识图谱，添加为第一个结果
                    if "knowledgeGraph" in data:
                        kg = data["knowledgeGraph"]
                        kg_title = kg.get("title", "知识图谱结果")
                        kg_description = kg.get("description", "")
                        kg_url = kg.get("url", "")
                        
                        # 创建页面内容
                        kg_content = f"## {kg_title}\n\n{kg_description}\n\n"
                        
                        # 添加属性
                        if "attributes" in kg:
                            kg_content += "### 属性\n\n"
                            for key, value in kg["attributes"].items():
                                kg_content += f"- {key}: {value}\n"
                        
                        formatted_results["organic"].append({
                            "title": kg_title,
                            "link": kg_url,
                            "snippet": kg_description,
                            "page_content": kg_content
                        })
                    
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
                    status_text.success(f"搜索成功，找到 {len(formatted_results['organic'])} 条结果")
                    return formatted_results
            elif response.status_code == 400 and "parameter is missing" in response.text.lower():
                # 特殊处理参数错误
                progress_bar.progress(90)
                status_text.warning("API参数错误，尝试修复...")
                
                # 尝试不同的参数格式
                payload = {
                    "query": query,
                    "gl": "us",
                    "hl": "en"
                }
                
                try:
                    # 再次尝试请求
                    response = requests.post(serper_url, headers=headers, json=payload, timeout=20)
                    
                    if response.status_code == 200:
                        # 处理成功响应
                        data = response.json()
                        
                        # 标准化并返回结果
                        formatted_results = self._convert_to_standard_format(data, query)
                        
                        progress_bar.progress(100)
                        status_text.success("修复参数后搜索成功")
                        return formatted_results
                except Exception as retry_error:
                    # 记录重试错误
                    status_text.error(f"修复参数后请求仍失败: {str(retry_error)}")
                
                # 失败后回退到模拟结果
                progress_bar.progress(100)
                status_text.warning("无法修复参数问题，使用模拟结果")
                
                return self._generate_mock_results(query)
            else:
                # 处理API错误
                progress_bar.progress(100)
                
                try:
                    error_json = response.json()
                    error_message = error_json.get("message", str(response.status_code))
                    status_text.error(f"搜索失败: {error_message}")
                    
                    # 显示详细错误信息
                    with st.expander("API错误详情", expanded=False):
                        st.code(json.dumps(error_json, indent=2))
                        
                except:
                    # 如果无法解析JSON，直接显示文本
                    status_text.error(f"搜索失败: {response.status_code} - {response.text}")
                
                # 生成模拟结果
                search_results = self._generate_mock_results(query)
                
                # 显示错误信息
                status_text.info("由于API错误，将使用模拟结果")
                
                return search_results
                
        except Exception as e:
            error_msg = str(e)
            
            # 更新UI状态
            if progress_bar and status_text:
                progress_bar.progress(100)
                status_text.error(f"搜索过程中出错: {error_msg}")
                
                # 显示详细错误
                with st.expander("错误详情", expanded=False):
                    st.code(traceback.format_exc())
            
            # 生成模拟结果
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

    async def direct_scrape(self, url: str, main_container=None) -> str:
        """
        直接抓取URL内容，不使用MCP，用作后备方案
        
        Args:
            url: 要抓取的URL
            main_container: 用于显示进度的容器
            
        Returns:
            抓取的内容
        """
        if main_container is None:
            main_container = st.container()
        
        with main_container:
            scrape_status = st.empty()
            scrape_progress = st.progress(0)
            scrape_status.info(f"直接抓取网页内容: {url}")
            
            try:
                # 更新进度
                scrape_progress.progress(30)
                scrape_status.info("发送HTTP请求...")
                
                # 添加用户代理头，模拟现代浏览器
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Cache-Control": "max-age=0"
                }
                
                # 使用较短的超时发送请求
                max_retries = 3  # 增加重试次数
                current_retry = 0
                response = None
                last_error = None
                
                while current_retry <= max_retries:
                    try:
                        scrape_status.info(f"尝试发送请求 (尝试 {current_retry+1}/{max_retries+1})...")
                        response = requests.get(url, headers=headers, timeout=20, verify=True)
                        break  # 如果成功，跳出循环
                    except Exception as e:
                        last_error = e
                        current_retry += 1
                        if current_retry <= max_retries:
                            scrape_status.warning(f"请求失败，重试中: {str(e)[:100]}...")
                            await asyncio.sleep(1)
                        else:
                            # 所有重试都失败
                            scrape_status.error(f"所有请求尝试均失败: {str(e)}")
                
                # 如果所有尝试都失败
                if not response:
                    scrape_progress.progress(100)
                    scrape_status.error("无法连接到网站")
                    return f"# 无法抓取内容\n\n连接到 {url} 失败: {str(last_error)}\n\n请尝试直接访问网站查看内容。"
                
                scrape_progress.progress(60)
                
                # 检查响应
                if response.status_code == 200:
                    scrape_status.info(f"成功获取内容 (状态码: {response.status_code})")
                    
                    # 检查内容类型
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' in content_type:
                        # 处理可能的编码问题
                        try:
                            # 首先尝试使用响应的编码
                            html_content = response.text
                        except UnicodeDecodeError:
                            # 如果失败，尝试检测编码
                            try:
                                import chardet
                                detected_encoding = chardet.detect(response.content)['encoding']
                                html_content = response.content.decode(detected_encoding or 'utf-8', errors='replace')
                            except:
                                # 最后的备选方案
                                html_content = response.content.decode('utf-8', errors='replace')
                        
                        # 提取标题
                        import re  # 导入re模块
                        title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
                        title = title_match.group(1) if title_match else url
                        
                        # 使用BeautifulSoup解析HTML
                        from bs4 import BeautifulSoup
                        try:
                            # 导入所有需要的模块
                            import re
                            
                            # 使用BeautifulSoup解析HTML
                            soup = BeautifulSoup(html_content, 'html.parser')
                            
                            # 移除脚本、样式、导航、广告和其他干扰元素
                            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript']):
                                element.extract()
                            
                            # 大学项目相关关键词
                            program_keywords = [
                                'program', 'programme', 'course', 'degree', 'master', 'msc', 'ma', 'phd', 
                                'curriculum', 'admission', 'requirements', 'apply', 'application', 'overview',
                                'syllabus', 'modules', 'faculty', 'department', 'research'
                            ]
                            
                            # 尝试找到主要内容区域
                            main_content = None
                            
                            # 1. 检查含有程序关键词的ID和类名
                            import re  # 确保导入re模块用于正则表达式
                            for keyword in program_keywords:
                                # 查找ID包含关键词的元素
                                for element in soup.find_all(id=re.compile(f'.*{keyword}.*', re.IGNORECASE)):
                                    if len(element.get_text(strip=True)) > 100:  # 确保有足够内容
                                        main_content = element
                                        break
                                
                                # 查找类名包含关键词的元素
                                if not main_content:
                                    for element in soup.find_all(class_=re.compile(f'.*{keyword}.*', re.IGNORECASE)):
                                        if len(element.get_text(strip=True)) > 100:
                                            main_content = element
                                            break
                                
                                if main_content:
                                    break
                            
                            # 2. 查找常见的内容容器
                            if not main_content:
                                content_candidates = [
                                    soup.find('main'),
                                    soup.find(id='main-content'),
                                    soup.find(id='content'),
                                    soup.find(id='main'),
                                    soup.find(class_='main-content'),
                                    soup.find(class_='content'),
                                    soup.find(role='main'),
                                    soup.find(class_='program-details'),
                                    soup.find(class_='course-details'),
                                    soup.find(class_='description'),
                                    soup.find(class_='program-description'),
                                    soup.find(id='program-details'),
                                    soup.find(id='course-details')
                                ]
                                
                                for candidate in content_candidates:
                                    if candidate and len(candidate.get_text(strip=True)) > 200:
                                        main_content = candidate
                                        break
                            
                            # 3. 查找特定的HTML5标记元素
                            if not main_content:
                                for tag in ['article', 'section', 'main']:
                                    elements = soup.find_all(tag)
                                    for element in elements:
                                        if len(element.get_text(strip=True)) > 300:
                                            main_content = element
                                            break
                                    if main_content:
                                        break
                            
                            # 4. 尝试查找包含关键词的段落和标题集合
                            program_sections = []
                            
                            # 找所有标题，尤其注重包含关键词的部分
                            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                                heading_text = heading.get_text(strip=True).lower()
                                
                                # 检查标题是否包含相关关键词
                                if any(keyword in heading_text for keyword in program_keywords):
                                    # 初始化这个部分的内容
                                    section_content = []
                                    section_content.append(f"# {heading.get_text(strip=True)}")
                                    
                                    # 获取这个标题之后的内容
                                    next_sibling = heading.find_next_sibling()
                                    while next_sibling:
                                        # 如果找到新标题，结束收集
                                        if next_sibling.name in ['h1', 'h2', 'h3', 'h4']:
                                            break
                                        
                                        # 提取有意义的文本，忽略空内容
                                        if next_sibling.name in ['p', 'ul', 'ol', 'table', 'div']:
                                            text = next_sibling.get_text(strip=True)
                                            if text and len(text) > 10:  # 非空且有意义
                                                # 列表项特殊处理
                                                if next_sibling.name in ['ul', 'ol']:
                                                    list_items = []
                                                    for li in next_sibling.find_all('li'):
                                                        li_text = li.get_text(strip=True)
                                                        if li_text:
                                                            list_items.append(f"- {li_text}")
                                                    if list_items:
                                                        section_content.append("\n".join(list_items))
                                                else:
                                                    section_content.append(text)
                                        
                                        next_sibling = next_sibling.find_next_sibling()
                                    
                                    # 如果收集到有意义的内容，添加到部分列表
                                    if len(section_content) > 1:
                                        program_sections.append("\n\n".join(section_content))
                            
                            # 如果找到了有内容的部分，把它们合并为主内容
                            if program_sections:
                                extracted_content = "\n\n".join(program_sections)
                                # 如果有内容但没有找到特定区域，使用所有提取的部分
                                if not main_content or len(main_content.get_text(strip=True)) < len(extracted_content):
                                    # 创建一个包含所有提取内容的临时元素
                                    main_content = BeautifulSoup(f"<div>{extracted_content}</div>", 'html.parser').div
                            
                            # 5. 如果仍然没有找到有用内容，尝试从body提取所有重要段落
                            if not main_content or len(main_content.get_text(strip=True)) < 300:
                                important_paragraphs = []
                                
                                # 获取所有段落
                                for p in soup.find_all(['p', 'div', 'section']):
                                    p_text = p.get_text(strip=True)
                                    # 检查是否包含关键词且长度合适
                                    if len(p_text) > 100 and any(keyword in p_text.lower() for keyword in program_keywords):
                                        important_paragraphs.append(p_text)
                                
                                # 如果找到足够的段落，合并它们
                                if len(important_paragraphs) > 2:
                                    extracted_content = "\n\n".join(important_paragraphs)
                                    main_content = BeautifulSoup(f"<div>{extracted_content}</div>", 'html.parser').div
                            
                            # 如果仍未找到特定的内容区域，使用整个body，但跳过导航和页脚
                            if not main_content:
                                main_content = soup.body
                            
                            # 提取并格式化内容
                            extracted_text = self._extract_formatted_content(main_content, program_keywords)
                            
                            # 如果内容太短，可能没有提取到足够的信息
                            if len(extracted_text) < 300:
                                # 尝试再次从整个body提取，但只保留重要部分
                                extracted_text = self._extract_formatted_content(soup.body, program_keywords)
                            
                            # 如果内容包含占位符，尝试查找更多信息
                            if "(待补充" in extracted_text or "placeholder" in extracted_text.lower():
                                # 搜索是否有详细信息
                                detail_sections = []
                                for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                                    heading_text = heading.get_text(strip=True).lower()
                                    if any(detail_word in heading_text for detail_word in ['detail', 'more', 'information', 'about']):
                                        detail_section = [f"# {heading.get_text(strip=True)}"]
                                        current = heading.next_sibling
                                        while current and current.name not in ['h1', 'h2', 'h3', 'h4']:
                                            if hasattr(current, 'get_text'):
                                                text = current.get_text(strip=True)
                                                if text and len(text) > 50:
                                                    detail_section.append(text)
                                            current = current.next_sibling
                                        if len(detail_section) > 1:
                                            detail_sections.append("\n\n".join(detail_section))
                                
                                # 添加找到的详细信息
                                if detail_sections:
                                    extracted_text += "\n\n## 附加信息\n\n" + "\n\n".join(detail_sections)
                            
                            # 完成处理
                            scrape_progress.progress(100)
                            scrape_status.success("成功抓取并处理内容")
                            
                            # 返回格式化的内容，并包含来源URL
                            final_content = f"# {title}\n\n{extracted_text}\n\n来源: {url}"
                            return final_content
                        
                        except Exception as parsing_error:
                            # BeautifulSoup处理错误
                            scrape_progress.progress(100)
                            scrape_status.error(f"解析HTML时出错: {str(parsing_error)}")
                            with st.expander("错误详情", expanded=False):
                                st.code(traceback.format_exc())
                            return f"# 抓取错误\n\n解析 {url} 的内容时出错: {str(parsing_error)}\n\n请尝试直接访问网站查看内容。"
                    
                    else:
                        # 非HTML内容
                        scrape_progress.progress(100)
                        scrape_status.warning(f"URL返回非HTML内容: {content_type}")
                        return f"# 非文本内容\n\nURL {url} 返回了非HTML内容 ({content_type})。请直接访问网站查看。"
                
                else:
                    # 非200状态码
                    scrape_progress.progress(100)
                    scrape_status.error(f"HTTP错误: {response.status_code}")
                    return f"# 抓取错误\n\n访问 {url} 时返回HTTP错误 {response.status_code}。请稍后再试或直接访问网站。"
            
            except Exception as e:
                # 其他所有错误
                scrape_progress.progress(100)
                scrape_status.error(f"抓取过程中发生异常: {str(e)}")
                with st.expander("错误详情", expanded=False):
                    st.code(traceback.format_exc())
                return f"# 抓取错误\n\n处理 {url} 时发生异常: {str(e)}\n\n请尝试直接访问网站查看内容。"
    
    def _extract_formatted_content(self, element, keywords):
        """
        从HTML元素中提取格式化内容
        
        Args:
            element: BeautifulSoup元素
            keywords: 关键词列表用于识别重要内容
            
        Returns:
            格式化的内容文本
        """
        if not element:
            return ""
        
        import re  # 确保在方法内部也导入re模块
        from bs4 import BeautifulSoup
        
        # 提取有用的文本
        text_parts = []
        
        # 特别处理标题，确保它们有正确的格式和层次
        for level, tag in enumerate(['h1', 'h2', 'h3', 'h4', 'h5'], 1):
            for heading in element.find_all(tag):
                heading_text = heading.get_text().strip()
                if heading_text:
                    # 添加标题格式 (最多到三级标题)
                    text_parts.append("\n" + "#" * min(level, 3) + " " + heading_text + "\n")
        
        # 处理列表 - 有序和无序
        for list_element in element.find_all(['ul', 'ol']):
            list_items = []
            for li in list_element.find_all('li'):
                li_text = li.get_text().strip()
                if li_text:
                    if list_element.name == 'ul':
                        list_items.append("- " + li_text)
                    else:
                        list_items.append("1. " + li_text)  # 简化为统一的编号
            
            if list_items:
                text_parts.append("\n" + "\n".join(list_items) + "\n")
        
        # 处理段落
        for p in element.find_all('p'):
            p_text = p.get_text().strip()
            if p_text:
                # 添加段落，确保段落之间有空行
                text_parts.append(p_text)
        
        # 处理div - 通常包含段落或其他内容
        for div in element.find_all('div'):
            # 跳过已经处理过的元素
            if div.find(['p', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5']):
                continue
                
            div_text = div.get_text().strip()
            # 只保留有意义的div内容
            if div_text and len(div_text) > 50:
                # 查找该div是否包含关键词，如果包含，给它更高优先级
                has_keywords = any(keyword in div_text.lower() for keyword in keywords)
                
                if has_keywords:
                    text_parts.insert(0, div_text)  # 放在前面
                else:
                    text_parts.append(div_text)
        
        # 处理表格
        for table in element.find_all('table'):
            # 添加表格标题
            text_parts.append("\n### 表格信息\n")
            
            # 提取表格行
            for row in table.find_all('tr'):
                cells = []
                for cell in row.find_all(['td', 'th']):
                    cell_text = cell.get_text().strip().replace('\n', ' ')
                    cells.append(cell_text)
                
                if cells:
                    text_parts.append("| " + " | ".join(cells) + " |")
            
            text_parts.append("\n")
        
        # 合并所有内容，并进行清理
        combined_text = "\n\n".join(text_parts)
        
        # 清理多余的空行和空格
        cleaned_text = re.sub(r'\n{3,}', '\n\n', combined_text)
        cleaned_text = re.sub(r' {2,}', ' ', cleaned_text)
        
        # 替换可能的占位符文本
        final_text = cleaned_text.replace('(待补充)', '').replace('(待确认)', '')
        
        return final_text.strip()

    async def jina_reader_scrape(self, url: str, main_container=None) -> str:
        """
        使用Jina Reader API抓取URL内容
        
        Args:
            url: 要抓取的URL
            main_container: 用于显示进度的容器
            
        Returns:
            抓取的内容
        """
        # 标准化URL作为缓存键
        cache_key = url.lower().strip()
        # 检查缓存
        if self.cache_enabled and cache_key in self.scrape_cache:
            # 如果提供了容器，显示缓存命中信息
            if main_container:
                with main_container:
                    st.success(f"使用缓存内容: {url}")
            return self.scrape_cache[cache_key]
            
        if main_container is None:
            main_container = st.container()
            
        with main_container:
            scrape_status = st.empty()
            scrape_progress = st.progress(0)
            scrape_status.info(f"使用Jina Reader抓取内容: {url}")
            
            try:
                # 更新进度
                scrape_progress.progress(30)
                
                # 从配置中获取Jina Reader设置
                jina_base_url = JINA_CONFIG["base_url"]
                request_timeout = 12  # 缩短超时时间，原为25秒
                max_retries = 1  # 减少重试次数，原为2次
                headers = JINA_CONFIG["request"]["headers"]
                
                # 构建Jina Reader URL
                jina_url = f"{jina_base_url}{url}"
                scrape_status.info(f"抓取网页中，请稍候...")
                
                # 使用较短的超时发送请求
                current_retry = 0
                last_error = None
                
                while current_retry <= max_retries:
                    try:
                        scrape_progress.progress(50 + current_retry * 10)
                        
                        # 使用aiohttp进行异步请求
                        async with aiohttp.ClientSession() as session:
                            async with session.get(jina_url, headers=headers, timeout=request_timeout) as response:
                                if response.status == 200:
                                    content = await response.text()
                                    scrape_status.success("成功抓取内容")
                                    scrape_progress.progress(100)
                                    
                                    # 限制内容长度，避免过长内容处理
                                    if len(content) > 30000:
                                        content = content[:30000] + "\n\n...(内容已截断)..."
                                        scrape_status.info("内容过长，已截断")
                                    
                                    # 返回抓取的内容
                                    if content:
                                        # 保存到缓存
                                        if self.cache_enabled:
                                            self.scrape_cache[cache_key] = content
                                        return content
                                    else:
                                        raise Exception("抓取结果为空")
                                else:
                                    status_code = response.status
                                    status_text = response.reason
                                    raise Exception(f"HTTP错误: {status_code} {status_text}")
                        
                    except Exception as e:
                        last_error = e
                        current_retry += 1
                        if current_retry <= max_retries:
                            scrape_status.warning(f"Jina Reader请求失败，重试中: {str(e)[:100]}...")
                            await asyncio.sleep(1)
                        else:
                            # 所有重试都失败
                            scrape_status.error(f"Jina Reader抓取失败: {str(e)}")
                            break
                
                # 如果所有Jina尝试都失败且配置允许回退，则使用直接抓取
                if JINA_CONFIG["features"]["fallback_to_direct"]:
                    scrape_status.warning("无法使用Jina Reader抓取，切换到直接抓取")
                    return await self.direct_scrape(url, main_container)
                else:
                    # 配置不允许回退，返回错误信息
                    scrape_progress.progress(100)
                    scrape_status.error("Jina Reader抓取失败，未启用回退")
                    return f"# 抓取失败\n\n无法使用Jina Reader抓取 {url} 的内容，且未启用回退到直接抓取。错误: {str(last_error)}"
                
            except Exception as e:
                # 处理所有其他异常
                scrape_status.error(f"Jina Reader处理错误: {str(e)}")
                scrape_progress.progress(100)
                
                # 如果配置允许回退，使用直接抓取
                if JINA_CONFIG["features"]["fallback_to_direct"]:
                    return await self.direct_scrape(url, main_container)
                else:
                    # 配置不允许回退，返回错误信息
                    return f"# 抓取错误\n\n处理 {url} 时发生异常: {str(e)}\n\n未启用回退到直接抓取。"

    async def _jina_reader_scrape(self, url: str) -> str:
        """
        使用Jina Reader API抓取URL内容
        
        Args:
            url: 要抓取的URL
        
        Returns:
            str: 抓取到的Markdown格式内容
        """
        jina_url = f"{JINA_CONFIG['base_url']}?url={url}"
        timeout = JINA_CONFIG['request']['timeout']
        max_retries = JINA_CONFIG['request']['max_retries']
        headers = JINA_CONFIG['request']['headers']
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(max_retries + 1):
                try:
                    async with session.get(jina_url, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            content = await response.text()
                            
                            # 如果启用了简化输出，处理内容以减少大小
                            if JINA_CONFIG['features'].get('simplified_output', False):
                                # 删除多余的空行
                                content = re.sub(r'\n{3,}', '\n\n', content)
                                # 简化图片描述
                                content = re.sub(r'!\[.*?\]', '![Image]', content)
                                # 限制内容长度
                                if len(content) > 25000:
                                    content = content[:25000] + "\n\n...(内容已截断)..."
                            
                            return content
                        else:
                            print(f"Jina Reader抓取失败，状态码: {response.status}")
                            if attempt < max_retries:
                                await asyncio.sleep(1)  # 失败后短暂等待
                            
                except asyncio.TimeoutError:
                    print(f"Jina Reader请求超时 (尝试 {attempt+1}/{max_retries+1})")
                    if attempt < max_retries:
                        await asyncio.sleep(1)
                except Exception as e:
                    print(f"Jina Reader抓取异常: {str(e)}")
                    if attempt < max_retries:
                        await asyncio.sleep(1)
                        
        return ""

    async def scrape_url(self, url: str) -> str:
        """
        抓取URL内容 - 使用Jina Reader作为主要抓取方法
        
        Args:
            url: 要抓取的URL
        
        Returns:
            str: 抓取到的内容
        """
        # 检查URL有效性
        if not url or not url.startswith(('http://', 'https://')):
            return "无效URL"
            
        print(f"开始使用Jina Reader抓取: {url}")
        
        # 使用Jina Reader API抓取
        content = await self._jina_reader_scrape(url)
        
        # 如果Jina Reader成功获取内容
        if content:
            print("Jina Reader抓取成功")
            return content
        
        # 如果配置允许回退到直接抓取
        if JINA_CONFIG['features'].get('fallback_to_direct', True):
            print("Jina Reader抓取失败，切换到直接抓取")
            # 使用直接抓取作为后备方案
            try:
                response = requests.get(url, headers=JINA_CONFIG['request']['headers'], 
                                        timeout=JINA_CONFIG['request']['timeout'])
                if response.status_code == 200:
                    from bs4 import BeautifulSoup
                    import chardet
                    
                    # 检测编码
                    encoding = chardet.detect(response.content)['encoding'] or 'utf-8'
                    
                    # 解析HTML
                    soup = BeautifulSoup(response.content.decode(encoding, errors='ignore'), 'html.parser')
                    
                    # 提取正文内容
                    for tag in soup(['script', 'style', 'head', 'header', 'footer', 'nav']):
                        tag.extract()
                    
                    # 提取主要内容
                    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.body
                    
                    if main_content:
                        # 转换为Markdown格式
                        text = main_content.get_text('\n', strip=True)
                        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
                        markdown = '\n\n'.join(paragraphs)
                        
                        # 提取标题
                        title = soup.title.string if soup.title else ""
                        if title:
                            markdown = f"# {title.strip()}\n\n{markdown}"
                            
                        return markdown
                    else:
                        return "抓取格式错误"
                else:
                    return "抓取错误: HTTP状态码 " + str(response.status_code)
            except Exception as e:
                return f"抓取异常: {str(e)}"
        
        return "抓取失败"

    async def search_and_scrape_multi(self, query: str, urls_to_scrape: List[str]) -> Dict[str, str]:
        """
        并行抓取多个URL的内容
        
        Args:
            query: 搜索查询
            urls_to_scrape: 要抓取的URL列表
            
        Returns:
            Dict[str, str]: URL和抓取内容的映射
        """
        results = {}
        
        # 如果启用并行处理
        if JINA_CONFIG['features'].get('parallel_processing', False):
            max_concurrent = JINA_CONFIG['features'].get('max_concurrent_requests', 3)
            # 创建协程任务列表
            tasks = []
            for url in urls_to_scrape:
                tasks.append(self._jina_reader_scrape(url))
                
            # 并行执行任务，但限制并发数
            for i in range(0, len(tasks), max_concurrent):
                batch = tasks[i:i+max_concurrent]
                batch_results = await asyncio.gather(*batch)
                
                # 添加结果到字典
                for j, content in enumerate(batch_results):
                    url_index = i + j
                    if url_index < len(urls_to_scrape):
                        url = urls_to_scrape[url_index]
                        if content:
                            results[url] = content
                        else:
                            # 如果Jina失败，尝试直接抓取
                            if JINA_CONFIG['features'].get('fallback_to_direct', True):
                                print(f"Jina Reader抓取{url}失败，切换到直接抓取")
                                results[url] = await self.scrape_url(url)
        else:
            # 顺序抓取
            for url in urls_to_scrape:
                content = await self.scrape_url(url)
                if content:
                    results[url] = content
                    
        return results

    async def search_and_scrape(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        搜索并抓取结果
        
        Args:
            query: 搜索查询
            num_results: 搜索结果数量
            
        Returns:
            Dict[str, Any]: 包含搜索结果和抓取内容的字典
        """
        # 首先进行搜索，使用新的search方法获取优化查询结果
        search_results = await self.search(query, num_results)
        if not search_results or not search_results.get("organic", []):
            return {"error": "搜索失败或没有结果"}
            
        organic_results = search_results.get("organic", [])
        
        # 过滤结果，移除明显的非官方或低质量网站
        filtered_results = []
        excluded_domains = [
            'quora.com', 'reddit.com', 'wikipedia.org', 'youtube.com', 
            'facebook.com', 'twitter.com', 'instagram.com',
            'studyportals.com', 'mastersportal.com', 'topuniversities.com'
        ]
        
        for result in organic_results:
            url = result.get("link", "")
            # 检查是否应该排除该网站
            should_exclude = any(domain in url.lower() for domain in excluded_domains)
            
            if not should_exclude:
                filtered_results.append(result)
            else:
                print(f"排除非官方网站: {url}")
        
        # 如果过滤后没有结果，则使用原始结果
        if not filtered_results:
            print("过滤后没有结果，使用原始结果")
            filtered_results = organic_results
        
        # 更新搜索结果
        search_results["organic"] = filtered_results
        organic_results = filtered_results
        
        # 提取要抓取的URL
        urls_to_scrape = []
        for result in organic_results:
            url = result.get("link")
            if url:
                urls_to_scrape.append(url)
                
        # 并行抓取URL内容
        print(f"正在抓取 {len(urls_to_scrape)} 个URL...")
        
        scraped_contents = {}
        
        # 使用并行抓取来提高性能
        if urls_to_scrape:
            scraped_contents = await self.search_and_scrape_multi(query, urls_to_scrape)
                
        # 将抓取内容添加到搜索结果中
        for result in organic_results:
            url = result.get("link")
            if url in scraped_contents:
                result["scraped_content"] = scraped_contents[url]
            else:
                result["scraped_content"] = ""
                
        return {
            "query": query,
            "organic": organic_results
        }

    async def search(self, query: str, num_results: int = 5, main_container=None) -> Dict[str, Any]:
        """
        搜索方法 - 直接调用search_web并添加优化的查询
        
        Args:
            query: 搜索查询
            num_results: 结果数量
            main_container: 显示容器
            
        Returns:
            搜索结果
        """
        # 检查是否应该优化查询以获取更多官方网站
        optimized_query = query
        
        # 添加官方网站关键字以获得更多官方结果
        if any(term in query.lower() for term in ["university", "college", "msc", "master", "program", "degree"]):
            # 检查查询中是否有具体大学名称
            uni_names = ["harvard", "stanford", "mit", "oxford", "cambridge", "yale", "princeton", 
                         "columbia", "ucla", "berkeley", "imperial", "ucl", "eth", "lse"]
            
            has_uni_name = any(name in query.lower() for name in uni_names)
            
            # 如果查询已经包含大学名称，优化为查找官方信息
            if has_uni_name:
                optimized_query = f"{query} official site"
            # 否则，可能是一般性查询，添加大学关键词
            else:
                # 检查查询中是否已经有官方关键词
                if not any(term in query.lower() for term in ["official", "site", "website", "admission"]):
                    optimized_query = f"{query} official university information"
        
        print(f"原始查询: {query}")
        print(f"优化查询: {optimized_query}")
        
        # 调用现有的搜索web方法
        return await self.search_web(optimized_query, main_container)