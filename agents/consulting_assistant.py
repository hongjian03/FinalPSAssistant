import os
import re
import requests
from typing import Dict, Any, List, Optional
import json
import streamlit as st
from bs4 import BeautifulSoup
from config.prompts import load_prompts
from agents.serper_client import SerperClient
import asyncio
import uuid
import traceback

class ConsultingAssistant:
    """
    Agent responsible for recommending suitable UCL programs based on 
    the competitiveness analysis report.
    """
    
    def __init__(self, model_name=None):
        """
        Initialize the Consulting Assistant agent.
        
        Args:
            model_name: The name of the LLM model to use via OpenRouter
        """
        self.prompts = load_prompts()["consultant"]
        
        # 设置模型名称，如果未提供则使用默认值
        self.model_name = model_name if model_name else "anthropic/claude-3-5-sonnet"
        
        # Get API key from Streamlit secrets (OpenRouter unified API key)
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
        # Set API endpoint for OpenRouter
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # 首先检查session_state中是否有已初始化的SerperClient实例
        if "serper_client" in st.session_state and st.session_state.serper_initialized:
            # 使用已初始化的共享实例
            st.info("使用全局已初始化的Serper客户端实例进行UCL项目搜索")
            self.serper_client = st.session_state.serper_client
            self.use_shared_client = True
        else:
            # 回退到创建新实例
            st.warning("未找到已初始化的Serper客户端，将创建新实例。网络搜索功能可能受限。")
            self.serper_client = SerperClient()
            self.use_shared_client = False
    
    async def search_ucl_programs_async(self, keywords: List[str]) -> List[Dict[str, str]]:
        """
        Asynchronously search for UCL programs using web search.
        
        Args:
            keywords: List of keywords to search for
            
        Returns:
            List of program information dictionaries
        """
        # Create container for showing progress
        search_container = st.container()
        
        with search_container:
            st.subheader("搜索UCL项目")
            search_status = st.empty()
            search_status.info(f"正在搜索关键词: {', '.join(keywords)}")
        
        try:
            # 创建搜索查询
            search_query = f"UCL University College London postgraduate {' '.join(keywords)} program requirements application"
            
            # 确保SerperClient已初始化
            if not self.use_shared_client:
                search_status.info("初始化搜索客户端...")
                initialized = await self.serper_client.initialize(main_container=search_container)
                if not initialized:
                    search_status.error("无法初始化搜索客户端，将使用默认项目数据")
                    return self.get_mock_programs()
            
            # 执行搜索
            search_status.info(f"搜索UCL项目: {search_query}")
            search_results = await self.serper_client.search_web(search_query, main_container=search_container)
            
            # 检查搜索结果是否有错误
            if "error" in search_results:
                search_status.warning(f"搜索出错: {search_results['error']}")
                return self.get_mock_programs()
            
            # 检查是否有有机结果
            if "organic" not in search_results or not search_results["organic"]:
                search_status.warning("未找到相关UCL项目")
                return self.get_mock_programs()
            
            # 处理搜索结果，提取项目信息
            programs = []
            for result in search_results["organic"][:5]:  # 使用前5个结果
                title = result.get("title", "")
                link = result.get("link", "")
                snippet = result.get("snippet", "")
                
                # 只处理UCL相关的结果
                if "ucl" in link.lower() or "ucl" in title.lower():
                    # 从搜索结果中提取项目信息
                    program_name = title
                    if " - UCL" in program_name:
                        program_name = program_name.split(" - UCL")[0]
                    if " | UCL" in program_name:
                        program_name = program_name.split(" | UCL")[0]
                    
                    # 基本结构
                    program_info = {
                        "program_name": program_name,
                        "program_url": link,
                        "description": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                        "department": self._extract_department(title, snippet)
                    }
                    
                    programs.append(program_info)
            
            search_status.success(f"找到 {len(programs)} 个相关UCL项目")
            
            # 如果没有找到相关项目，则使用默认数据
            if not programs:
                search_status.info("未找到符合条件的UCL项目，使用默认数据")
                return self.get_mock_programs()
                
            return programs
        
        except Exception as e:
            search_status.error(f"搜索UCL项目时出错: {str(e)}")
            return self.get_mock_programs()
    
    def search_ucl_programs(self, keywords: List[str]) -> List[Dict[str, str]]:
        """
        Search UCL website for programs matching the given keywords.
        
        Args:
            keywords: List of keywords to search for
            
        Returns:
            List of program information dictionaries
        """
        # Run the async search method synchronously
        return asyncio.run(self.search_ucl_programs_async(keywords))
    
    def _extract_department(self, title: str, description: str) -> str:
        """
        Extract department information from search result
        
        Args:
            title: The title of the search result
            description: The description or snippet
            
        Returns:
            Department name or default value
        """
        # Common UCL departments
        departments = [
            "Department of Computer Science",
            "Department of Statistical Science",
            "Department of Economics",
            "Department of Mathematics",
            "Department of Physics",
            "Department of Chemistry",
            "Department of Mechanical Engineering",
            "Department of Electronic Engineering",
            "Department of Civil Engineering",
            "UCL School of Management"
        ]
        
        # Look for department name in title and description
        for dept in departments:
            if dept.lower() in title.lower() or dept.lower() in description.lower():
                return dept
        
        # Default to faculty level if specific department not found
        faculties = [
            "Faculty of Engineering",
            "Faculty of Mathematical & Physical Sciences",
            "Faculty of Arts & Humanities",
            "Faculty of Social & Historical Sciences",
            "Faculty of Medical Sciences",
            "Faculty of Life Sciences"
        ]
        
        for faculty in faculties:
            if faculty.lower() in title.lower() or faculty.lower() in description.lower():
                return faculty
        
        # Default value if no department or faculty found
        return "UCL Graduate School"
    
    def get_mock_programs(self) -> List[Dict[str, str]]:
        """
        Get mock program data as a fallback when web search fails.
        
        Returns:
            List of mock program information dictionaries
        """
        # Mock program data
        mock_programs = [
            {
                "department": "Department of Computer Science",
                "program_name": "MSc Computer Science",
                "application_open": "October 2023",
                "application_close": "July 31, 2024",
                "program_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/computer-science-msc"
            },
            {
                "department": "Department of Computer Science",
                "program_name": "MSc Data Science and Machine Learning",
                "application_open": "October 2023",
                "application_close": "March 29, 2024",
                "program_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/data-science-machine-learning-msc"
            },
            {
                "department": "Department of Computer Science",
                "program_name": "MSc Software Systems Engineering",
                "application_open": "October 2023",
                "application_close": "July 31, 2024",
                "program_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/software-systems-engineering-msc"
            },
            {
                "department": "Department of Computer Science",
                "program_name": "MSc Web Technologies and Information Architecture",
                "application_open": "October 2023",
                "application_close": "July 31, 2024",
                "program_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/web-technologies-information-architecture-msc"
            },
            {
                "department": "Department of Statistical Science",
                "program_name": "MSc Statistics",
                "application_open": "October 2023",
                "application_close": "July 31, 2024",
                "program_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/statistics-msc"
            }
        ]
        
        return mock_programs
    
    def extract_keywords_from_report(self, competitiveness_report: str) -> List[str]:
        """
        Extract relevant keywords from the competitiveness report to search for programs.
        
        Args:
            competitiveness_report: The competitiveness analysis report
            
        Returns:
            List of keywords for program search
        """
        # In a real implementation, you would use NLP to extract keywords
        # For now, we'll return mock keywords based on the expected report format
        
        # Mock keywords
        keywords = ["Computer Science", "Software Engineering", "Data Science"]
        
        return keywords
    
    def recommend_projects(self, competitiveness_report: str, custom_requirements: str = "") -> str:
        """
        Generate program recommendations based on the competitiveness report.
        
        Args:
            competitiveness_report: The competitiveness analysis report
            custom_requirements: Optional custom requirements or questions from the user
            
        Returns:
            Formatted program recommendations
        """
        try:
            # Extract keywords from the report
            keywords = self.extract_keywords_from_report(competitiveness_report)
            
            # Search for matching programs using Serper web search
            programs = self.search_ucl_programs(keywords)
            
            # 准备自定义需求部分（如果有）
            custom_req_text = ""
            if custom_requirements and custom_requirements.strip():
                custom_req_text = f"""
                Additional Student Requirements/Questions:
                {custom_requirements}
                
                Please address these specific requirements/questions in your recommendations.
                """
            
            # Generate recommendations using LLM via OpenRouter
            prompt = f"""
            {self.prompts['role']}
            
            {self.prompts['task']}
            
            Competitiveness Report:
            {competitiveness_report}
            
            Available UCL Programs:
            {json.dumps(programs, indent=2)}
            {custom_req_text}
            
            {self.prompts['output']}
            """
            
            # Call OpenRouter API with the selected model
            return self._call_openrouter_api(prompt, programs)
                
        except Exception as e:
            st.error(f"Error generating program recommendations: {str(e)}")
            return self._format_program_recommendations(self.get_mock_programs())
    
    def _call_openrouter_api(self, prompt: str, fallback_programs: List[Dict[str, str]]) -> str:
        """Call OpenRouter API to generate recommendations with selected model."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://applicant-analysis.streamlit.app",
            "X-Title": "Applicant Analysis Tool"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500
        }
        
        # 在 OpenRouter 调用之前记录模型信息
        provider = "openrouter"
        model_name = self.model_name
        if "/" in model_name:
            provider = model_name.split("/")[0]
        
        # 创建输入数据
        input_data = {"messages": [{"role": "user", "content": prompt}]}
        
        with st.spinner(f"Generating program recommendations with {self.model_name}..."):
            # 使用更简单的方法调用 API
            try:
                # 直接发送请求
                response = requests.post(self.api_url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    # 可以添加额外的日志记录代码
                    
                    return content
                else:
                    st.error(f"OpenRouter API Error ({self.model_name}): {response.status_code} - {response.text}")
                    return self._format_program_recommendations(fallback_programs)
            except Exception as e:
                # 处理异常
                st.error(f"Error in OpenRouter API call: {str(e)}")
                return self._format_program_recommendations(fallback_programs)
    
    def _format_program_recommendations(self, programs: List[Dict[str, str]]) -> str:
        """
        Format program recommendations as Markdown (fallback method).
        
        Args:
            programs: List of program information dictionaries
            
        Returns:
            Formatted program recommendations as Markdown
        """
        recommendation_items = []
        for program in programs:
            recommendation_items.append(
                f"### {program['program_name']}\n"
                f"**Department**: {program['department']}\n"
                f"**Application Period**: {program['application_open']} to {program['application_close']}\n"
                f"**Program Link**: [{program['program_url']}]({program['program_url']})\n"
            )
        
        recommendations = "# UCL Program Recommendations\n\n" + "\n".join(recommendation_items)
        
        return recommendations 