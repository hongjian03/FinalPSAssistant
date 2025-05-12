import streamlit as st
import logging
import sys
import base64
import io
from typing import Dict, Any, Optional, List
from docx import Document
from PyPDF2 import PdfReader
import time
from threading import Thread
from queue import Queue, Empty
import traceback

logger = logging.getLogger(__name__)

def safe_api_call(func, *args, **kwargs):
    """安全地调用API，处理潜在的错误"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_msg = f"API调用错误: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return {"status": "error", "message": error_msg}

def extract_text_from_docx(file_bytes: bytes) -> str:
    """从Word文档中提取文本"""
    try:
        doc = Document(io.BytesIO(file_bytes))
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        logger.error(f"从Word文档提取文本时出错: {str(e)}")
        return ""

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """从PDF文件中提取文本"""
    try:
        pdf_reader = PdfReader(io.BytesIO(file_bytes))
        text_content = ""
        for page in pdf_reader.pages:
            text_content += page.extract_text() + "\n"
        return text_content
    except Exception as e:
        logger.error(f"从PDF提取文本时出错: {str(e)}")
        return ""

class QueueCallbackHandler:
    """用于LLM流式输出的回调处理器"""
    def __init__(self, queue):
        self.queue = queue
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.queue.put(token)

def run_with_streaming(func, args=None, kwargs=None):
    """运行函数并流式输出结果"""
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}
    
    message_queue = Queue()
    callback_handler = QueueCallbackHandler(message_queue)
    
    # 添加回调处理器
    if "callbacks" not in kwargs:
        kwargs["callbacks"] = []
    kwargs["callbacks"].append(callback_handler)
    
    def token_generator():
        while True:
            try:
                token = message_queue.get(block=False)
                yield token
            except Empty:
                if not thread.is_alive() and message_queue.empty():
                    break
            time.sleep(0.01)
    
    def run_function():
        try:
            result = func(*args, **kwargs)
            thread.result = result
            return result
        except Exception as e:
            error_msg = f"运行出错: {str(e)}"
            message_queue.put(f"\n\n{error_msg}")
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            thread.exception = e
            raise e
    
    # 启动线程
    thread = Thread(target=run_function)
    thread.start()
    
    # 创建流式输出容器
    output_container = st.empty()
    
    # 流式输出
    with output_container:
        full_response = st.write_stream(token_generator())
    
    # 等待线程完成
    thread.join()
    
    # 检查是否有异常
    if hasattr(thread, "exception") and thread.exception:
        raise thread.exception
    
    # 获取结果
    if hasattr(thread, "result"):
        return thread.result, full_response, output_container
    
    return None, full_response, output_container 