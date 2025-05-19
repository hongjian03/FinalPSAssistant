"""
Jina Reader配置文件
用于控制网页抓取的配置
"""

# Jina Reader API配置
JINA_READER_CONFIG = {
    # Jina Reader API基础URL
    "base_url": "https://r.jina.ai/",
    
    # 请求配置
    "request": {
        "timeout": 15,  # 请求超时时间减少到15秒
        "max_retries": 1,  # 减少重试次数以加快响应
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/markdown,text/plain,*/*;q=0.9",
            "Cache-Control": "no-cache"
        }
    },
    
    # 功能控制
    "features": {
        "use_as_primary": True,  # 是否将Jina Reader作为主要抓取方法
        "fallback_to_direct": True,  # 失败时是否回退到直接抓取
        "parallel_processing": True,  # 启用并行处理
        "max_concurrent_requests": 3,  # 最大并发请求数
        "simplified_output": True  # 简化输出，减少处理时间
    }
}

def get_jina_config():
    """返回Jina Reader配置"""
    return JINA_READER_CONFIG 