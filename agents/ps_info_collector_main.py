import os
import streamlit as st
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Callable
import requests
import json
import traceback
import time
from .serper_client import SerperClient
from config.prompts import load_prompts

class PSInfoCollectorMain:
    """
    Agent 1.1: 负责搜索课程介绍主网页，生成初步院校信息报告，标注缺失项和待补全URL。
    """
    def __init__(self, model_name=None):
        self.model_name = model_name if model_name else "anthropic/claude-3-7-sonnet"
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.serper_client = SerperClient()
        # 加载提示词配置
        self.prompts = load_prompts().get("ps_info_collector_main", {})

    async def collect_main_info(self, university: str, major: str, custom_requirements: str = "", progress_callback: Optional[Callable[[int, str], None]] = None) -> Dict[str, Any]:
        """
        搜索课程主网页，生成初步报告，返回：{'report': 报告内容, 'missing_fields': 缺失项, 'urls_for_deep': 需补全的URL列表}
        
        Args:
            university: 目标大学名称
            major: 目标专业名称
            custom_requirements: 自定义需求
            progress_callback: 可选的进度回调函数，用于更新UI进度条
        """
        search_container = st.container()
        with search_container:
            st.write(f"## 正在收集 {university} 的 {major} 主网页信息")
            if not hasattr(self.serper_client, 'search_tool_name') or not self.serper_client.search_tool_name:
                try:
                    st.info("正在初始化Web搜索客户端...")
                    # 更新进度到20%
                    if progress_callback:
                        progress_callback(20, "Agent 1.1：初始化Web搜索客户端...")
                    await self.serper_client.initialize(search_container)
                except Exception as e:
                    st.error(f"初始化搜索客户端时出错: {str(e)}")
                    return {"report": f"初始化搜索失败: {str(e)}", "missing_fields": [], "urls_for_deep": []}
        
        try:
            # 搜索主网页
            with search_container:
                st.info(f"正在搜索 {university} {major} 主网页...")
            # 更新进度到40%
            if progress_callback:
                progress_callback(40, "Agent 1.1：搜索主网页中...")
            search_query = f"{university} {major} program official site"
            search_results = await self.serper_client.search_web(search_query, main_container=search_container)
            
            # 选取主网页URL
            main_url = None
            if search_results and "organic" in search_results and search_results["organic"]:
                for result in search_results.get("organic", []):
                    link = result.get("link", "").lower()
                    # 优先选择官方网站
                    if university.lower() in link and (".edu" in link or ".ac." in link or "university" in link):
                        main_url = result.get("link")
                        with search_container:
                            st.success(f"找到官方主网页: {main_url}")
                        break
                
                # 如果没找到符合条件的，就用第一个结果
                if not main_url:
                    main_url = search_results["organic"][0].get("link")
                    with search_container:
                        st.info(f"未找到官方主网页，使用搜索第一结果: {main_url}")
            else:
                with search_container:
                    st.error("搜索结果为空，无法获取主网页")
                return {"report": "搜索失败，无法获取主网页", "missing_fields": [], "urls_for_deep": []}
            
            # 用Jina抓主网页内容
            with search_container:
                st.info(f"正在抓取网页内容: {main_url}")
            # 更新进度到60%
            if progress_callback:
                progress_callback(60, "Agent 1.1：抓取网页内容中...")
            
            main_content = ""
            if main_url:
                try:
                    # 使用jina_reader_scrape替代scrape_url
                    main_content = await self.serper_client.jina_reader_scrape(main_url, main_container=search_container)
                except Exception as e:
                    # 如果Jina Reader失败，尝试直接抓取
                    with search_container:
                        st.warning(f"Jina Reader抓取失败: {str(e)}，尝试直接抓取")
                    try:
                        main_content = await self.serper_client.direct_scrape(main_url, main_container=search_container)
                    except Exception as direct_error:
                        with search_container:
                            st.error(f"所有抓取方法均失败: {str(direct_error)}")
                
                if not main_content:
                    with search_container:
                        st.warning("主网页内容为空，将使用搜索结果摘要")
                    # 使用搜索结果摘要作为备选
                    for result in search_results.get("organic", [])[:3]:
                        main_content += f"\n标题: {result.get('title', '')}\n摘要: {result.get('snippet', '')}\n链接: {result.get('link', '')}\n"
            
            # 生成初步报告，分析缺失项
            with search_container:
                st.info("正在分析网页内容，生成初步报告...")
            # 更新进度到75%
            if progress_callback:
                progress_callback(75, "Agent 1.1：分析网页内容，生成初步报告...")
            
            report, missing_fields = await self._analyze_main_content(university, major, main_content, main_url, custom_requirements, search_container)
            
            urls_for_deep = []
            if missing_fields:
                with search_container:
                    st.warning(f"信息不完整，缺失项: {', '.join(missing_fields)}")
                    st.info("正在搜索补充信息页面...")
                # 更新进度到85%
                if progress_callback:
                    progress_callback(85, "Agent 1.1：搜索补充信息页面...")
                
                # 为每个缺失项找一个最佳URL
                for field in missing_fields:
                    field_name = field[0] if isinstance(field, tuple) else field
                    with search_container:
                        st.info(f"搜索补充信息: {field_name}")
                    
                    # 针对缺失项生成更细致的搜索词
                    keywords = ""
                    if "项目概览" in field_name:
                        keywords = "program overview introduction about"
                    elif "申请要求" in field_name:
                        keywords = "admission requirements entry criteria"
                    elif "申请流程" in field_name:
                        keywords = "application process deadline procedure"
                    elif "课程设置" in field_name:
                        keywords = "curriculum syllabus course structure modules"
                    elif "相关资源" in field_name:
                        keywords = "resources contact faculty staff"
                    
                    if university.lower().split()[0].endswith('y'):
                        domain = f"{university.lower().split()[0][:-1]}ies"
                    else:
                        domain = f"{university.lower().split()[0]}"
                    
                    sub_query = f"{university} {major} {keywords}"
                    sub_results = await self.serper_client.search_web(sub_query, main_container=search_container)
                    
                    # 为每个缺失项至少找一个URL
                    field_urls = []
                    if sub_results and "organic" in sub_results:
                        for res in sub_results.get("organic", [])[:3]:  # 只考虑前3个结果
                            url = res.get("link")
                            if url and url != main_url and url not in urls_for_deep and url not in field_urls:
                                field_urls.append(url)
                    
                    # 将找到的URL加入总列表
                    urls_for_deep.extend(field_urls)
                
                # 去重并限制URL数量，避免过多抓取
                urls_for_deep = list(set(urls_for_deep))[:5]  # 最多5个补充URL
                
                with search_container:
                    st.success(f"已找到 {len(urls_for_deep)} 个补充页面")
                    if urls_for_deep:
                        with st.expander("补充页面URL", expanded=False):
                            for i, url in enumerate(urls_for_deep):
                                st.write(f"{i+1}. [{url}]({url})")
            else:
                with search_container:
                    st.success("主网页信息完整，无需补充")
            
            # 更新进度到100%
            if progress_callback:
                progress_callback(95, "Agent 1.1：准备完成...")
            
            return {
                "report": report,
                "missing_fields": missing_fields,
                "urls_for_deep": urls_for_deep,
                "main_url": main_url
            }
            
        except Exception as e:
            with search_container:
                st.error(f"处理过程中出错: {str(e)}")
                st.code(traceback.format_exc())
            return {
                "report": f"处理失败: {str(e)}", 
                "missing_fields": [], 
                "urls_for_deep": []
            }

    async def _analyze_main_content(self, university: str, major: str, content: str, main_url: str, custom_requirements: str, container=None) -> Tuple[str, List[str]]:
        """
        使用LLM分析主网页内容，生成初步报告和缺失项列表。
        """
        # 从配置中读取提示词
        role = self.prompts.get("role", "你是一位专业的院校信息收集专家，擅长分析大学官网内容，提取关键项目信息")
        task = self.prompts.get("task", "分析提供的大学项目网页内容，提取核心信息，识别信息缺失点")
        output_format = self.prompts.get("output", "生成一份结构化的初步报告，标记已收集和缺失的信息部分")
        
        # 构建分析提示词
        prompt = f"""
        # 角色
        {role}
        
        # 任务
        {task}
        
        你需要分析以下关于{university}的{major}专业的网页内容，提取核心信息，识别信息缺失：

        目标大学: {university}
        目标专业: {major}
        网页来源: {main_url}
        
        # 网页内容
        {content[:15000]}  # 限制内容长度，避免超出token限制
        
        # 分析要求
        请仔细分析上述内容，提取以下几个方面的信息：
        1. 项目概览：项目名称、学位类型、学制时长、项目特色
        2. 申请要求：学历背景、语言要求(雅思/托福分数)、GPA要求、其他学术标准
        3. 申请流程：申请截止日期、所需材料、申请费用等
        4. 课程设置：核心课程、选修方向、特色课程、实习或研究机会
        5. 相关资源：重要链接、联系方式等
        
        # 输出格式
        {output_format}
        
        请输出：
        1. 一份初步报告，使用markdown格式
        2. 一个清晰标记哪些信息部分是缺失的JSON列表

        对于在网页中能找到的信息，直接提取并整理到报告中对应部分。
        对于网页中缺失的信息，在对应部分加上"[缺失，需补全]"标记。
        
        输出格式要求：
        ```
        REPORT:
        # {university} {major}专业信息收集报告

        ## 项目概览
        [提取的内容或"[缺失，需补全]"]

        ## 申请要求
        [提取的内容或"[缺失，需补全]"]

        ## 申请流程
        [提取的内容或"[缺失，需补全]"]

        ## 课程设置
        [提取的内容或"[缺失，需补全]"]

        ## 相关资源
        [提取的内容或"[缺失，需补全]"]

        ## 信息来源
        [主网页链接]

        MISSING_FIELDS:
        ["项目概览", "申请要求", ...]  // 只包含缺失的部分
        ```
        """
        
        if container:
            with container:
                with st.expander("LLM分析提示词", expanded=False):
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
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=90)
            
            if response.status_code != 200:
                if container:
                    with container:
                        st.error(f"API返回错误: {response.status_code} - {response.text}")
                return f"# {university} {major}专业信息收集报告\n\n无法分析内容: API返回错误{response.status_code}", ["项目概览", "申请要求", "申请流程", "课程设置", "相关资源"]
            
            result = response.json()
            
            # 提取内容
            content = result["choices"][0]["message"]["content"]
            
            # 解析结果，提取报告和缺失项
            try:
                # 分离报告和缺失项
                report_part = ""
                missing_fields = []
                
                if "REPORT:" in content and "MISSING_FIELDS:" in content:
                    report_part = content.split("REPORT:")[1].split("MISSING_FIELDS:")[0].strip()
                    missing_fields_str = content.split("MISSING_FIELDS:")[1].strip()
                    try:
                        missing_fields = json.loads(missing_fields_str)
                    except:
                        # 如果JSON解析失败，尝试简单提取
                        missing_fields = [field.strip(' "[]') for field in missing_fields_str.split(",") if field.strip()]
                else:
                    # 如果没有明确的分隔，使用整个内容作为报告
                    report_part = content
                    # 检测报告中标记为缺失的部分
                    sections = ["项目概览", "申请要求", "申请流程", "课程设置", "相关资源"]
                    for section in sections:
                        if f"## {section}\n[缺失，需补全]" in content:
                            missing_fields.append(section)
                
                # 确保报告有正确的格式
                if not report_part.startswith("# "):
                    report_part = f"# {university} {major}专业信息收集报告\n\n" + report_part
                
                return report_part, missing_fields
                
            except Exception as parse_error:
                if container:
                    with container:
                        st.error(f"解析LLM输出时出错: {str(parse_error)}")
                
                # 使用整个响应作为报告
                return content, ["项目概览", "申请要求", "申请流程", "课程设置", "相关资源"]
                
        except Exception as e:
            if container:
                with container:
                    st.error(f"调用LLM API时出错: {str(e)}")
            
            # 简单方式分析，作为后备
            required_fields = [
                "项目概览", "申请要求", "申请流程", "课程设置", "相关资源"
            ]
            
            # 检查内容中是否有这些字段的关键词
            keywords = {
                "项目概览": ["项目", "专业", "概述", "介绍", "overview", "program", "introduction"],
                "申请要求": ["申请", "要求", "条件", "admission", "requirement", "criteria"],
                "申请流程": ["流程", "截止", "日期", "材料", "application", "deadline", "process"],
                "课程设置": ["课程", "结构", "模块", "学习", "curriculum", "module", "course"],
                "相关资源": ["资源", "联系", "链接", "resource", "contact", "link"]
            }
            
            missing = []
            report = f"# {university} {major}专业信息收集报告\n"
            
            # 根据关键词检查每个字段是否存在
            for field in required_fields:
                found = False
                if content:
                    for kw in keywords[field]:
                        if kw in content.lower():
                            found = True
                            break
                
                if found:
                    report += f"\n## {field}\n内容需提取\n"
                else:
                    report += f"\n## {field}\n[缺失，需补全]\n"
                    missing.append(field)
            
            report += f"\n\n## 信息来源\n主网页: {main_url}"
            
            if missing:
                report += f"\n\n**以下部分信息缺失，建议补全：{', '.join(missing)}**"
            
            return report, missing 