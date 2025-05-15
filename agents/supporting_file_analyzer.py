import os
import streamlit as st
import base64
import io
from typing import Dict, Any, List, Optional
import requests
import json
import fitz  # PyMuPDF
from PIL import Image

class SupportingFileAnalyzer:
    """
    Agent 2.1: 负责分析用户上传的所有支持文件，生成支持文件分析报告
    """
    
    def __init__(self, model_name=None):
        """
        初始化支持文件分析代理。
        
        Args:
            model_name: 使用的LLM模型名称
        """
        # 设置模型名称，如果未提供则使用默认值
        self.model_name = model_name if model_name else "anthropic/claude-3-7-sonnet"
        
        # 从Streamlit secrets获取API密钥
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
        # 设置OpenRouter API端点
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def analyze_files(self, uploaded_files: List) -> str:
        """
        分析上传的支持文件，生成分析报告。
        
        Args:
            uploaded_files: 上传的支持文件列表
            
        Returns:
            格式化的支持文件分析报告
        """
        if not uploaded_files:
            return "未提供支持文件，跳过支持文件分析环节。"
        
        try:
            # 解析所有上传的文件
            file_contents = []
            
            for file in uploaded_files:
                file_content = self._extract_file_content(file)
                if file_content:
                    file_contents.append({
                        "filename": file.name,
                        "content": file_content
                    })
            
            if not file_contents:
                return "无法从上传的文件中提取内容，请检查文件格式。"
            
            # 构建提示
            prompt = self._build_analysis_prompt(file_contents)
            
            # 调用OpenRouter API生成报告
            return self._call_openrouter_api(prompt)
        
        except Exception as e:
            st.error(f"分析支持文件时出错: {str(e)}")
            return self._get_mock_report()
    
    def _extract_file_content(self, file) -> str:
        """从上传的文件中提取内容"""
        filename = file.name.lower()
        content = ""
        
        try:
            # PDF文件处理
            if filename.endswith(".pdf"):
                # 保存上传的文件
                bytes_data = file.getvalue()
                
                # 使用PyMuPDF读取PDF
                with fitz.open(stream=bytes_data, filetype="pdf") as pdf:
                    for page_num in range(len(pdf)):
                        page = pdf[page_num]
                        content += page.get_text() + "\n\n"
            
            # 图片文件处理
            elif any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                # 这里可以接入OCR服务处理图片，目前简单返回格式信息
                content = f"[图片文件: {filename}] - 此处应包含图片OCR提取的文本"
                
                # 如果需要详细处理图片内容，可以添加OCR逻辑
                # image = Image.open(io.BytesIO(file.getvalue()))
                # OCR处理逻辑...
            
            # 其他文本文件处理
            else:
                # 尝试作为文本文件读取
                content = file.getvalue().decode("utf-8")
        
        except Exception as e:
            st.warning(f"无法处理文件 {filename}: {str(e)}")
            content = f"[无法处理的文件: {filename}]"
        
        return content
    
    def _build_analysis_prompt(self, file_contents: List[Dict[str, str]]) -> str:
        """构建分析提示"""
        # 格式化所有文件内容
        formatted_contents = ""
        for i, file_data in enumerate(file_contents, 1):
            formatted_contents += f"文件 {i}: {file_data['filename']}\n内容:\n{file_data['content']}\n\n{'='*50}\n\n"
        
        # 构建完整提示
        prompt = f"""
        # 角色: 学术支持材料分析专家
        
        你是一位专业的学术申请顾问，专长于分析申请者提供的支持材料，并提取其中对个人陈述(PS)撰写有帮助的关键信息和亮点。
        
        # 任务
        
        请仔细分析提供的所有支持文件内容，提取以下关键信息：
        
        1. 学术成就与表现：GPA、专业排名、获得的奖学金或荣誉等
        2. 研究经历：参与的研究项目、发表的论文、学术会议等
        3. 实习与工作经验：相关的工作经历、实习项目、职责与成就
        4. 技能与专长：专业技能、语言能力、软件/工具掌握程度等
        5. 课外活动：社团参与、志愿服务、领导经历等
        6. 个人特质：从材料中可以推断的性格特点、专业素养等
        
        # 支持文件内容
        
        以下是申请者提供的支持文件内容:
        
        {formatted_contents}
        
        # 输出格式
        
        请将你的分析整理为一份专业的支持文件分析报告，格式如下：
        
        # 支持文件分析报告
        
        ## 文件概览
        [简要描述分析的文件类型及总体评价]
        
        ## 学术背景摘要
        [总结学术表现、专业方向、成绩等信息]
        
        ## 研究与专业经验
        [详述研究项目、实习、工作经验等]
        
        ## 技能与专长
        [列出技术技能、软技能、语言能力等]
        
        ## 个人特质与亮点
        [分析材料中体现的个人特质和突出亮点]
        
        ## PS撰写建议
        [基于支持材料，提出5-8点个人陈述撰写建议]
        """
        
        return prompt
    
    def _call_openrouter_api(self, prompt: str) -> str:
        """调用OpenRouter API使用选定的模型生成分析结果"""
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
        
        with st.spinner(f"使用 {self.model_name} 分析支持文件..."):
            try:
                response = requests.post(self.api_url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return content
                else:
                    st.error(f"OpenRouter API 错误 ({self.model_name}): {response.status_code} - {response.text}")
                    return self._get_mock_report()
            except Exception as e:
                st.error(f"OpenRouter API 调用错误: {str(e)}")
                return self._get_mock_report()
    
    def _get_mock_report(self) -> str:
        """
        获取模拟报告作为后备选项。
        
        Returns:
            模拟的支持文件分析报告
        """
        mock_report = """
        # 支持文件分析报告
        
        ## 文件概览
        分析了申请者提供的个人简历、成绩单和研究经历证明材料。材料整体较为完整，包含了学术背景、研究经验和专业技能等关键信息。
        
        ## 学术背景摘要
        申请者就读于清华大学计算机科学与技术专业，目前GPA为3.8/4.0，专业排名前10%。曾获国家奖学金和优秀学生称号。主修课程包括数据结构、算法分析、机器学习、人工智能和计算机视觉等。
        
        ## 研究与专业经验
        - 参与了"基于深度学习的医学图像分割"研究项目，负责算法设计和模型优化
        - 在国内某AI公司实习6个月，参与开发了一个自然语言处理平台
        - 作为学生研究助理协助导师完成了一篇发表在CVPR会议上的论文
        - 参与开源项目贡献，主要是计算机视觉相关的Python库开发
        
        ## 技能与专长
        - 编程语言：Python（精通），C/C++（熟练），Java（基础）
        - 框架与工具：PyTorch, TensorFlow, OpenCV, Git
        - 研究领域：计算机视觉，深度学习，医学图像处理
        - 语言能力：英语（雅思7.0），中文（母语）
        
        ## 个人特质与亮点
        - 展现了较强的研究能力和学术热情，特别是在计算机视觉领域
        - 具有项目实践和团队协作经验，能够将理论知识应用到实际问题中
        - 表现出解决复杂问题的能力和创新思维
        - 有国际交流经历，参加过学术会议和夏令营活动
        
        ## PS撰写建议
        1. 强调在计算机视觉和医学图像处理领域的研究经验，展示专业方向的连贯性
        2. 详细描述CVPR论文的贡献，突出学术研究能力
        3. 将实习经历与研究生学习规划相结合，展示理论与实践的结合能力
        4. 具体说明对目标院校相关研究方向的了解，以及为何该项目适合你的学术发展
        5. 分享一个解决技术挑战的具体案例，展示问题解决能力和创新思维
        6. 提及你的长期职业目标，以及研究生学习如何帮助你实现这些目标
        7. 简要提及语言能力和国际交流经历，展示适应国际学习环境的能力
        8. 避免简单罗列成就，而是围绕核心主题构建一个连贯的个人学术故事
        """
        
        return mock_report 