import os
import streamlit as st
import asyncio
from typing import Dict, Any, Optional, List
import requests
import json
import traceback
import time
from .serper_client import SerperClient

class PSInfoCollectorMain:
    """
    Agent 1.1: 负责搜索课程介绍主网页，生成初步院校信息报告，标注缺失项和待补全URL。
    """
    def __init__(self, model_name=None):
        self.model_name = model_name if model_name else "anthropic/claude-3-7-sonnet"
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.serper_client = SerperClient()

    async def collect_main_info(self, university: str, major: str, custom_requirements: str = "") -> Dict[str, Any]:
        """
        搜索课程主网页，生成初步报告，返回：{'report': 报告内容, 'missing_fields': 缺失项, 'urls_for_deep': 需补全的URL列表}
        """
        search_container = st.container()
        with search_container:
            st.write(f"## 正在收集 {university} 的 {major} 主网页信息")
            if not hasattr(self.serper_client, 'search_tool_name') or not self.serper_client.search_tool_name:
                try:
                    st.info("正在初始化Web搜索客户端...")
                    await self.serper_client.initialize(search_container)
                except Exception as e:
                    st.error(f"初始化搜索客户端时出错: {str(e)}")
                    return {"report": "初始化搜索失败", "missing_fields": [], "urls_for_deep": []}
        # 搜索主网页
        search_query = f"{university} {major} program official site"
        search_results = await self.serper_client.search_web(search_query, main_container=search_container)
        # 选取主网页URL
        main_url = None
        for result in search_results.get("organic", []):
            if university.lower() in result.get("link", "").lower():
                main_url = result.get("link")
                break
        if not main_url and search_results.get("organic"):
            main_url = search_results["organic"][0].get("link")
        # 用Jina抓主网页内容
        main_content = ""
        if main_url:
            main_content = await self.serper_client.scrape_url(main_url, main_container=search_container)
        # 生成初步报告，分析缺失项
        report, missing_fields = self._analyze_main_content(university, major, main_content, custom_requirements)
        urls_for_deep = []
        if missing_fields:
            # 搜索相关补充页面
            for field in missing_fields:
                # 针对缺失项生成更细致的搜索词
                sub_query = f"{university} {major} {field} site:{university.split()[0].lower()}.edu"
                sub_results = await self.serper_client.search_web(sub_query, main_container=search_container)
                for res in sub_results.get("organic", []):
                    if res.get("link") and res.get("link") not in urls_for_deep:
                        urls_for_deep.append(res.get("link"))
        return {"report": report, "missing_fields": missing_fields, "urls_for_deep": urls_for_deep}

    def _analyze_main_content(self, university, major, content, custom_requirements) -> (str, List[str]):
        """
        分析主网页内容，生成初步报告和缺失项列表。
        """
        # 这里简单模拟，实际可用LLM分析content，提取关键信息，判断缺失项
        required_fields = [
            ("项目概览", ["overview", "introduction", "about"]),
            ("申请要求", ["requirement", "admission", "entry"]),
            ("申请流程", ["application", "process", "deadline"]),
            ("课程设置", ["curriculum", "module", "course structure"]),
            ("相关资源", ["contact", "website", "link"])
        ]
        missing = []
        report = f"# {university} {major}专业信息收集报告\n"
        for field, keywords in required_fields:
            found = False
            for kw in keywords:
                if content and kw in content.lower():
                    found = True
                    break
            if found:
                report += f"\n## {field}\n[已收集]\n"
            else:
                report += f"\n## {field}\n[缺失，需补全]\n"
                missing.append(field)
        report += "\n\n## 信息来源\n"
        report += "主网页: " + (main_url if 'main_url' in locals() else "无")
        if missing:
            report += f"\n\n**以下部分信息缺失，建议补全：{', '.join(missing)}**"
        return report, missing 