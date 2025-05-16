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
                "serper",
                "scrape"
            ]
            
            # 显示基本连接信息
            status_text.info("开始初始化Serper MCP服务")
            
            # 第一步：准备连接
            progress_bar.progress(10)
            status_text.info("正在检查连接参数...")
            await asyncio.sleep(0.3)
            
            # 尝试多次连接以减少TaskGroup错误的影响
            max_attempts = 3
            current_attempt = 0
            
            while current_attempt < max_attempts:
                current_attempt += 1
                progress_bar.progress(20 + current_attempt * 5)
                status_text.info(f"尝试连接 MCP 服务 (尝试 {current_attempt}/{max_attempts})...")
                
                # 简化错误处理逻辑，使用单一的大型try-except而不是嵌套
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
                                    async with asyncio.timeout(10):
                                        tools_result = await session.list_tools()
                                        
                                        # 成功获取工具列表
                                        if hasattr(tools_result, 'tools'):
                                            self.available_tools = [t.name for t in tools_result.tools]
                                            progress_bar.progress(80)
                                            status_text.info("已获取工具列表，正在查找搜索工具...")
                                            
                                            # 显示工具信息
                                            with st.expander("可用工具", expanded=False):
                                                for tool in tools_result.tools:
                                                    st.caption(f"工具: {tool.name}")
                                                    if hasattr(tool, 'description'):
                                                        st.caption(f"描述: {tool.description}")
                                            
                                            # 查找搜索工具
                                            for tool_name in search_tool_candidates:
                                                if tool_name in self.available_tools:
                                                    self.search_tool_name = tool_name
                                                    break
                                            
                                            # 如果没找到，尝试模糊匹配
                                            if not self.search_tool_name:
                                                for tool_name in self.available_tools:
                                                    if "search" in tool_name.lower() or "google" in tool_name.lower():
                                                        self.search_tool_name = tool_name
                                                        break
                                            
                                            # 检查是否找到工具
                                            if self.search_tool_name:
                                                progress_bar.progress(100)
                                                status_text.success(f"MCP连接成功! 已选择搜索工具: {self.search_tool_name}")
                                                return True
                                            elif len(self.available_tools) > 0:
                                                # 没找到搜索工具，使用第一个可用的
                                                self.search_tool_name = self.available_tools[0]
                                                progress_bar.progress(100)
                                                status_text.warning(f"未找到专用搜索工具，将使用 {self.search_tool_name} 工具作为替代")
                                                return True
                                            else:
                                                # 没有任何工具可用
                                                progress_bar.progress(100)
                                                status_text.error("MCP连接成功，但未找到任何可用工具!")
                                                return False
                                        else:
                                            # tools_result没有tools属性
                                            progress_bar.progress(80)
                                            status_text.warning("工具列表格式不正确，使用默认设置")
                                            self.search_tool_name = search_tool_candidates[0]
                                            self.available_tools = [self.search_tool_name]
                                            progress_bar.progress(100)
                                            status_text.warning(f"由于工具列表格式问题，使用默认搜索工具: {self.search_tool_name}")
                                            return True
                                except (asyncio.TimeoutError, Exception) as tool_error:
                                    # 获取工具列表失败
                                    progress_bar.progress(80)
                                    error_msg = str(tool_error)
                                    status_text.warning(f"获取工具列表失败: {error_msg[:50]}...")
                                    
                                    # 使用默认工具
                                    self.search_tool_name = search_tool_candidates[0]
                                    self.available_tools = [self.search_tool_name]
                                    progress_bar.progress(100)
                                    status_text.warning(f"由于工具列表获取失败，使用默认搜索工具: {self.search_tool_name}")
                                    return True
                except Exception as e:
                    # 所有其他错误，包括TaskGroup错误
                    error_msg = str(e)
                    if "TaskGroup" in error_msg and current_attempt < max_attempts:
                        # TaskGroup错误，尝试重试
                        status_text.warning(f"发生TaskGroup错误，重试中... ({current_attempt}/{max_attempts})")
                        await asyncio.sleep(1)
                        continue
                    elif current_attempt >= max_attempts:
                        # 最后一次尝试也失败了，使用默认设置
                        progress_bar.progress(90)
                        self.search_tool_name = search_tool_candidates[0]
                        self.available_tools = [self.search_tool_name]
                        progress_bar.progress(100)
                        status_text.warning(f"经过多次尝试后仍然出错，使用默认搜索工具: {self.search_tool_name}")
                        error_log.warning(f"最后一次错误: {error_msg[:200]}")
                        return True
                    else:
                        # 其他错误，继续重试
                        status_text.warning(f"连接出错: {type(e).__name__}, 重试中... ({current_attempt}/{max_attempts})")
                        await asyncio.sleep(0.5)
                        continue
            
            # 如果所有尝试都失败了，使用默认设置
            progress_bar.progress(100)
            status_text.error("无法建立MCP连接，使用默认设置")
            self.search_tool_name = search_tool_candidates[0]
            self.available_tools = [self.search_tool_name]
            return True
    
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
            scrape_progress = st.progress(0)
            scrape_status.info(f"正在抓取网页内容: {url}")
            
            # 检查是否有搜索工具可用
            if not self.search_tool_name:
                scrape_status.error("未找到有效的搜索工具")
                return f"无法抓取 {url} 的内容：未找到有效的搜索工具"
            
            # 最大重试次数
            max_retries = 3
            current_retry = 0
            
            # 保存最后一个错误消息用于诊断
            last_error = None
            
            while current_retry < max_retries:
                scrape_progress.progress(10 + current_retry * 10)  # 更新进度条
                
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
                    
                    # 更新进度
                    scrape_progress.progress(20 + current_retry * 10)
                    
                    # 预处理TaskGroup错误检测 - 这是一个预防措施
                    try:
                        # 设置较短的连接超时
                        async with asyncio.timeout(30):
                            # 使用streamable_http_client连接到服务器
                            async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                                # 更新进度
                                scrape_progress.progress(40 + current_retry * 10)
                                
                                try:
                                    # 使用较短的会话操作超时
                                    async with asyncio.timeout(25):
                                        # 创建MCP会话
                                        async with mcp.ClientSession(read_stream, write_stream) as session:
                                            # 初始化会话
                                            await session.initialize()
                                            
                                            # 更新进度
                                            scrape_progress.progress(60 + current_retry * 10)
                                            
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
                                            
                                            # 使用较短的工具调用超时，避免永久挂起
                                            try:
                                                async with asyncio.timeout(20):
                                                    # 更新进度  
                                                    scrape_progress.progress(70 + current_retry * 5)
                                                    
                                                    # 调用MCP工具
                                                    result = await session.call_tool(tool_name, arguments=args)
                                                    
                                                    # 更新进度
                                                    scrape_progress.progress(90)
                                                    
                                                    # 处理结果
                                                    if hasattr(result, 'result'):
                                                        # 成功获取结果
                                                        scrape_status.success(f"MCP {tool_name} 成功获取内容")
                                                        scrape_progress.progress(100)
                                                        
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
                                                        # 没有result属性，尝试其他方法
                                                        last_error = "MCP返回结果格式不正确，缺少result属性"
                                                        raise ValueError(last_error)
                                            except asyncio.TimeoutError:
                                                # 工具调用超时，尝试下一个工具
                                                scrape_status.warning(f"工具调用超时 (尝试 {current_retry+1}/{max_retries})")
                                                last_error = "工具调用超时，尝试其他方法"
                                                current_retry += 1
                                                continue
                                            except Exception as tool_error:
                                                error_msg = str(tool_error)
                                                last_error = error_msg
                                                
                                                # 特殊处理TaskGroup错误
                                                if "TaskGroup" in error_msg or "asyncio" in error_msg:
                                                    scrape_status.warning(f"工具调用出现TaskGroup错误，尝试其他方法 (尝试 {current_retry+1}/{max_retries})")
                                                    current_retry += 1
                                                    continue
                                                else:
                                                    # 其他错误，检查是否有重试机会
                                                    scrape_status.warning(f"工具调用错误: {error_msg[:50]}... (尝试 {current_retry+1}/{max_retries})")
                                                    current_retry += 1
                                                    continue
                                except asyncio.TimeoutError:
                                    # 会话操作超时，尝试下一次
                                    scrape_status.warning(f"MCP会话操作超时 (尝试 {current_retry+1}/{max_retries})")
                                    last_error = "MCP会话操作超时，尝试其他方法"
                                    current_retry += 1
                                    continue
                                except Exception as session_error:
                                    error_msg = str(session_error)
                                    last_error = error_msg
                                    
                                    # 特殊处理TaskGroup错误
                                    if "TaskGroup" in error_msg or "asyncio" in error_msg:
                                        scrape_status.warning(f"MCP会话出现TaskGroup错误，尝试其他方法 (尝试 {current_retry+1}/{max_retries})")
                                        current_retry += 1
                                        continue
                                    else:
                                        # 其他错误，尝试下一次
                                        scrape_status.warning(f"MCP会话错误: {error_msg[:50]}... (尝试 {current_retry+1}/{max_retries})")
                                        current_retry += 1
                                        continue
                    except asyncio.TimeoutError:
                        # 连接超时，尝试下一次
                        scrape_status.warning(f"MCP连接超时 (尝试 {current_retry+1}/{max_retries})")
                        last_error = "MCP连接超时，尝试其他方法"
                        current_retry += 1
                        continue
                    except Exception as conn_error:
                        error_msg = str(conn_error)
                        last_error = error_msg
                        
                        # 特殊处理TaskGroup错误
                        if "TaskGroup" in error_msg or "asyncio" in error_msg:
                            scrape_status.warning(f"MCP连接出现TaskGroup错误，尝试其他方法 (尝试 {current_retry+1}/{max_retries})")
                            current_retry += 1
                            continue
                        else:
                            # 其他错误，尝试下一次
                            scrape_status.warning(f"MCP连接错误: {error_msg[:50]}... (尝试 {current_retry+1}/{max_retries})")
                            current_retry += 1
                            continue
                
                except Exception as e:
                    # 处理所有其他错误
                    error_msg = str(e)
                    last_error = error_msg
                    
                    # 更新状态
                    scrape_status.warning(f"抓取错误: {error_msg[:100]}... (尝试 {current_retry+1}/{max_retries})")
                    
                    # 继续下一次尝试
                    current_retry += 1
                    continue
            
            # 如果所有重试都失败，返回一个提供最后错误信息的友好消息
            scrape_progress.progress(100)
            scrape_status.error("所有抓取方法都失败")
            
            # 尝试直接抓取URL内容作为最后手段
            try:
                scrape_status.info("尝试直接抓取URL内容...")
                # 使用requests直接抓取
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    # 检查内容类型，只处理文本
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' in content_type or 'text/plain' in content_type:
                        # 提取页面标题
                        import re
                        title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
                        title = title_match.group(1) if title_match else url
                        
                        # 限制内容大小
                        content = response.text[:10000] + "..." if len(response.text) > 10000 else response.text
                        
                        scrape_status.success("成功直接抓取URL内容")
                        return f"## {title}\n\n{content}\n\n来源: {url}"
            except Exception as req_error:
                # 直接抓取也失败，记录错误
                with st.expander("直接抓取错误详情"):
                    st.error(f"直接抓取失败: {str(req_error)}")
            
            # 所有方法都失败，返回错误信息
            error_details = f"最后错误: {last_error}" if last_error else "多次尝试失败，无法获取详细错误信息"
            with st.expander("抓取错误详情"):
                st.error(error_details)
            
            return f"无法抓取 {url} 的内容。尝试了多种方法但都失败了。\n{error_details}\n\n建议访问网站手动查看内容。"
    
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
            
            # 检查是否有MCP搜索工具
            if not self.search_tool_name:
                search_status.warning("未找到MCP搜索工具，将使用备用搜索方法")
                return await self._fallback_search(query, search_progress, search_status)
            
            # 尝试使用MCP进行搜索
            try:
                search_progress.progress(20)
                search_status.info("初始化MCP搜索工具...")
                
                # 使用特定处理来避免TaskGroup错误
                try:
                    # 设置较短的超时时间
                    async with asyncio.timeout(30):
                        # 使用streamable_http_client连接到服务器
                        async with streamablehttp_client(self.url) as (read_stream, write_stream, _):
                            search_progress.progress(40)
                            search_status.info("创建MCP会话...")
                            
                            # 创建MCP会话
                            async with mcp.ClientSession(read_stream, write_stream) as session:
                                # 初始化会话
                                await session.initialize()
                                
                                search_progress.progress(60)
                                search_status.info(f"使用 {self.search_tool_name} 执行搜索: {query}")
                                
                                # 准备搜索参数 - 根据工具类型设置不同参数格式
                                if self.search_tool_name == "google_search":
                                    args = {
                                        "query": query,
                                        "gl": "us",
                                        "hl": "en",
                                        "numResults": 8
                                    }
                                else:
                                    args = {"query": query}
                                
                                # 调用MCP工具进行搜索
                                try:
                                    # 使用一个额外的超时来避免工具调用卡住
                                    async with asyncio.timeout(20):
                                        result = await session.call_tool(self.search_tool_name, arguments=args)
                                        
                                    search_progress.progress(80)
                                    search_status.info("处理搜索结果...")
                                    
                                    # 处理搜索结果
                                    if hasattr(result, 'result'):
                                        if isinstance(result.result, dict):
                                            # 标准化结果格式
                                            formatted_results = self._standardize_mcp_results(result.result, query)
                                            
                                            search_progress.progress(100)
                                            result_count = len(formatted_results.get('organic', []))
                                            search_status.success(f"搜索成功，找到 {result_count} 条结果")
                                            return formatted_results
                                        else:
                                            # 处理非字典结果
                                            search_progress.progress(100)
                                            search_status.warning("非标准搜索结果格式，需要转换")
                                            
                                            # 尝试将结果转换为标准格式
                                            return self._convert_to_standard_format(result.result, query)
                                    else:
                                        search_progress.progress(100)
                                        search_status.warning("MCP返回了无效的结果格式")
                                        return await self._fallback_search(query, search_progress, search_status)
                                except asyncio.TimeoutError:
                                    search_progress.progress(85)
                                    search_status.warning("工具调用超时，切换到备用方法")
                                    return await self._fallback_search(query, search_progress, search_status)
                                except Exception as tool_error:
                                    if "TaskGroup" in str(tool_error):
                                        search_progress.progress(85)
                                        search_status.warning("工具调用出现TaskGroup错误，切换到备用方法")
                                        # 由于是TaskGroup错误，没有办法通过MCP方法修复，使用备用方法
                                        return await self._fallback_search(query, search_progress, search_status)
                                    else:
                                        raise tool_error
                
                except asyncio.TimeoutError:
                    search_progress.progress(90)
                    search_status.warning("MCP连接超时，使用备用搜索")
                    return await self._fallback_search(query, search_progress, search_status)
                except Exception as e:
                    error_msg = str(e)
                    # 特殊处理TaskGroup错误
                    if "TaskGroup" in error_msg:
                        search_status.warning("MCP会话出现TaskGroup错误，使用备用搜索方法")
                        return await self._fallback_search(query, search_progress, search_status)
                    else:
                        search_status.error(f"MCP错误: {type(e).__name__}")
                        with st.expander("错误详情", expanded=False):
                            st.code(error_msg)
                        return await self._fallback_search(query, search_progress, search_status)
            
            except Exception as e:
                # 处理所有其他异常
                search_progress.progress(100)
                search_status.error(f"搜索错误: {str(e)[:100]}...")
                
                # 记录详细的错误信息
                with st.expander("错误详情", expanded=False):
                    st.code(traceback.format_exc())
                
                # 使用备用搜索作为最后的手段
                return await self._fallback_search(query, search_progress, search_status)
    
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
            
            payload = {
                "q": query,
                "gl": "us",
                "hl": "en",
                "num": 10,
                "autocorrect": True
            }
            
            # 记录搜索参数
            status_text.info(f"搜索参数: query='{query}'")
            
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
                        
                        kg_content = f"## {kg_title} ({kg_type})\n\n{kg_description}\n\n"
                        
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
            else:
                # 处理API错误
                progress_bar.progress(100)
                status_text.error(f"搜索失败: {response.status_code}")
                
                # 生成模拟结果
                search_results = self._generate_mock_results(query)
                
                # 显示错误信息
                try:
                    error_content = response.json()
                    st.info(f"系统将使用已有知识生成信息 - API错误: {json.dumps(error_content)}")
                except:
                    st.info(f"系统将使用已有知识生成信息 - API响应: {response.text}")
                
                return search_results
        except Exception as e:
            error_msg = str(e)
            
            # 更新UI状态
            if progress_bar and status_text:
                progress_bar.progress(100)
                status_text.error(f"搜索过程中出错: {error_msg}")
            
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