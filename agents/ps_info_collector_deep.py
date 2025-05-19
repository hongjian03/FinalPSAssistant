import os
import streamlit as st
import asyncio
from typing import Dict, Any, List
from .serper_client import SerperClient

class PSInfoCollectorDeep:
    """
    Agent 1.2: 针对1.1报告缺失项，抓取指定URL补全信息，只补全缺失项，不修改已确认内容。
    """
    def __init__(self):
        self.serper_client = SerperClient()

    async def complete_missing_info(self, main_report: str, missing_fields: List[str], urls_for_deep: List[str], university: str, major: str, custom_requirements: str = "") -> str:
        """
        针对缺失项，抓取指定URL补全，合成最终报告。
        """
        deep_container = st.container()
        supplement = {}
        # 针对每个缺失项，遍历URL抓取内容
        for field in missing_fields:
            for url in urls_for_deep:
                content = await self.serper_client.scrape_url(url, main_container=deep_container)
                if self._field_in_content(field, content):
                    supplement[field] = content
                    break
        # 合成最终报告
        final_report = self._merge_report(main_report, supplement)
        return final_report

    def _field_in_content(self, field, content):
        # 简单判断，实际可用LLM分析
        if not content:
            return False
        return field[:2] in content  # 例如"项目"、"申请"等

    def _merge_report(self, main_report: str, supplement: Dict[str, str]) -> str:
        # 只替换[缺失，需补全]部分
        for field, value in supplement.items():
            main_report = main_report.replace(f"## {field}\n[缺失，需补全]", f"## {field}\n{value}")
        return main_report 