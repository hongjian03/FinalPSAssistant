import os
import streamlit as st
import asyncio
from typing import Dict, Any, Optional
import requests
import json

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
        收集大学和专业信息，生成院校信息收集报告。
        
        Args:
            university: 目标大学
            major: 目标专业
            custom_requirements: 用户提供的自定义要求
            
        Returns:
            格式化的院校信息收集报告
        """
        try:
            # 创建主容器用于显示所有内容
            main_container = st.container()
            
            # 创建初始化容器
            with main_container:
                st.subheader("初始化网络搜索功能")
                
                # 创建专门的容器来显示初始化进度
                init_container = st.container()
                with init_container:
                    st.info("正在初始化MCP连接以执行Web搜索...")
            
            # 尝试初始化Serper客户端，传递容器确保UI在主区域显示
            initialized = await self.serper_client.initialize(main_container=init_container)
            if not initialized:
                with main_container:
                    st.error("无法初始化Serper客户端进行网络搜索。将使用基础LLM知识生成信息。")
                return self._generate_info_with_llm(university, major, custom_requirements, main_container)
            
            # 检查输入参数
            if not university or not university.strip():
                return "**错误：未提供目标大学。请输入一个有效的大学名称。**"
                
            if not major or not major.strip():
                return "**错误：未提供目标专业。请输入一个有效的专业名称。**"
            
            # 构建搜索查询
            search_query = f"{university} {major} postgraduate program requirements application"
            
            # 执行Web搜索
            search_container = st.container()
            search_results = await self.serper_client.search_web(search_query, main_container=search_container)
            
            # 检查搜索结果是否包含错误
            if "error" in search_results:
                error_msg = search_results["error"]
                with main_container:
                    st.error(f"执行Web搜索时出错: {error_msg}")
                    st.warning("搜索失败，将使用LLM生成院校信息。请注意，此信息可能不是最新的。")
                return self._generate_info_with_llm(university, major, custom_requirements, main_container)
            
            # 检查搜索结果是否有效
            if not search_results or "organic" not in search_results or not search_results["organic"]:
                with main_container:
                    st.warning(f"未找到关于{university}的{major}专业的搜索结果。将使用LLM生成基本信息。")
                return self._generate_info_with_llm(university, major, custom_requirements, main_container)
            
            # 检查搜索结果并显示
            if len(search_results.get('organic', [])) > 0:
                with main_container:
                    result_container = st.container()
                    with result_container:
                        st.subheader("搜索结果摘要")
                        st.caption(f"找到 {len(search_results.get('organic', []))} 条相关结果")
                        for i, result in enumerate(search_results.get('organic', [])[:3], 1):
                            st.markdown(f"**{i}. {result.get('title', '无标题')}**")
                            st.caption(f"来源: {result.get('link', '无链接')}")
            
            # 根据搜索结果生成提示
            prompt = self._build_info_prompt(university, major, search_results, custom_requirements)
            
            # 显示生成信息
            report_container = st.container()
            with report_container:
                st.subheader("生成院校信息报告")
                report_progress = st.progress(0)
                report_status = st.empty()
                
                # 更新进度
                report_status.info(f"使用 {self.model_name} 生成院校信息报告...")
                report_progress.progress(30)
                
                # 调用OpenRouter API生成报告
                report = self._call_openrouter_api(prompt, university, major)
                
                # 更新进度
                report_progress.progress(100)
                if not report.startswith("**错误："):
                    report_status.success("院校信息报告生成成功")
                else:
                    report_status.error("院校信息报告生成失败")
                
            return report
        
        except Exception as e:
            error_msg = f"**错误：收集院校信息时出错 - {str(e)}**"
            with st.container():
                st.error(error_msg)
                st.warning("发生错误，将使用LLM生成院校信息。请注意，此信息可能不是最新的。")
            return self._generate_info_with_llm(university, major, custom_requirements)
            
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
        """
        构建用于生成院校信息报告的提示。
        
        Args:
            university: 目标大学
            major: 目标专业
            search_results: Web搜索结果
            custom_requirements: 用户的自定义要求
            
        Returns:
            生成的提示文本
        """
        # 准备搜索结果摘要
        search_content = ""
        
        # 确保我们有有机搜索结果
        if "organic" in search_results and search_results["organic"]:
            # 限制为最相关的前5个结果
            relevant_results = search_results["organic"][:5]
            
            search_content += "以下是从Web搜索获取的相关信息：\n\n"
            
            # 添加每个搜索结果
            for i, result in enumerate(relevant_results, 1):
                title = result.get("title", "无标题")
                link = result.get("link", "无链接")
                snippet = result.get("snippet", result.get("description", "无内容摘要"))
                
                search_content += f"信息源 {i}: {title}\n"
                search_content += f"链接: {link}\n"
                search_content += f"摘要: {snippet}\n\n"
        # 兼容其他可能的结果格式
        elif "results" in search_results and search_results["results"]:
            # 适配一些搜索API返回的不同结构
            relevant_results = search_results["results"][:5]
            
            search_content += "以下是从Web搜索获取的相关信息：\n\n"
            
            # 添加每个搜索结果
            for i, result in enumerate(relevant_results, 1):
                title = result.get("title", "无标题")
                link = result.get("link", result.get("url", "无链接"))
                snippet = result.get("snippet", result.get("description", result.get("content", "无内容摘要")))
                
                search_content += f"信息源 {i}: {title}\n"
                search_content += f"链接: {link}\n"
                search_content += f"摘要: {snippet}\n\n"
        # 如果没有结构化的搜索结果，但有原始文本响应
        elif isinstance(search_results, str) and len(search_results) > 0:
            search_content += "以下是从Web搜索获取的相关信息：\n\n"
            search_content += search_results[:2000] + "..." if len(search_results) > 2000 else search_results
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
        
        你是一位专业的高等教育顾问，专门负责收集和分析国际高校的招生信息。你的专长是整理与总结硕士研究生项目的重要信息，特别是针对国际学生申请者的相关要求和流程。
        
        # 任务
        
        请基于提供的搜索结果和你的知识，全面准确地收集并整理以下关于{university}的{major}专业的关键信息:
        
        1. 项目概述：项目名称、学位类型、学制时长、重要特色
        2. 申请要求：学历背景、语言要求(雅思/托福分数)、GPA要求或其他学术标准
        3. 申请流程：申请截止日期、所需材料、申请费用等
        4. 课程结构：核心课程、选修方向、特色课程、实习或研究机会
        5. 相关资源：项目官网链接、招生办联系方式
        
        {custom_req_text}
        
        # 搜索结果
        
        {search_content}
        
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
        [列出本报告的信息来源，如搜索结果或模型知识]
        
        重要提示：
        1. 优先使用搜索结果中的信息，并引用信息来源
        2. 如果搜索结果中缺少某些信息，可以使用你的知识进行补充，但请明确指出这部分是估计信息
        3. 保持客观专业的语气，专注于事实性信息
        4. 如有冲突信息，请分析优先采用最可靠的来源（如官方网站信息）
        5. 不要编造不存在的信息，如不确定，请明确说明
        """
        
        return prompt
    
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