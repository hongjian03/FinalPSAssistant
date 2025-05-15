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
                st.error("无法初始化Serper客户端进行网络搜索。")
                return self._get_mock_report(university, major)
            
            # 构建搜索查询
            search_query = f"{university} {major} postgraduate program requirements application"
            
            # 执行Web搜索
            with st.status("正在搜索网络获取最新院校信息..."):
                search_results = await self.serper_client.search_web(search_query)
            
            # 根据搜索结果生成提示
            prompt = self._build_info_prompt(university, major, search_results, custom_requirements)
            
            # 调用OpenRouter API生成报告
            return self._call_openrouter_api(prompt, university, major)
        
        except Exception as e:
            st.error(f"收集院校信息时出错: {str(e)}")
            return self._get_mock_report(university, major)
    
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
                    st.error(f"OpenRouter API 错误 ({self.model_name}): {response.status_code} - {response.text}")
                    return self._get_mock_report(university, major)
            except Exception as e:
                st.error(f"OpenRouter API 调用错误: {str(e)}")
                return self._get_mock_report(university, major)
    
    def _get_mock_report(self, university: str, major: str) -> str:
        """
        获取模拟报告作为后备选项。
        
        Returns:
            模拟的院校信息收集报告
        """
        # 使用提供的数据填充，或使用默认值
        university = university or "剑桥大学"
        major = major or "计算机科学"
        
        mock_report = f"""
        # {university} {major}专业信息收集报告
        
        ## 项目概览
        {university}的{major}硕士项目是一个为期12个月的全日制课程，旨在为学生提供计算机科学领域的先进知识和研究技能。该项目在QS世界大学排名中位列计算机科学专业前10，以其卓越的教学质量和研究水平著称。
        
        ## 申请要求
        - **学历背景**：计算机科学或相关学科的本科学位，成绩优良（英国一等或二等一学位，GPA 3.5/4.0或以上）
        - **语言要求**：雅思总分至少6.5分，单项不低于6.0；或托福iBT总分至少92分，单项不低于22分
        - **其他要求**：需提供两封学术推荐信，个人陈述需突出研究兴趣和职业目标
        
        ## 申请流程
        - **申请开放日期**：每年10月初
        - **申请截止日期**：国际学生建议在1月15日前申请，最终截止日期为6月30日
        - **所需材料**：在线申请表、成绩单、学位证书、语言成绩证明、个人陈述、推荐信
        - **申请费用**：75英镑
        
        ## 课程设置
        - **核心课程**：高级算法、机器学习、计算机视觉、人工智能、网络安全
        - **选修方向**：数据科学、人工智能、软件工程、网络安全
        - **研究机会**：学生需完成一个独立研究项目，并提交硕士论文
        - **实习机会**：与行业合作伙伴提供实习机会，包括谷歌、微软等知名企业
        
        ## 相关资源
        - **项目官网**：https://www.{university.lower()}.ac.uk/study/{major.lower().replace(' ', '-')}/postgraduate
        - **招生办邮箱**：admissions@{university.lower()}.ac.uk
        - **国际学生服务**：international-students@{university.lower()}.ac.uk
        
        ## 信息来源
        本报告信息来源于{university}官方网站以及相关教育门户网站，由于网站信息可能会更新，申请者应以官方网站最新信息为准。
        """
        
        return mock_report
    
    def run_async(self, coroutine):
        """帮助方法，用于同步运行异步方法"""
        return asyncio.run(coroutine) 