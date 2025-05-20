import os
import streamlit as st
import asyncio
import requests
import json
import traceback
from typing import Dict, Any, List, Optional, Callable
from .serper_client import SerperClient

class PSInfoCollectorDeep:
    """
    Agent 1.2: 针对1.1报告缺失项，抓取指定URL补全信息，只补全缺失项，不修改已确认内容。
    """
    def __init__(self, model_name=None, max_urls_to_process=3):
        """
        初始化Agent 1.2
        
        Args:
            model_name: 要使用的AI模型名称
            max_urls_to_process: 最多处理的补充URL数量（默认为3）
        """
        self.model_name = model_name if model_name else "anthropic/claude-3-7-sonnet"
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.serper_client = SerperClient()
        # 加载提示词配置
        prompts = st.session_state.get("prompts")
        if not prompts:
            from config.prompts import DEFAULT_PROMPTS
            prompts = DEFAULT_PROMPTS
        self.prompts = prompts.get("ps_info_collector_deep", {})
        # 最大处理URL数量限制
        self.max_urls_to_process = max_urls_to_process

    async def complete_missing_info(self, main_report: str, missing_fields: List[str], urls_for_deep: List[str], university: str, major: str, custom_requirements: str = "", progress_callback: Optional[Callable[[int, str], None]] = None) -> str:
        """
        针对缺失项，抓取指定URL补全，合成最终报告。
        
        Args:
            main_report: 主报告内容
            missing_fields: 缺失项列表
            urls_for_deep: 需要抓取的补充URL列表
            university: 大学名称
            major: 专业名称
            custom_requirements: 自定义需求
            progress_callback: 可选的进度回调函数，用于更新UI进度条
        """
        deep_container = st.container()
        
        with deep_container:
            st.write(f"## 深度补全 {university} {major} 专业缺失信息")
            
            if not missing_fields or not urls_for_deep:
                st.success("无需补全信息，主报告已完整")
                if progress_callback:
                    progress_callback(100, "Agent 1.2：无需补全信息")
                return main_report
            
            # 限制处理的URL数量
            urls_for_deep = urls_for_deep[:self.max_urls_to_process]
            
            st.info(f"需要补全的信息: {', '.join(missing_fields)}")
            st.info(f"将抓取 {len(urls_for_deep)} 个补充页面")
            
            if progress_callback:
                progress_callback(15, "Agent 1.2：准备抓取补充页面...")
        
        try:
            # 抓取所有补充页面内容
            scraped_contents = {}
            for i, url in enumerate(urls_for_deep):
                with deep_container:
                    st.write(f"正在抓取第 {i+1}/{len(urls_for_deep)} 个页面: {url}")
                
                # 更新进度条，抓取部分占40%的进度
                if progress_callback:
                    progress_percent = 15 + int(((i+1) / len(urls_for_deep)) * 40)
                    progress_callback(progress_percent, f"Agent 1.2：抓取第 {i+1}/{len(urls_for_deep)} 个页面...")
                
                try:
                    # 使用jina_reader_scrape替代scrape_url
                    content = await self.serper_client.jina_reader_scrape(url, main_container=deep_container)
                except Exception as e:
                    # 如果Jina Reader失败，尝试直接抓取
                    with deep_container:
                        st.warning(f"Jina Reader抓取失败: {str(e)}，尝试直接抓取")
                    try:
                        content = await self.serper_client.direct_scrape(url, main_container=deep_container)
                    except Exception as direct_error:
                        with deep_container:
                            st.error(f"所有抓取方法均失败: {str(direct_error)}")
                        content = ""
                
                if content:
                    scraped_contents[url] = content
                    with deep_container:
                        st.success(f"成功抓取页面: {url}")
                else:
                    with deep_container:
                        st.warning(f"页面 {url} 内容为空")
            
            # 如果没有成功抓取任何内容，直接返回原报告
            if not scraped_contents:
                with deep_container:
                    st.error("所有补充页面抓取失败，将使用原报告")
                if progress_callback:
                    progress_callback(100, "Agent 1.2：抓取失败，使用原报告")
                return main_report
            
            # 使用LLM分析抓取内容，针对缺失项生成补充内容
            if progress_callback:
                progress_callback(60, "Agent 1.2：分析补充页面内容...")
                
            supplementary_info = await self._analyze_scraped_content(
                main_report=main_report,
                missing_fields=missing_fields,
                scraped_contents=scraped_contents,
                university=university,
                major=major,
                deep_container=deep_container
            )
            
            # 合成最终报告
            if progress_callback:
                progress_callback(85, "Agent 1.2：合成最终报告...")
                
            final_report = self._merge_report(main_report, supplementary_info)
            
            with deep_container:
                st.success("深度补全完成，已生成最终报告")
                
                # 显示更新了哪些部分
                updated_sections = list(supplementary_info.keys())
                if updated_sections:
                    st.info(f"已更新的部分: {', '.join(updated_sections)}")
                else:
                    st.warning("未能补全任何信息")
                
                # 显示最终报告预览
                with st.expander("最终报告预览", expanded=False):
                    st.markdown(final_report)
            
            if progress_callback:
                progress_callback(95, "Agent 1.2：准备完成...")
            
            return final_report
            
        except Exception as e:
            with deep_container:
                st.error(f"补全过程中出错: {str(e)}")
                st.code(traceback.format_exc())
            
            # 出错时返回原报告
            if progress_callback:
                progress_callback(100, "Agent 1.2：执行出错，使用原报告")
            return main_report

    async def _analyze_scraped_content(self, main_report: str, missing_fields: List[str], scraped_contents: Dict[str, str], university: str, major: str, deep_container=None) -> Dict[str, str]:
        """
        使用LLM分析抓取的内容，为缺失项生成补充信息。
        返回格式: {"字段名": "补充内容", ...}
        """
        # 从配置中读取提示词
        role = self.prompts.get("role", "你是一位院校信息深度补全专家，擅长从多个网页中提取特定信息，整合补充到初步报告中。")
        task = self.prompts.get("task", "分析抓取的补充页面，提取主报告中缺失的信息，生成可直接合并的补充内容。")
        output_format = self.prompts.get("output", "为每个缺失项生成一个单独的补充内容块，格式清晰规范。")
        
        # 合并所有抓取内容（不限制长度）
        all_content = ""
        for url, content in scraped_contents.items():
            # 不再限制内容长度
            all_content += f"\n--- 页面: {url} ---\n{content}\n\n"
        
        # 从主报告中提取已有结构
        report_structure = self._extract_report_structure(main_report)
        
        # 构建提示词
        prompt = f"""
        # 角色
        {role}
        
        # 任务
        {task}
        
        ## 背景
        你需要从补充页面内容中，提取主报告缺失的信息，生成补充内容。
        
        大学: {university}
        专业: {major}
        
        ## 主报告结构
        {report_structure}
        
        ## 需要补全的部分
        {', '.join(missing_fields)}
        
        ## 补充页面内容
        {all_content}
        
        # 输出格式
        {output_format}
        
        请仅为主报告中标记为"[缺失，需补全]"的部分生成补充内容。
        不要修改已有内容，只补充缺失的部分。
        
        对于每个缺失部分，请输出:
        ```
        FIELD: 字段名称(如"项目概览")
        CONTENT:
        补充的具体内容，使用markdown格式
        ```
        
        如果补充页面没有足够信息填充某个缺失部分，请输出:
        ```
        FIELD: 字段名称
        CONTENT:
        无法从补充页面找到相关信息。建议访问大学官方网站获取最新信息。
        ```
        
        请确保:
        1. 内容准确、简洁、专业
        2. 只针对缺失部分生成内容
        3. 格式规范，结构清晰
        4. 内容符合大学专业信息的标准
        """
        
        if deep_container:
            with deep_container:
                with st.expander("LLM提取提示词", expanded=False):
                    st.code(prompt)
        
        try:
            # 调用OpenRouter API
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
            
            with deep_container:
                st.info(f"正在使用 {self.model_name} 分析补充内容...")
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=90)
            
            if response.status_code != 200:
                with deep_container:
                    st.error(f"API返回错误: {response.status_code} - {response.text}")
                return {}
            
            result = response.json()
            
            # 提取LLM回复内容
            content = result["choices"][0]["message"]["content"]
            
            # 解析补充内容
            supplementary_info = {}
            if "FIELD:" in content:
                sections = content.split("FIELD:")[1:]  # 切分各个字段
                for section in sections:
                    if "CONTENT:" in section:
                        field_parts = section.split("CONTENT:", 1)
                        field_name = field_parts[0].strip()
                        field_content = field_parts[1].strip()
                        
                        # 去除字段名中可能的引号和多余字符
                        field_name = field_name.strip('"\'`')
                        
                        supplementary_info[field_name] = field_content
            
            return supplementary_info
            
        except Exception as e:
            if deep_container:
                with deep_container:
                    st.error(f"分析补充内容时出错: {str(e)}")
            return {}

    def _extract_report_structure(self, report: str) -> str:
        """从主报告中提取结构，标记哪些部分需要补全"""
        structure = []
        lines = report.split("\n")
        current_section = None
        
        for line in lines:
            if line.startswith("## "):
                section = line[3:].strip()
                status = "[缺失]" if "[缺失，需补全]" in report.split(line)[1].split("##")[0] else "[已有]"
                structure.append(f"{section}: {status}")
        
        return "\n".join(structure)

    def _merge_report(self, main_report: str, supplementary_info: Dict[str, str]) -> str:
        """
        合并主报告和补充信息，只替换[缺失，需补全]部分
        """
        final_report = main_report
        
        for field, content in supplementary_info.items():
            # 构建替换模式
            target = f"## {field}\n[缺失，需补全]"
            replacement = f"## {field}\n{content}"
            
            # 执行替换
            if target in final_report:
                final_report = final_report.replace(target, replacement)
        
        # 更新"以下部分信息缺失"的提示
        missing_info_marker = "**以下部分信息缺失，建议补全："
        if missing_info_marker in final_report:
            remaining_missing = []
            for field in supplementary_info.keys():
                if f"## {field}\n[缺失，需补全]" not in final_report:
                    remaining_missing.append(field)
            
            if remaining_missing:
                # 更新缺失信息列表
                start_idx = final_report.find(missing_info_marker)
                end_idx = final_report.find("**", start_idx + len(missing_info_marker))
                if end_idx > start_idx:
                    final_report = final_report[:start_idx] + f"{missing_info_marker}{', '.join(remaining_missing)}**" + final_report[end_idx+2:]
            else:
                # 移除整个缺失信息提示
                start_idx = final_report.find(missing_info_marker)
                end_idx = final_report.find("**", start_idx + len(missing_info_marker))
                if end_idx > start_idx:
                    final_report = final_report[:start_idx] + final_report[end_idx+2:]
        
        return final_report 