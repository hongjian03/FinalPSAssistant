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
        "timeout": 25,  # 请求超时时间(秒)
        "max_retries": 2,  # 最大重试次数
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/markdown,text/plain,*/*;q=0.9",
            "Cache-Control": "no-cache"
        }
    },
    
    # 功能控制
    "features": {
        "use_as_primary": True,  # 是否将Jina Reader作为主要抓取方法
        "fallback_to_direct": True  # 失败时是否回退到直接抓取
    }
}

def get_jina_config():
    """返回Jina Reader配置"""
    return JINA_READER_CONFIG 