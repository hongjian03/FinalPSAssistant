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
        
        # 初始化Serper客户端
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
            # 确保Serper客户端初始化
            initialized = await self.serper_client.initialize()
            if not initialized:
                return "**错误：无法初始化Serper客户端进行网络搜索。请检查SERPER_API_KEY和SMITHERY_API_KEY是否正确设置。**"
            
            # 构建搜索查询
            search_query = f"{university} {major} postgraduate program requirements application"
            
            # 执行Web搜索
            with st.status("正在搜索网络获取最新院校信息..."):
                search_results = await self.serper_client.search_web(search_query)
                
                # 检查搜索结果是否包含错误
                if "error" in search_results:
                    return f"**错误：执行Web搜索时出错 - {search_results['error']}**"
                
                # 检查搜索结果是否有效
                if not search_results or "organic" not in search_results or not search_results["organic"]:
                    return f"**错误：未找到关于{university}的{major}专业的搜索结果。请检查拼写或尝试其他关键词。**"
            
            # 根据搜索结果生成提示
            prompt = self._build_info_prompt(university, major, search_results, custom_requirements)
            
            # 调用OpenRouter API生成报告
            report = self._call_openrouter_api(prompt, university, major)
            
            # 检查报告是否生成成功
            if report.startswith("**错误："):
                return report
                
            return report
        
        except Exception as e:
            error_msg = f"**错误：收集院校信息时出错 - {str(e)}**"
            st.error(error_msg)
            return error_msg
    
    def _build_info_prompt(self, university: str, major: str, search_results: Dict[str, Any], custom_requirements: str) -> str:
        """构建带有搜索结果的提示"""
        # 格式化搜索结果
        formatted_results = ""
        if search_results and "organic" in search_results:
            for i, result in enumerate(search_results.get("organic", [])[:5], 1):
                title = result.get("title", "No title")
                link = result.get("link", "No link")
                snippet = result.get("snippet", "No snippet")
                formatted_results += f"{i}. {title}\nURL: {link}\n摘要: {snippet}\n\n"
        
        # 添加自定义要求（如果有）
        custom_req_text = ""
        if custom_requirements and custom_requirements.strip():
            custom_req_text = f"""
            用户附加要求:
            {custom_requirements}
            
            请在你的分析中考虑这些特定要求。
            """
        
        # 构建完整提示
        prompt = f"""
        # 角色: 院校信息收集专家
        
        你是一位专业的高等教育顾问，专门负责收集和分析国际高校的招生信息。你的专长是整理与总结硕士研究生项目的重要信息，特别是针对国际学生申请者的相关要求和流程。
        
        # 任务
        
        请基于提供的网络搜索结果，全面收集并整理以下关于{university}的{major}专业的关键信息:
        
        1. 项目概述：项目名称、学位类型、学制时长、重要特色
        2. 申请要求：学历背景、语言要求(雅思/托福分数)、GPA要求或其他学术标准
        3. 申请流程：申请截止日期、所需材料、申请费用等
        4. 课程结构：核心课程、选修方向、特色课程、实习或研究机会
        5. 相关资源：项目官网链接、招生办联系方式、常见问题解答
        
        # 搜索结果
        
        以下是关于{university}的{major}项目的网络搜索结果:
        
        {formatted_results}
        
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
        [列出本报告的信息来源]
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
        
        with st.spinner(f"使用 {self.model_name} 生成院校信息报告..."):
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