import os
import streamlit as st
import asyncio
from typing import Dict, Any, Optional
import requests
import json
import traceback
import time

from .serper_client import SerperClient

class PSInfoCollector:
    """
    Agent 1: 负责搜索院校及专业信息，出具院校信息收集报告
    """
    
    def __init__(self, model_name=None):
        """
        初始化院校信息收集代理。
        
        Args:
            model_name: 使用的LLM模型名称
        """
        # 设置模型名称，如果未提供则使用默认值
        self.model_name = model_name if model_name else "anthropic/claude-3-7-sonnet"
        
        # 从Streamlit secrets获取API密钥
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
        # 设置OpenRouter API端点
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # 初始化Serper客户端（用于网络搜索）
        self.serper_client = SerperClient()
    
    async def collect_information(self, university: str, major: str, custom_requirements: str = "") -> str:
        """
        收集大学和专业信息。
        
        Args:
            university: 目标大学
            major: 目标专业
            custom_requirements: 用户提供的自定义要求
            
        Returns:
            收集的院校信息报告
        """
        # 创建一个容器来组织UI
        search_setup_container = st.container()
        
        with search_setup_container:
            st.write(f"## 正在收集 {university} 的 {major} 专业信息")
            
            # 检查是否需要初始化Serper客户端
            if not hasattr(self.serper_client, 'search_tool_name') or not self.serper_client.search_tool_name:
                try:
                    st.info("正在初始化Web搜索客户端...")
                    await self.serper_client.initialize(search_setup_container)
                except Exception as init_error:
                    st.error(f"初始化搜索客户端时出错: {str(init_error)}")
                    st.warning("将使用基础知识生成院校信息。请注意，此信息可能不是最新的。")
                    return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
        
        try:
            # 准备搜索查询 - 添加更专业的搜索词以找到更多项目信息
            search_terms = [
                f"{university} {major} program",
                f"{university} {major} admission requirements",
                f"{university} {major} application",
                f"{university} {major} curriculum"
            ]
            
            # 选择第一个搜索词作为主搜索
            search_query = search_terms[0]
            
            with search_setup_container:
                st.info(f"搜索查询: {search_query}")
            
            # 执行Web搜索，确保进度显示在search_setup_container中
            try:
                # 第一次尝试搜索
                search_results = await self.serper_client.search_web(search_query, main_container=search_setup_container)
                
                # 检查结果质量，如果不足够好，尝试备用查询
                if (not search_results or "organic" not in search_results or 
                   len(search_results.get("organic", [])) < 2 or
                   all("example.com" in result.get("link", "") for result in search_results.get("organic", []))):
                    
                    # 尝试备用查询
                    with search_setup_container:
                        st.warning(f"第一次搜索未返回足够的结果，尝试备用查询")
                    
                    # 尝试其他搜索词
                    for alternative_query in search_terms[1:]:
                        with search_setup_container:
                            st.info(f"备用搜索查询: {alternative_query}")
                        
                        alternative_results = await self.serper_client.search_web(alternative_query, main_container=search_setup_container)
                        
                        # 如果新结果更好，使用它们
                        if (alternative_results and "organic" in alternative_results and 
                            len(alternative_results.get("organic", [])) > len(search_results.get("organic", []))):
                            
                            with search_setup_container:
                                st.success(f"备用查询返回了更好的结果")
                            
                            # 合并结果 - 添加新结果到原始结果中
                            for result in alternative_results.get("organic", []):
                                # 检查这个URL是否已经在结果中
                                if not any(existing.get("link") == result.get("link") for existing in search_results.get("organic", [])):
                                    search_results.setdefault("organic", []).append(result)
                            
                            break
                
                # 检查合并后的搜索结果是否包含错误
                if "error" in search_results:
                    error_msg = search_results["error"]
                    with search_setup_container:
                        st.error(f"执行Web搜索时出错: {error_msg}")
                        st.warning("搜索失败，将使用基础知识生成院校信息。请注意，此信息可能不是最新的。")
                    return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
                
                # 检查搜索结果是否有效
                if not search_results or "organic" not in search_results or not search_results["organic"]:
                    with search_setup_container:
                        st.warning(f"未找到关于{university}的{major}专业的搜索结果。将使用基础知识生成信息。")
                    return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
                
                # 检查搜索结果是否都是模拟结果 (example.com链接)
                if all("example.com" in result.get("link", "") for result in search_results.get("organic", [])):
                    with search_setup_container:
                        st.warning("搜索只返回了模拟结果，可能无法提供准确信息。将尝试使用基础知识补充。")
                
                # 显示找到的结果数量
                with search_setup_container:
                    result_count = len(search_results.get("organic", []))
                    st.success(f"找到 {result_count} 条相关结果")
                    
                    # 在UI中展示搜索结果摘要
                    with st.expander("搜索结果摘要", expanded=False):
                        for i, result in enumerate(search_results.get("organic", [])[:5]):  # 只显示前5个结果
                            st.write(f"**{i+1}. {result.get('title', '无标题')}**")
                            st.caption(f"来源: {result.get('link', '无链接')}")
                            st.write(result.get('snippet', '无摘要'))
                            st.write("---")
            
            except Exception as search_error:
                # 捕获所有可能的搜索异常
                with search_setup_container:
                    st.error(f"搜索过程中出现错误: {str(search_error)}")
                    st.warning("由于搜索错误，将使用基础知识生成院校信息。")
                
                # 记录详细错误信息
                with search_setup_container:
                    with st.expander("错误详情", expanded=False):
                        st.code(traceback.format_exc())
                
                return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
            
            # 构建信息生成的提示词
            with search_setup_container:
                st.write("## 处理收集到的信息")
                generate_progress = st.progress(0)
                generate_status = st.empty()
                generate_status.info("准备生成院校信息报告...")
                
            # 构建提示
            prompt = self._build_info_prompt(university, major, search_results, custom_requirements)
            
            # 更新UI进度
            with search_setup_container:
                generate_progress.progress(40)
                generate_status.info(f"正在使用 {self.model_name} 分析搜索结果...")
            
            # 调用LLM生成报告
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://ps-assistant.streamlit.app", 
                "X-Title": "PS Assistant Tool"
            }
            
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            # 尝试请求LLM并处理可能的连接错误
            max_retries = 2
            current_retry = 0
            response = None
            
            while current_retry <= max_retries:
                try:
                    with search_setup_container:
                        generate_status.info(f"正在生成报告 (尝试 {current_retry+1}/{max_retries+1})...")
                    
                    # 发送API请求
                    response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
                    
                    # 检查响应
                    if response.status_code == 200:
                        break  # 成功获取响应
                    else:
                        # API错误，可能需要重试
                        with search_setup_container:
                            generate_status.warning(f"API返回错误码: {response.status_code}, 尝试重试...")
                        
                        current_retry += 1
                        if current_retry > max_retries:
                            # 所有重试都失败
                            raise Exception(f"API返回错误码: {response.status_code}, 响应: {response.text}")
                        else:
                            # 等待后重试
                            time.sleep(2)
                except (requests.RequestException, requests.Timeout) as e:
                    # 连接错误，可能需要重试
                    with search_setup_container:
                        generate_status.warning(f"连接错误: {str(e)}, 尝试重试...")
                    
                    current_retry += 1
                    if current_retry > max_retries:
                        raise Exception(f"连接错误: {str(e)}")
                    else:
                        # 等待后重试
                        time.sleep(2)
            
            # 如果所有尝试都失败
            if not response or response.status_code != 200:
                with search_setup_container:
                    generate_status.error("无法从API获取响应，尝试使用基础知识生成")
                return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
            
            # 处理响应
            result = response.json()
            
            # 提取内容
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                
                # 更新UI
                with search_setup_container:
                    generate_progress.progress(100)
                    generate_status.success("院校信息收集完成！")
                
                # 显示结果数据源
                with search_setup_container:
                    with st.expander("信息来源", expanded=False):
                        st.write("本报告基于以下来源生成:")
                        for i, result in enumerate(search_results.get("organic", [])[:5]):
                            st.write(f"{i+1}. [{result.get('title', '无标题')}]({result.get('link', '#')})")
                
                return content
            else:
                # 如果没有找到内容，使用备用方法
                with search_setup_container:
                    generate_status.error("API响应格式不正确，使用基础知识生成")
                return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
        
        except Exception as e:
            # 捕获所有其他异常
            error_msg = f"**错误：收集院校信息时出错 - {str(e)}**"
            with search_setup_container:
                st.error(error_msg)
                
                # 显示详细错误信息
                with st.expander("错误详情", expanded=False):
                    st.code(traceback.format_exc())
                
                st.warning("发生错误，将使用基础知识生成院校信息。请注意，此信息可能不是最新的。")
            
            return self._generate_info_with_llm(university, major, custom_requirements, search_setup_container)
            
    def _generate_info_with_llm(self, university: str, major: str, custom_requirements: str = "", main_container=None) -> str:
        """
        在无法使用Serper进行搜索时，直接使用LLM生成院校信息。
        
        Args:
            university: 目标大学
            major: 目标专业
            custom_requirements: 用户提供的自定义要求
            main_container: 主UI容器
            
        Returns:
            LLM生成的院校信息报告
        """
        # 创建容器用于显示UI（如果未提供）
        if main_container is None:
            main_container = st.container()
            
        # 显示状态提示
        with main_container:
            status_container = st.container()
            with status_container:
                st.subheader("基于模型知识生成院校信息")
                llm_progress = st.progress(0)
                llm_status = st.empty()
                llm_status.info("准备使用LLM基础知识生成院校信息...")
                llm_progress.progress(20)
        
        # 添加自定义要求（如果有）
        custom_req_text = ""
        if custom_requirements and custom_requirements.strip():
            custom_req_text = f"""
            用户附加要求:
            {custom_requirements}
            
            请在你的分析中考虑这些特定要求。
            """
            
        # 构建提示，直接让LLM基于现有知识生成
        prompt = f"""
        # 角色: 院校信息收集专家
        
        你是一位专业的高等教育顾问，专门负责收集和分析国际高校的招生信息。你的专长是整理与总结硕士研究生项目的重要信息，特别是针对国际学生申请者的相关要求和流程。
        
        # 任务
        
        请基于你的知识和专业经验，尽可能准确地收集并整理以下关于{university}的{major}专业的关键信息:
        
        1. 项目概述：项目名称、学位类型、学制时长、重要特色
        2. 申请要求：学历背景、语言要求(雅思/托福分数)、GPA要求或其他学术标准
        3. 申请流程：申请截止日期、所需材料、申请费用等
        4. 课程结构：核心课程、选修方向、特色课程、实习或研究机会
        5. 相关资源：项目官网链接、招生办联系方式(如果你知道的话)
        
        {custom_req_text}
        
        # 输出格式
        
        请将你的回答组织为一份专业的信息收集报告，格式如下：
        
        # {university} {major}专业信息收集报告
        
        ## 项目概览
        [简要描述项目的基本情况和主要特点]
        
        ## 申请要求
        [详细列出申请该项目所需满足的条件]
        
        ## 申请流程
        [列出申请步骤、截止日期和所需材料]
        
        ## 课程设置
        [介绍课程结构、核心课程和特色内容]
        
        ## 相关资源
        [提供重要链接和联系方式]
        
        ## 信息来源
        [列出本报告的信息来源，如果是LLM知识，请标明这是基于模型现有知识生成]
        
        重要提示：
        1. 如果你不确定某些具体信息（如具体截止日期），请明确指出这是估计或常见情况
        2. 请基于你已有的知识提供尽可能准确的信息
        3. 在信息来源部分明确说明这些信息是基于模型知识生成，并建议用户访问官方网站获取最新信息
        """
        
        # 更新进度
        with main_container:
            llm_progress.progress(50)
            llm_status.info(f"使用 {self.model_name} 生成院校信息...")
        
        # 调用OpenRouter API生成报告
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://ps-assistant.streamlit.app", 
            "X-Title": "PS Assistant Tool"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                with main_container:
                    llm_progress.progress(100)
                    llm_status.success("院校信息生成成功")
                return content
            else:
                error_msg = f"**错误：LLM生成信息失败: {response.status_code} - {response.text}**"
                with main_container:
                    llm_progress.progress(100)
                    llm_status.error("LLM生成信息失败")
                    st.error(error_msg)
                return error_msg
        except Exception as e:
            error_msg = f"**错误：LLM生成信息出现异常: {str(e)}**"
            with main_container:
                llm_progress.progress(100)
                llm_status.error("LLM生成信息出现异常")
                st.error(error_msg)
            return error_msg
    
    def _build_info_prompt(self, university: str, major: str, search_results: Dict[str, Any], custom_requirements: str) -> str:
        prompts = st.session_state.get("prompts")
        if not prompts:
            from config.prompts import DEFAULT_PROMPTS
            prompts = DEFAULT_PROMPTS
        role = prompts["ps_info_collector"]["role"]
        task = prompts["ps_info_collector"]["task"]
        output_format = prompts["ps_info_collector"]["output"]
        
        # 准备搜索结果摘要
        search_content = ""
        
        # 确保我们有有机搜索结果
        if "organic" in search_results and search_results["organic"]:
            # 限制为最相关的前4个结果
            relevant_results = search_results["organic"][:4]
            
            search_content += "以下是从Web搜索获取的相关信息：\n\n"
            
            # 添加每个搜索结果
            for i, result in enumerate(relevant_results, 1):
                title = result.get("title", "无标题")
                link = result.get("link", "无链接")
                snippet = result.get("snippet", result.get("description", "无内容摘要"))
                
                search_content += f"## 信息源 {i}: {title}\n"
                search_content += f"链接: {link}\n"
                search_content += f"摘要: {snippet}\n\n"
                
                # 添加抓取的页面内容（如果有）
                if "page_content" in result and result["page_content"]:
                    page_content = result["page_content"]
                    # 限制内容长度，避免提示词过长
                    max_content_length = 10000
                    if len(page_content) > max_content_length:
                        page_content = page_content[:max_content_length] + "...[内容过长已截断]"
                    
                    # 清理和格式化内容
                    page_content = self._clean_and_format_content(page_content)
                    
                    search_content += f"### 网页详细内容:\n{page_content}\n\n"
                    search_content += "---\n\n"
                else:
                    search_content += "（未能获取此页面的详细内容）\n\n"
                    search_content += "---\n\n"
        
        # 兼容其他可能的结果格式
        elif "results" in search_results and search_results["results"]:
            # 适配一些搜索API返回的不同结构
            relevant_results = search_results["results"][:4]
            
            search_content += "以下是从Web搜索获取的相关信息：\n\n"
            
            # 添加每个搜索结果
            for i, result in enumerate(relevant_results, 1):
                title = result.get("title", "无标题")
                link = result.get("link", result.get("url", "无链接"))
                snippet = result.get("snippet", result.get("description", result.get("content", "无内容摘要")))
                
                search_content += f"## 信息源 {i}: {title}\n"
                search_content += f"链接: {link}\n"
                search_content += f"摘要: {snippet}\n\n"
                
                # 添加抓取的页面内容（如果有）
                if "page_content" in result and result["page_content"]:
                    page_content = result["page_content"]
                    # 限制内容长度，避免提示词过长
                    max_content_length = 10000
                    if len(page_content) > max_content_length:
                        page_content = page_content[:max_content_length] + "...[内容过长已截断]"
                    
                    # 清理和格式化内容
                    page_content = self._clean_and_format_content(page_content)
                    
                    search_content += f"### 网页详细内容:\n{page_content}\n\n"
                    search_content += "---\n\n"
                else:
                    search_content += "（未能获取此页面的详细内容）\n\n"
                    search_content += "---\n\n"
        
        # 如果没有结构化的搜索结果，但有原始文本响应
        elif isinstance(search_results, str) and len(search_results) > 0:
            search_content += "以下是从Web搜索获取的相关信息：\n\n"
            search_content += search_results[:3000] + "..." if len(search_results) > 3000 else search_results
            search_content += "\n\n"
        else:
            search_content = "未找到相关搜索结果。请基于模型知识提供可能的信息，并明确标注是估计的信息。\n\n"
            
        # 添加自定义要求（如果有）
        custom_req_text = ""
        if custom_requirements and custom_requirements.strip():
            custom_req_text = f"""
            用户附加要求:
            {custom_requirements}
            
            请在你的分析中考虑这些特定要求。
            """
            
        # 构建最终提示
        prompt = f"""
        # 角色: 院校信息收集专家
        
        {role}
        
        # 目标大学与专业
        
        - 大学名称: {university}
        - 专业名称: {major}
        
        # 任务
        
        {task}
        
        {custom_req_text}
        
        # 提取信息指南
        
        你需要从提供的搜索内容中提取以下关键信息:
        
        1. 项目名称与学位类型:
           - 项目的正式名称
           - 授予的学位类型(如硕士、博士等)
           - 学制长度(如1年、2年等)
        
        2. 申请要求:
           - 学历背景要求
           - GPA要求(如3.0+/4.0)
           - 语言要求(雅思/托福最低分数)
           - 其他特殊要求(如工作经验、作品集等)
        
        3. 申请流程:
           - 申请截止日期
           - 申请材料清单
           - 申请费用
           - 录取流程与时间线
        
        4. 课程设置:
           - 核心课程
           - 选修课方向
           - 实习/研究机会
           - 特色项目
        
        5. 其他重要信息:
           - 学费信息
           - 奖学金机会
           - 就业前景
           - 官方联系方式
        
        # 搜索结果和网页内容
        
        {search_content}
        
        # 输出格式
        
        {output_format.replace("[大学名称]", university).replace("[专业名称]", major)}
        
        # 重要提示
        
        1. **优先使用搜索结果**: 优先使用提供的网页内容信息，尤其是来自官方大学网站的信息
        2. **保持准确性**: 确保所有信息准确无误，不要杜撰不存在的信息
        3. **内容完整性**: 确保涵盖所有关键部分，避免省略重要信息
        4. **明确标注估计信息**: 当搜索结果中缺少某些信息时，可以使用你的知识补充，但必须明确标注为"根据模型知识估计"
        5. **信息来源**: 在报告末尾列出所有信息来源，如官方网站链接等
        6. **格式严谨**: 保持专业的格式和语气，使用清晰的标题和小标题
        7. **准确摘录**: 从网页内容中摘录准确的课程信息、申请要求和截止日期
        8. **不要抄袭HTML或网页格式代码**: 只提取实质性内容，忽略HTML标签或格式代码
        
        确保最终报告是一份专业、全面、准确的院校信息收集报告，帮助申请者了解该项目的关键信息。
        """
        
        return prompt
    
    def _clean_and_format_content(self, content: str) -> str:
        """清理和格式化网页内容，移除无用的HTML标记和格式化问题"""
        # 简单替换一些常见的HTML实体
        content = content.replace('&nbsp;', ' ')
        content = content.replace('&amp;', '&')
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&quot;', '"')
        
        # 移除可能的JavaScript代码块
        import re
        content = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', content)
        
        # 尝试移除过多的空白行
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # 替换连续的空格
        content = re.sub(r' {2,}', ' ', content)
        
        # 移除大多数标签但保留段落结构
        content = re.sub(r'<[^>]*>', ' ', content)
        
        # 再次清理多余空格
        content = re.sub(r' {2,}', ' ', content)
        
        return content
    
    def _call_openrouter_api(self, prompt: str, university: str, major: str) -> str:
        """调用OpenRouter API使用选定的模型生成报告"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://ps-assistant.streamlit.app", 
            "X-Title": "PS Assistant Tool"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return content
            else:
                error_msg = f"**错误：OpenRouter API 调用失败 ({self.model_name}): {response.status_code} - {response.text}**"
                st.error(error_msg)
                return error_msg
        except Exception as e:
            error_msg = f"**错误：OpenRouter API 调用时发生异常: {str(e)}**"
            st.error(error_msg)
            return error_msg
    
    def run_async(self, coroutine):
        """帮助方法，用于同步运行异步方法"""
        return asyncio.run(coroutine) 