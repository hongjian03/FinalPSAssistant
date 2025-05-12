"""
此模块提供了Smithery MCP顺序思考工具的替代实现，使用纯LangChain
"""

import json
import logging
from typing import Dict, Any, Callable, Optional, List
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain.schema import HumanMessage, SystemMessage
from langchain.callbacks.base import BaseCallbackHandler

logger = logging.getLogger(__name__)

class SequentialThinkingTool:
    """
    使用纯LangChain实现的顺序思考工具
    """
    
    def __init__(self, api_key: str, model_name: str = "anthropic/claude-3-haiku-20240307"):
        """
        初始化顺序思考工具
        
        Args:
            api_key: OpenRouter API密钥
            model_name: 使用的模型名称
        """
        self.api_key = api_key
        self.model_name = model_name
        
        self.llm = ChatOpenAI(
            temperature=0.1,
            model=model_name,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
    
    async def run_sequential_thinking(self, task: str, callback_handler: Optional[BaseCallbackHandler] = None) -> str:
        """
        运行顺序思考
        
        Args:
            task: 思考任务
            callback_handler: 回调处理器
        
        Returns:
            思考结果
        """
        system_template = """
        你是一位擅长结构化分析和逐步思考的助手。面对复杂任务，你会按照以下步骤进行思考：
        
        1. 分解问题：将大问题分解为可管理的小步骤
        2. 确定关键信息：识别任务中最重要的信息点
        3. 逻辑推理：分析各个部分之间的关系，形成连贯的思考过程
        4. 综合结论：基于前面的分析得出合理的结论
        5. 最终方案：提出具体、可执行的方案
        
        请保持你的思考过程清晰、条理、逻辑性强，使用分步骤的方式表达你的思考过程。
        避免跳跃性思维，确保每一步逻辑都是前一步的自然延伸。
        """
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", "{task}")
        ])
        
        chain = LLMChain(
            llm=self.llm,
            prompt=prompt,
            verbose=True
        )
        
        result = await chain.arun(
            task=task,
            callbacks=[callback_handler] if callback_handler else None
        )
        
        return result

async def run_sequential_thinking(task: str, api_key: str, callback: Optional[Callable] = None) -> str:
    """
    运行顺序思考的便捷函数
    
    Args:
        task: 思考任务
        api_key: API密钥
        callback: 回调函数
    
    Returns:
        思考结果
    """
    # 创建回调处理器(如果提供了回调函数)
    callback_handler = None
    if callback:
        class TokenCallbackHandler(BaseCallbackHandler):
            def on_llm_new_token(self, token: str, **kwargs) -> None:
                callback(token)
        
        callback_handler = TokenCallbackHandler()
    
    # 运行顺序思考
    tool = SequentialThinkingTool(api_key)
    result = await tool.run_sequential_thinking(task, callback_handler)
    
    return result 