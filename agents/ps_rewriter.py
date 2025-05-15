import os
import streamlit as st
from typing import Dict, Any, Optional
import requests
import json

class PSRewriter:
    """
    Agent 3: 负责根据改写策略报告完成PS的最终改写
    """
    
    def __init__(self, model_name=None):
        """
        初始化PS改写代理。
        
        Args:
            model_name: 使用的LLM模型名称
        """
        # 设置模型名称，如果未提供则使用默认值
        self.model_name = model_name if model_name else "anthropic/claude-3-7-sonnet"
        
        # 从Streamlit secrets获取API密钥
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        
        # 设置OpenRouter API端点
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def rewrite_ps(self, ps_content: str, rewrite_strategy: str, university_info: str) -> str:
        """
        根据改写策略完成PS的最终改写。
        
        Args:
            ps_content: PS初稿内容
            rewrite_strategy: PS改写策略报告
            university_info: 院校信息收集报告
            
        Returns:
            改写后的PS
        """
        if not ps_content or not rewrite_strategy:
            return "缺少必要的PS初稿或改写策略，无法完成改写。"
        
        try:
            # 构建提示
            prompt = self._build_rewrite_prompt(ps_content, rewrite_strategy, university_info)
            
            # 调用OpenRouter API生成改写后的PS
            return self._call_openrouter_api(prompt)
        
        except Exception as e:
            st.error(f"改写PS时出错: {str(e)}")
            return self._get_mock_rewrite()
    
    def _build_rewrite_prompt(self, ps_content: str, rewrite_strategy: str, university_info: str) -> str:
        """构建改写提示"""
        # 构建完整提示
        prompt = f"""
        # 角色: 专业PS改写专家
        
        你是一位资深的个人陈述(Personal Statement)撰写专家，擅长将初稿改写成高质量的最终版本。你熟悉各类研究生项目的申请要求，能够准确把握院校期望，并根据申请者的背景创作出有说服力的个人陈述。
        
        # 任务
        
        请根据提供的PS初稿和改写策略报告，完成一份全面改写的个人陈述。你的改写应该：
        
        1. 完全遵循改写策略报告中的建议
        2. 保留原稿中的核心信息和个人经历，但大幅改进表达方式
        3. 增强PS与目标院校/专业的匹配度
        4. 提升整体结构和逻辑连贯性
        5. 确保语言流畅、专业且有吸引力
        6. 突出申请者的优势和独特价值
        
        # PS初稿内容
        
        ```
        {ps_content}
        ```
        
        # 改写策略报告
        
        ```
        {rewrite_strategy}
        ```
        
        # 院校信息
        
        ```
        {university_info}
        ```
        
        # 输出格式
        
        请直接输出完整改写后的个人陈述，无需添加任何额外说明、标题或分析。改写后的PS应保持适当长度（通常500-1000词），语言正式但富有个性，段落结构清晰。
        """
        
        return prompt
    
    def _call_openrouter_api(self, prompt: str) -> str:
        """调用OpenRouter API使用选定的模型生成改写后的PS"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://ps-assistant.streamlit.app", 
            "X-Title": "PS Assistant Tool"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000
        }
        
        with st.spinner(f"使用 {self.model_name} 完成PS改写..."):
            try:
                response = requests.post(self.api_url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return content
                else:
                    st.error(f"OpenRouter API 错误 ({self.model_name}): {response.status_code} - {response.text}")
                    return self._get_mock_rewrite()
            except Exception as e:
                st.error(f"OpenRouter API 调用错误: {str(e)}")
                return self._get_mock_rewrite()
    
    def _get_mock_rewrite(self) -> str:
        """
        获取模拟改写内容作为后备选项。
        
        Returns:
            模拟的改写后PS
        """
        mock_rewrite = """
        My journey into the realm of computer vision began not with lines of code, but with a moment of wonder. Standing before a medical imaging display during a hospital visit with my ailing grandfather, I watched as radiologists discussed the subtle patterns in his lung scans. The thought struck me then: what if machines could see these patterns with greater precision than human eyes? This question has guided my academic and research path ever since, leading me now to apply for the Computer Vision MSc program at Cambridge University.

        My foundation in computational thinking was laid at Tsinghua University, where I pursued my undergraduate degree in Computer Science. Though my transcript reveals strong performance across the curriculum, it was three courses that truly shaped my research interests. In Advanced Algorithms (98%), I developed a fascination with efficiency in computational problems. Machine Learning (95%) introduced me to the principles that would later become central to my research work. But it was Computer Vision (97%) that crystallized my passion, challenging me to implement a facial recognition system that worked robustly under varying lighting conditions – a project that won departmental recognition and fueled my curiosity about visual computing problems.

        This academic preparation provided the scaffolding for my most significant research experience: working as a research assistant in Professor Zhang's Medical Imaging Laboratory. When tasked with improving segmentation accuracy in brain MRI scans, I faced a challenge that existing algorithms handled poorly – the indistinct boundaries between certain brain tissues. Rather than simply applying established techniques, I proposed a novel approach combining convolutional neural networks with attention mechanisms that could better capture contextual relationships in the images. This initiative required me to independently study advanced deep learning architectures beyond our curriculum and collaborate with medical professionals to understand their practical needs.

        The resulting algorithm achieved a 23% improvement in segmentation accuracy, particularly in areas with low contrast. More importantly, the work contributed to a paper published at CVPR 2022, where I was listed as second author. The experience taught me not only technical skills but also the importance of interdisciplinary collaboration and perseverance when confronting seemingly intractable problems. This research journey reinforced my belief in computer vision's potential to transform healthcare – a belief that directly aligns with Cambridge's Medical Image Analysis Group's pioneering work.

        To complement my academic research, I sought practical experience through a six-month internship at XYZ Tech, where I worked on their natural language processing platform. This experience broadened my understanding of AI applications beyond vision, but also revealed interesting parallels between language and visual pattern recognition. By implementing a sentiment analysis system that incorporated visual cues from user-submitted images, I bridged these domains and delivered a more nuanced analysis tool that the company has since incorporated into their production system.

        Cambridge University's Computer Vision program particularly appeals to me because of its unique combination of theoretical depth and practical application. Professor Johnson's research on uncertainty estimation in medical image analysis directly connects with my previous work, while Dr. Williams' exploration of vision-language models represents the direction I hope to pursue in my future research. The program's emphasis on industry collaboration also provides the perfect environment to develop solutions that bridge academic innovation and real-world impact – a balance I experienced firsthand during my internship.

        Beyond the classroom and laboratory, I have cultivated skills that would contribute to Cambridge's dynamic research community. Through leading our university's AI Student Association (150+ members), I've developed abilities in communicating complex technical concepts to diverse audiences and coordinating collaborative projects – skills I would bring to research group discussions and interdisciplinary initiatives. My experience organizing our department's annual AI symposium demonstrated my capacity to build connections across specialties and foster academic dialogue.

        My immediate goal upon completing the MSc program would be to pursue doctoral research in computer vision, with a focus on medical applications or multimodal learning systems. Ultimately, I aim to lead research that creates vision systems that not only see but understand, whether in healthcare settings, assistive technologies, or human-computer interaction. Cambridge's blend of theoretical rigor and practical innovation provides the ideal foundation for this trajectory.

        The path from that hospital room where I first contemplated the possibilities of machine vision to potentially joining Cambridge's storied research community represents both a personal journey and an intellectual evolution. I am prepared to contribute my technical skills, collaborative spirit, and persistent curiosity to your program, and to help advance the field that has fascinated me since that pivotal moment years ago.
        """
        
        return mock_rewrite 