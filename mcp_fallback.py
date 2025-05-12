"""
简化版MCP顺序思考工具的替代实现
"""

import logging
import json
from typing import Dict, Any, Callable, Optional
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.callbacks.base import BaseCallbackHandler

logger = logging.getLogger(__name__)

async def run_sequential_thinking(task: str, api_key: str, callback: Optional[Callable] = None) -> str:
    """
    使用直接LLM调用替代MCP的顺序思考功能的简单实现
    
    Args:
        task: 思考任务
        api_key: API密钥
        callback: 用于流式输出的回调函数
    
    Returns:
        思考结果
    """
    # 创建回调处理器
    callback_handler = None
    if callback:
        class TokenCallbackHandler(BaseCallbackHandler):
            def on_llm_new_token(self, token: str, **kwargs) -> None:
                callback(token)
        
        callback_handler = TokenCallbackHandler()
    
    try:
        # 创建模型
        chat = ChatOpenAI(
            temperature=0.1,
            model="anthropic/claude-3-haiku-20240307",
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        
        # 创建消息
        messages = [
            SystemMessage(content="""
            你是一位擅长结构化分析和逐步思考的助手。面对复杂任务，你会按照以下步骤进行思考：
            
            1. 分解问题：将大问题分解为可管理的小步骤
            2. 确定关键信息：识别任务中最重要的信息点
            3. 逻辑推理：分析各个部分之间的关系，形成连贯的思考过程
            4. 综合结论：基于前面的分析得出合理的结论
            5. 最终方案：提出具体、可执行的方案
            
            请保持你的思考过程清晰、条理、逻辑性强，使用分步骤的方式表达你的思考过程。
            避免跳跃性思维，确保每一步逻辑都是前一步的自然延伸。
            """),
            HumanMessage(content=task)
        ]
        
        # 调用模型
        response = await chat.ainvoke(
            messages,
            callbacks=[callback_handler] if callback_handler else None
        )
        
        return response.content
        
    except Exception as e:
        logger.error(f"替代实现错误: {str(e)}")
        error_message = f"替代实现错误: {str(e)}"
        
        if callback:
            for token in error_message.split():
                callback(token + " ")
        
        return error_message 