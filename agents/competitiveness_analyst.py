import os
import io
from PIL import Image
from typing import Dict, Any, Optional
import requests
import json
import streamlit as st
from langchain.chains import LLMChain
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from config.prompts import load_prompts

class CompetitivenessAnalyst:
    """
    Agent responsible for analyzing student competitiveness and generating competitiveness reports.
    Can use multiple LLM models based on user selection via OpenRouter API.
    """
    
    def __init__(self, model_name=None):
        """
        Initialize the Competitiveness Analyst agent.
        
        Args:
            model_name: The name of the LLM model to use via OpenRouter
        """
        self.prompts = load_prompts()["analyst"]
        
        # 设置模型名称，如果未提供则使用默认值
        self.model_name = model_name if model_name else "anthropic/claude-3-5-sonnet"
        
        # Get API key from Streamlit secrets (OpenRouter unified API key)
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
        # Set API endpoint for OpenRouter
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def extract_transcript_data(self, image: Image.Image) -> str:
        """
        Extract transcript data from an uploaded image.
        
        Args:
            image: The transcript image uploaded by the user
            
        Returns:
            String representation of the extracted transcript data
        """
        # Convert image to bytes for API processing
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format=image.format if image.format else 'JPEG')
        img_byte_arr = img_byte_arr.getvalue()
        
        # In a real implementation, you would call the vision model API here
        # For now, we'll return a mock response
        
        # Mock response - in production, replace with actual API call
        mock_transcript = """
        Student Name: Zhang Wei
        Student ID: 2022XJU456
        Program: Computer Science
        Academic Year: 2023-2024
        
        Courses:
        - CSE101 Introduction to Programming: A (90%)
        - CSE102 Data Structures and Algorithms: A- (85%)
        - MTH201 Linear Algebra: B+ (78%)
        - CSE201 Database Systems: A (92%)
        - CSE205 Computer Networks: B (75%)
        - ENG101 Academic English: B+ (79%)
        
        Current GPA: 3.76/4.0
        """
        
        return mock_transcript
    
    def generate_report(self, university: str, major: str, predicted_degree: str, transcript_content: str, custom_requirements: str = "") -> str:
        """
        Generate a competitiveness analysis report based on the provided information.
        
        Args:
            university: The student's university
            major: The student's major
            predicted_degree: The student's predicted degree classification
            transcript_content: The extracted transcript data
            custom_requirements: Optional custom requirements or questions from the user
            
        Returns:
            A formatted competitiveness analysis report
        """
        try:
            # 准备自定义需求部分（如果有）
            custom_req_text = ""
            if custom_requirements and custom_requirements.strip():
                custom_req_text = f"""
                Additional Requirements/Questions:
                {custom_requirements}
                
                Please address these specific requirements/questions in your analysis.
                """
            
            # Prepare prompt with provided information
            prompt = f"""
            {self.prompts['role']}
            
            {self.prompts['task']}
            
            Information:
            University: {university}
            Major: {major}
            Predicted Degree Classification: {predicted_degree}
            Transcript Data:
            {transcript_content}
            {custom_req_text}
            
            {self.prompts['output']}
            """
            
            # Call OpenRouter API with selected model
            return self._call_openrouter_api(prompt, university, major, predicted_degree)
                
        except Exception as e:
            st.error(f"Error generating competitiveness report: {str(e)}")
            return self._get_mock_report(university, major, predicted_degree)
    
    def _call_openrouter_api(self, prompt: str, university: str, major: str, predicted_degree: str) -> str:
        """Call OpenRouter API to generate report with selected model."""
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
        
        # 在 OpenRouter 调用之前直接记录 LangSmith 元数据
        provider = "openrouter"
        model_name = self.model_name
        if "/" in model_name:
            provider = model_name.split("/")[0]
        
        # 创建初始输入数据
        input_data = {"messages": [{"role": "user", "content": prompt}]}
        
        with st.spinner(f"Generating competitiveness report with {self.model_name}..."):
            # 使用更简单的方法追踪 - 避免使用 Client/trace
            try:
                # 直接发送请求，不使用 trace
                response = requests.post(self.api_url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    # 手动记录到 LangSmith，如果有需要
                    # 这里可以添加代码将模型使用信息记录到其他地方
                    
                    return content
                else:
                    st.error(f"OpenRouter API Error ({self.model_name}): {response.status_code} - {response.text}")
                    return self._get_mock_report(university, major, predicted_degree)
            except Exception as e:
                # 处理异常
                st.error(f"Error in OpenRouter API call: {str(e)}")
                return self._get_mock_report(university, major, predicted_degree)
    
    def _get_mock_report(self, university: str, major: str, predicted_degree: str) -> str:
        """
        Get a mock competitiveness report as a fallback.
        
        Returns:
            Mock competitiveness report string
        """
        # Fill in with provided data or defaults
        university = university or "Xi'an Jiaotong-Liverpool University"
        major = major or "Computer Science"
        predicted_degree = predicted_degree or "First Class"
        
        mock_report = f"""
        # Competitiveness Analysis Report

        ## Student Profile
        - **University**: {university}
        - **Major**: {major}
        - **Predicted Degree**: {predicted_degree}
        - **Current GPA**: 3.76/4.0

        ## Academic Strengths
        - Strong performance in core Computer Science courses (90-92%)
        - Particularly excellent in Programming and Database Systems
        - Good balance of technical and communication skills

        ## Areas for Improvement
        - Mathematics performance is above average but could be stronger (78%)
        - Computer Networks score (75%) is the lowest among technical subjects

        ## Competitiveness Assessment
        
        ### Overall Rating: ★★★★☆ (4/5) - Strong Candidate
        
        The student demonstrates a strong academic profile with a high GPA of 3.76/4.0, which places them in approximately the top 15% of Computer Science graduates. Their predicted First Class degree further strengthens their application.

        ### Program Suitability
        
        **Highly Competitive For**:
        - MSc Computer Science
        - MSc Software Engineering
        - MSc Data Science
        - MSc Human-Computer Interaction
        
        **Moderately Competitive For**:
        - MSc Artificial Intelligence
        - MSc Machine Learning
        - MSc Advanced Computing
        
        **Less Competitive For**:
        - MSc Computational Statistics and Machine Learning (due to mathematics score)
        - MSc Financial Computing (requires stronger mathematics)

        ## Recommendations for Improvement
        
        1. Consider taking additional mathematics or statistics courses to strengthen quantitative skills
        2. Pursue projects or certifications in networking to address the lower grade in Computer Networks
        3. Gain practical experience through internships or research projects to enhance competitiveness
        4. Consider preparing for standardized tests like GRE to further strengthen applications
        
        ## Additional Notes
        
        The student's academic profile shows consistent performance across multiple academic years, which is viewed favorably by admissions committees. Their strong grades in core Computer Science subjects indicate good preparation for advanced study in the field.
        """
        
        return mock_report 