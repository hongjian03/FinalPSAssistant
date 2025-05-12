import os
import sys
import logging

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 强制替换 sqlite3 - 为了确保streamlit cloud上正常工作
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import streamlit as st
import json
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.chains import SequentialChain, LLMChain
from typing import Dict, Any, List
import io
import base64
from PyPDF2 import PdfReader
from PIL import Image
import fitz  # PyMuPDF
import requests
import re
from langchain_community.tools.serper_search import SerperSearchResults
from langchain_core.tools import Tool
from langchain.agents import create_structured_chat_agent
import asyncio
import nest_asyncio
from queue import Queue
from threading import Thread
import time
from queue import Empty
from langchain.callbacks.base import BaseCallbackHandler
from markitdown import MarkItDown
from docx import Document

# 导入 MCP 模块
try:
    import mcp
    from mcp.client.streamable_http import streamablehttp_client
    logger.info("MCP 模块已成功导入")
    MCP_AVAILABLE = True
except ImportError:
    logger.error("MCP 模块导入失败，请安装 MCP: pip install mcp")
    st.error("缺少 MCP 模块，某些功能可能不可用。请运行 pip install mcp 安装所需依赖。")
    MCP_AVAILABLE = False

# 导入替代实现
if not MCP_AVAILABLE:
    try:
        from smithery_fallback import run_sequential_thinking
        logger.info("已加载 Smithery 替代实现")
    except ImportError:
        logger.warning("无法导入 Smithery 替代实现，某些功能可能不可用")

# 应用 nest_asyncio 避免在Streamlit中运行asyncio时的问题
nest_asyncio.apply()

# 记录程序启动
logger.info("程序开始运行")

# 只在第一次运行时替换 sqlite3
if 'sqlite_setup_done' not in st.session_state:
    try:
        logger.info("尝试设置 SQLite")
        st.session_state.sqlite_setup_done = True
        logger.info("SQLite 设置成功")
    except Exception as e:
        logger.error(f"SQLite 设置错误: {str(e)}")
        st.session_state.sqlite_setup_done = True


class PromptTemplates:
    def __init__(self):
        # 定义示例数据作为字符串
        self.default_templates = {
            'school_research_role': """
            # 角色
            你是一位专业的院校研究专家，擅长分析各国大学的专业项目，包括课程设置、研究方向、申请要求和就业前景等信息。
            你的职责是通过搜索引擎收集特定学校和专业的最新信息，并将这些信息整理成简洁明了的报告，帮助学生更好地了解目标院校和专业。
            """,
            
            'school_research_task': """
            # 任务
            1. 基于用户提供的学校名称和专业名称，使用搜索工具收集相关信息
            2. 重点关注以下方面：专业介绍、课程设置、研究方向、申请要求、就业前景
            3. 对收集到的信息进行整理和分析，生成结构清晰的院校信息汇总报告
            4. 确保信息的准确性和时效性，尽可能引用官方来源
            5. 如有必要，可以进行多次搜索以获取更全面的信息
            """,
            
            'school_research_output': """
            # 输出格式
            ## 院校信息汇总报告：{学校名称} - {专业名称}

            ### 专业概览
            - 学位类型：[学士/硕士/博士]
            - 学制长度：[X年]
            - 专业定位：[简要描述专业的学术定位和特点]
            - 所属院系：[院系名称]

            ### 课程设置
            - 核心课程：[列出3-5门核心课程]
            - 选修方向：[列出主要选修方向]
            - 教学特色：[描述教学方法、特色项目等]

            ### 研究方向
            - 主要研究领域：[列出该专业的主要研究方向]
            - 研究中心/实验室：[列出相关研究中心或实验室]
            - 学术资源：[描述可用的学术资源和机会]

            ### 申请要求
            - 学术背景要求：[GPA、学位背景等]
            - 语言要求：[TOEFL/IELTS分数要求]
            - 其他要求：[GRE/GMAT、推荐信、个人陈述等]
            - 申请截止日期：[主要申请日期]

            ### 就业前景
            - 毕业去向：[主要就业方向]
            - 合作企业/机构：[学校的企业合作伙伴]
            - 校友网络：[校友分布和影响力]

            ### 总结评估
            [对该专业的综合评价，包括优势、特色和适合人群]

            ### 信息来源
            [列出信息来源的链接]
            """,
            
            'support_analysis_role': """
            # 角色
            你是一位专业的文档分析专家，擅长从支持文件（如成绩单、简历、推荐信等）中提取和分析关键信息，并将其整合为有用的分析报告。
            你的职责是帮助用户理解支持文件中的重要内容，特别是那些对个人陈述(PS)写作有价值的信息。
            """,
            
            'support_analysis_task': """
            # 任务
            1. 仔细分析用户上传的支持文件（可能是成绩单、简历、推荐信等）
            2. 从文件中提取关键信息，包括但不限于：学术背景、专业课程、研究经历、实习经验、技能、成就等
            3. 将提取的信息组织成结构化的报告，突出对PS写作有价值的内容
            4. 分析内容与用户的目标专业和学校的相关性
            5. 提供对这些信息的专业解读，指出哪些内容适合在PS中强调
            """,
            
            'support_analysis_output': """
            # 输出格式
            ## 支持文件分析报告

            ### 文件类型识别
            [识别上传的是什么类型的支持文件，如成绩单、简历、推荐信等]

            ### 关键信息提取
            #### 学术背景
            - 学位/专业：[提取的信息]
            - GPA/成绩：[提取的信息]
            - 重要课程：[提取的信息]
            - 学术成就：[提取的信息]

            #### 研究经历
            - 研究项目：[提取的信息]
            - 研究技能：[提取的信息]
            - 研究成果：[提取的信息]

            #### 实习与工作经验
            - 相关实习：[提取的信息]
            - 工作经历：[提取的信息]
            - 职责与成就：[提取的信息]

            #### 技能与专长
            - 技术技能：[提取的信息]
            - 语言能力：[提取的信息]
            - 其他专长：[提取的信息]

            #### 其他亮点
            - 奖项荣誉：[提取的信息]
            - 课外活动：[提取的信息]
            - 志愿服务：[提取的信息]

            ### PS写作建议
            [基于分析的文件内容，提供3-5点对PS写作的建议，指出哪些内容适合重点强调]

            ### 与目标专业的契合点
            [分析提取的信息与用户目标专业的相关性和契合度]
            """,
            
            'ps_strategy_role': """
            # 角色
            你是一位专业的个人陈述(PS)策略顾问，擅长分析初稿内容并提供改进建议。你有丰富的留学申请文书指导经验，了解各国高校和不同专业的PS写作特点和要求。
            """,
            
            'ps_strategy_task': """
            # 任务
            1. 仔细阅读用户提供的PS初稿内容
            2. 分析支持文件分析报告中的关键信息
            3. 评估初稿的优缺点，包括内容、结构、叙事逻辑和语言表达
            4. 基于目标学校和专业的特点，提出具体的改进策略
            5. 识别初稿中的关键亮点和需要加强的弱点
            6. 提供详细的改写指导，包括内容重组、叙事深化和表达优化
            7. 确保改写策略符合目标专业和学校的特定要求
            """,
            
            'ps_strategy_output': """
            # 输出格式
            ## PS改写策略报告

            ### 初稿总体评估
            - 整体印象：[对初稿的总体评价]
            - 优势：[列出3-5个初稿的主要优势]
            - 不足：[列出3-5个需要改进的方面]
            - 与目标专业的契合度：[评估初稿内容与目标专业的契合程度]

            ### 内容策略
            #### 专业动机
            - 现状：[初稿中专业动机部分的现状]
            - 建议：[如何强化或改进专业动机的表达]
            - 可利用的支持材料：[从支持文件分析中可利用的相关内容]

            #### 学术背景
            - 现状：[初稿中学术背景部分的现状]
            - 建议：[如何更有效地展示学术背景]
            - 可利用的支持材料：[从支持文件分析中可利用的相关内容]

            #### 研究经历
            - 现状：[初稿中研究经历部分的现状]
            - 建议：[如何深化研究经历的描述]
            - 可利用的支持材料：[从支持文件分析中可利用的相关内容]

            #### 实习与实践
            - 现状：[初稿中实习与实践部分的现状]
            - 建议：[如何优化实习与实践的叙述]
            - 可利用的支持材料：[从支持文件分析中可利用的相关内容]

            #### 未来规划
            - 现状：[初稿中未来规划部分的现状]
            - 建议：[如何使未来规划更具说服力]
            - 与目标专业的联系：[如何更好地将未来规划与目标专业联系起来]

            ### 结构与逻辑策略
            - 段落组织：[对当前段落结构的分析和改进建议]
            - 逻辑连贯性：[如何提高内容之间的连贯性]
            - 开头与结尾：[如何优化开头和结尾]

            ### 表达策略
            - 语言风格：[语言风格的评价和建议]
            - 具体性：[如何使表达更具体、更生动]
            - 学术性：[如何使表达更加学术性]

            ### 改写重点
            [列出3-5个改写的重点优先事项]

            ### 整体改写方向
            [总结性地提出整体改写的方向和目标]
            """,
            
            'content_creation_role': """
            # 角色
            你是一位专业的个人陈述(PS)创作专家，擅长根据策略指导和分析报告创作精彩的PS内容。你具有卓越的写作技巧和丰富的留学申请文书创作经验，了解如何将申请者的背景、经历和目标转化为引人入胜的叙述。
            """,
            
            'content_creation_task': """
            # 任务
            1. 根据PS改写策略报告中的指导，创作改进版的个人陈述内容
            2. 遵循策略报告中提出的内容、结构和表达建议
            3. 整合支持文件分析中的关键信息，强化PS的说服力
            4. 确保内容与目标专业和学校高度契合
            5. 保持申请者原有的个人风格，同时提升表达质量
            6. 创作流畅、连贯、引人入胜的叙述
            7. 突出申请者的独特优势和特点
            8. 确保内容真实可信，避免过度修饰或夸张
            """,
            
            'content_creation_output': """
            # 输出格式
            ## 个人陈述（{目标学校} - {目标专业}）

            [创作完整的个人陈述内容，根据PS策略报告的建议进行组织。不需要包含标题或分段标识，直接呈现流畅的PS正文内容。]
            """,
            
            'transcript_role': """
            # 角色
            你是专业的成绩单分析师，擅长从成绩单中提取关键信息并以表格形式展示成绩。
            """,
            
            'transcript_task': """

            """,
            
            'transcript_output': """

            """,
            
            'consultant_role2': """
            # 角色
            作为一个专业的个人陈述创作助手，我的核心能力是:
            1. 将分散的素材整合成连贯、有深度的个人故事
            2. 精准识别申请者与目标专业的契合点
            3. 将学术成就与个人经历有机结合，突出申请者优势
            4. 将中文素材转换为符合英语思维的表达方式
            5. 遵循STAR原则构建有说服力的经历描述
            6. 将抽象的兴趣与具体的学术、实践经历联系起来
            7. 确保每个段落既独立成章又相互关联，形成连贯叙事
            8. 从用户提供的素材、成绩单和申请方向中准确提取最有价值的信息
            9. 严格遵守素材真实性，不虚构或夸大内容
            10. 通过逻辑连接和自然过渡构建流畅的叙事

            在每次创作中，我都专注于让申请者的专业热情、学术基础、相关经历和未来规划形成一个清晰、连贯且有说服力的整体。

            """,
            
            'output_format2': """
            输出格式：
            ## 个人陈述（专业大类：[专业名称]）

            ### 专业兴趣塑造
            > [选择一个最合适的角度，注重逻辑性，深入展开细节描述和观点叙述，减少素材堆砌，注重描述深度]

            ### 学术基础展示
            > [结合素材表和成绩单，突出3-4个与申请专业相关的学术亮点，包括具体课程内容或作业项目的简述举例]

            ### 研究经历深化
            > [遵循STAR原则和总分总结构详细描述最相关的一个研究经历，与专业方向相联系]

            ### 实习经历深化
            > [遵循STAR原则和总分总结构详细描述最相关的一个实习经历，与专业方向相联系]

            ### 未来规划提升
            > [分为三个层次展开：
            > - 学术目标
            > - 职业短期规划
            > - 职业长期规划
            > 确保每个层次有明确目标和实现路径，并建立层次间的递进关系]

            ### 为何选择目标学校和目标项目
            > [按照顺序，从以下方面进行通用性阐述：
            > 1. 目标国家优势（禁止提及具体国家，提及国家时，用"目标国家"代替）
            > 2. 目标院校资源优势及学术环境
            > 3. 目标项目与研究方向的匹配度
            > 从而展示申请者选择的合理性]

            ##3 结语
            > [简洁有力地总结申请者的优势、志向和对该专业的热情]


            结构要求：
            1. 第一段(专业兴趣塑造)：
            - 选择最合适的一个角度(过去经历/时事新闻/科研成果)作为核心线索展开
            - 建立清晰的思维发展路径：从初始接触→深入探索→认识深化→专业方向确定
            - 使用具体例子支撑抽象概念，通过细节展示思考深度
            - 每句话应与前句有明确的逻辑关联，使用恰当的过渡词展示思维连贯性
            - 避免简单罗列多个素材点，而是深入发展单一主线
            - 结尾处应与未来学习方向自然衔接，为后续段落铺垫
            2.第二段(学术基础展示)：结合素材表+成绩单，找到3-4个与申请专业相关的学术亮点(包括但不限于与申请专业相关的专业知识、学术能力和专业技能)，进行阐述，并有具体课程内容或作业项目的简述举例3. 每个段落应采用"总-分-总"结构，第一句话承上启下，最后一句话总结该经历与目标专业的联系
            3.控制整体字数，每个段落控制在150-200字左右，确保文书紧凑精炼
            4.增强句子之间的逻辑连接：
            - 确保每个新句子包含前一句子的关键词或概念
            - 使用指代词明确引用前文内容
            - 恰当使用过渡词和连接词
            - 建立清晰的因果关系，使用"因此"、"由此"、"正是"等词语明确前后句关系
            - 采用递进结构展示思想发展，从初始观察到深入思考，再到形成核心观点
            - 添加过渡句确保各点之间自然衔接，如"这种认识引导我..."、"通过这一探索..."
            - 确保每个段落形成完整的思想发展脉络，展现认知的深化过程
            - 避免单纯并列不相关信息，而是通过逻辑词建立内在联系



            """,
            
            'consultant_task2': """
            任务描述:
            1. 基于提供的素材表、成绩单(如有)、申请方向及个性化需求(如有)，为指定专业方向创作完整的个人陈述初稿
            2. 充分利用用户提供的四类信息(素材表、成绩单、申请方向、个性化需求)，进行深度分析和内容创作
            3. 遵循STAR原则(情境-任务-行动-结果)呈现研究经历和实习经历，且只选择素材中最相关的一个经历
            4. 突出申请者与申请方向的契合点
            5. 在正文中直接使用【补充：】标记所有非素材表中的内容
            6. 确保段落间有自然过渡，保持文章整体连贯性
            7. 所有段落中的事实内容必须严格遵循素材表，不添加未在素材表中出现的内容
            8. 优化表述逻辑，确保内容之间的连贯性和自然过渡
            9. 核心的经历优先放入经历段落，避免一个经历多次使用，除非用户特别要求

            写作说明：
            ● 确保文章结构清晰，段落之间有良好的逻辑过渡
            ● 所有非素材表中需要补充的内容必须保留中文并用【补充：】标记
            ● 内容均使用纯中文表达
            ● 技术术语和专业概念则使用准确的英文表达
            ● 保持文章的整体连贯性和专业性
            ● 重点突出申请者的优势，并与申请方向建立明确联系
            ● 内容应真实可信，避免虚构经历或夸大成就
            ● 每个主题部分应当是一个连贯的整体段落，而非多个松散段落
            ● 在分析成绩单时，关注与申请专业相关的课程表现，但不要体现任何分数
            ● 确保内容精练，避免不必要的重复和冗余表达
            ● 结语应简明扼要地总结全文，展现申请者的决心和愿景
            ● 避免出现"突然感兴趣"或"因此更感兴趣"等生硬转折，确保兴趣发展有合理的渐进过程
            ● 各段落间应有内在的逻辑联系，而非简单罗列，每段内容应自然引出下一段内容
            ● 确保经历与专业兴趣间的关联性具有说服力，展示清晰的思维发展路径
            ● 必须充分理解和执行用户的个性化需求(如有)
            ● 确保整体叙事具有内在一致性和合理的心理动机发展
            ● 核心经历应只出现在对应的经历段落中，避免重复使用同一经历，除非用户特别要求



            """,
            "material_simplifier_role": """
            该指令用于将个人陈述调查问卷中的零散信息转化为结构化的要点列表，以便于撰写留学申请材料。
            这一过程需要确保所有信息被正确归类，同时彻底移除任何学校和专业具体信息，以保持申请材料的通用性与适用性。
            留学申请中，个人陈述是展示申请者背景、经历、专业兴趣以及未来规划的关键材料，但原始调查问卷通常包含大量未经整理的信息，且可能包含过于具体的学校和专业信息，需要进行专业化的整理与归类。


            """,
            "material_simplifier_task": """
            1. 处理流程：
                - 仔细阅读提供的个人陈述调查问卷素材
                - 将素材中的信息按照统一格式提取
                - 删除学校和专业名称的同时保留项目实质内容
                - 按照个人陈述素材表的七大框架进行分类整理
                - 使用规定格式输出最终结果

            2. 关键要求：
                - 删除标识性信息但保留内容：
                    * 删除大学名称、缩写和别称，但保留在该校完成的项目、研究或经历的具体内容
                    * 删除实验室、研究中心的具体名称，但保留其研究方向和内容
                    * 删除特定学位项目名称和编号，但保留课程内容
                    * 删除教授、导师的姓名和头衔，但保留与其合作的项目内容
                
                - 保留课程和经历细节：
                    * 课程内容、项目描述、技能培养等细节必须完整保留
                    * 课程保留具体课程编号及课程名称
                    * 项目经历的技术细节、方法论、工具使用等信息必须保留
                    * 保留所有成果数据、获奖情况（移除具体学校名称）
                    * 即使项目是在特定学校完成的，也必须保留项目的全部实质内容
                
                - 信息分类必须精确无误：
                    * 每条信息必须且只能归入一个类别
                    * 严格遵循"七大框架"的分类标准
                    * 不允许创建新类别或合并现有类别
                    * 不允许同一信息跨类别重复出现
                
                - 经历要点格式要求：
                    * 研究、实习和实践经历必须按照七个子要点分行显示
                    * 如某些要素缺失，保持顺序不变并跳过该要素
                    * 项目内容描述必须包含项目所经历的完整步骤和流程
                    * 个人职责必须详细列出所有责任、遇到的困难及解决方案

            """,

            "material_simplifier_output":"""
            输出标题为"个人陈述素材整理报告"，仅包含以下七个部分：

            1. 专业兴趣塑造
            - 仅包含专业兴趣形成过程的要点列表
            - 每个要点以单个短横线"-"开头
            - 保留所有激发兴趣的细节经历和体验

            2. 学术基础展示
            - 仅包含课程学习、学术项目、教育背景的要点列表
            - 每个要点以单个短横线"-"开头
            - 保留课程内容、学习成果和技能培养的详细描述

            3. 研究经历深化
            - 每个研究经历作为一个主要要点，包含七个分行显示的子要点：
                - 项目名称：[内容]
                - 具体时间：[内容]
                - 扮演的角色：[内容]
                - 项目内容描述：[详细描述项目的全部步骤、背景、目标和实施过程]
                - 个人职责：[详细描述所有责任、遇到的困难及解决方案]
                - 取得的成果：[内容]
                - 经历感悟：[内容]

            4. 实习经历深化
            - 每个实习经历作为一个主要要点，包含七个分行显示的子要点：
                - 项目名称：[内容]
                - 具体时间：[内容]
                - 扮演的角色：[内容]
                - 项目内容描述：[详细描述项目的全部步骤、背景、目标和实施过程]
                - 个人职责：[详细描述所有责任、遇到的困难及解决方案]
                - 取得的成果：[内容]
                - 经历感悟：[内容]

            5. 实践经历补充
            - 每个实践经历作为一个主要要点，包含七个分行显示的子要点：
                - 项目名称：[内容]
                - 具体时间：[内容]
                - 扮演的角色：[内容]
                - 项目内容描述：[详细描述项目的全部步骤、背景、目标和实施过程]
                - 个人职责：[详细描述所有责任、遇到的困难及解决方案]
                - 取得的成果：[内容]
                - 经历感悟：[内容]

            6. 未来规划提升
            - 仅包含学习计划、职业规划、发展方向的要点列表
            - 每个要点以单个短横线"-"开头
            - 保留所有时间节点和具体规划细节

            7. 为何选择该专业和院校
            - 仅包含选择原因、国家优势的要点列表（不含具体学校信息）
            - 每个要点以单个短横线"-"开头
            - 保留对专业领域、研究方向的具体兴趣描述

            禁止添加任何非要求的标题、注释或总结。

            """
        }
        
        # 初始化 session_state 中的模板
        if 'templates' not in st.session_state:
            st.session_state.templates = self.default_templates.copy()

    def get_template(self, template_name: str) -> str:
        return st.session_state.templates.get(template_name, "")

    def update_template(self, template_name: str, new_content: str) -> None:
        st.session_state.templates[template_name] = new_content

    def reset_to_default(self):
        st.session_state.templates = self.default_templates.copy()

class TranscriptAnalyzer:
    def __init__(self, api_key: str, prompt_templates: PromptTemplates):
        self.prompt_templates = prompt_templates
        if 'templates' not in st.session_state:
            st.session_state.templates = self.prompt_templates.default_templates.copy()
            
        self.llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.transcript_model,  # 使用session state中的模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        
        # 添加材料简化器LLM，使用成本较低的模型
        self.simplifier_llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.simplifier_model,  # 使用session state中的简化器模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        self.setup_simplifier_chains()

    def extract_images_from_pdf(self, pdf_bytes):
        """从PDF中提取图像"""
        try:
            images = []
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                # 将页面直接转换为图像
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                # 将图像编码为base64字符串
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                images.append(img_base64)
            
            return images
        except Exception as e:
            logger.error(f"提取PDF图像时出错: {str(e)}")
            return []
    
    def analyze_transcript(self, pdf_bytes) -> Dict[str, Any]:
        try:
            if not hasattr(self, 'prompt_templates'):
                logger.error("prompt_templates not initialized")
                raise ValueError("Prompt templates not initialized properly")
            
            images = self.extract_images_from_pdf(pdf_bytes)
            if not images:
                return {
                    "status": "error",
                    "message": "无法从PDF中提取图像"
                }
            
            # 修改消息格式
            messages = [
                SystemMessage(content=self.prompt_templates.get_template('transcript_role')),
                HumanMessage(content=[  # 注意这里改成了列表
                    {
                        "type": "text",
                        "text": f"\n\n请分析这份成绩单，提取成绩信息，并以表格形式输出成绩信息。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{images[0]}"
                        }
                    }
                ])
            ]
            
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行分析
            def run_analysis():
                try:
                    # 调用LLM进行分析
                    chain = LLMChain(llm=self.llm, prompt=ChatPromptTemplate.from_messages(messages))
                    result = chain.run(
                        {},
                        callbacks=[QueueCallbackHandler(message_queue)]
                    )
                    
                    message_queue.put("\n\n成绩单分析完成！")
                    thread.result = result
                    return result
                    
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"成绩单分析错误: {str(e)}")
                    thread.exception = e
                    raise e
            
            # 启动线程
            thread = Thread(target=run_analysis)
            thread.start()
            
            # 用于流式输出的容器
            output_container = st.empty()
            
            # 流式输出
            with output_container:
                full_response = st.write_stream(token_generator())
            
            # 等待线程完成
            thread.join()
            
            # 清空原容器并使用markdown重新渲染完整响应
            if full_response:
                output_container.empty()
                output_container.markdown(full_response)
            
            # 获取结果
            if hasattr(thread, "exception") and thread.exception:
                raise thread.exception
            
            logger.info("成绩单分析完成")
            
            return {
                "status": "success",
                "transcript_analysis": full_response
            }
                
        except Exception as e:
            logger.error(f"成绩单分析错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def setup_simplifier_chains(self):
            # 简化素材表 Chain
            simplifier_prompt = ChatPromptTemplate.from_messages([
                ("system", f"{self.prompt_templates.get_template('material_simplifier_role')}\n\n"
                        f"任务:\n{self.prompt_templates.get_template('material_simplifier_tesk')}\n\n"
                        f"请按照以下格式输出:\n{self.prompt_templates.get_template('material_simplifier_output')}"),
                ("human", "素材表document_content：\n{document_content}")
            ])
            
            self.simplifier_chain = LLMChain(
                llm=self.simplifier_llm,
                prompt=simplifier_prompt,
                output_key="simplifier_result",
                verbose=True
            )
    
    def simplify_materials(self, document_content: str) -> Dict[str, Any]:
        """简化素材表内容"""
        try:
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器，继承自 BaseCallbackHandler
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行LLM
            def run_llm():
                try:
                    result = self.simplifier_chain(
                        {
                            "document_content": document_content
                        },
                        callbacks=[QueueCallbackHandler(message_queue)]
                    )
                    # 将结果存储在线程对象中
                    thread.result = result
                    message_queue.put("\n\n简化完成！")
                    return result
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"简化素材表时出错: {str(e)}")
                    thread.exception = e
                    raise e
            
            # 启动线程
            thread = Thread(target=run_llm)
            thread.start()
            with st.expander("简化后的素材表", expanded=True):
                # 创建流式输出容器
                output_container = st.empty()
                
                # 流式输出
                with output_container:
                    full_response = st.write_stream(token_generator())
                
                # 等待线程完成
                thread.join()
                
                # 清空原容器并使用markdown重新渲染完整响应
                if full_response:
                # 处理可能存在的markdown代码块标记
                    if full_response.startswith("```markdown"):
                        # 移除开头的```markdown和结尾的```
                        full_response = full_response.replace("```markdown", "", 1)
                        if full_response.endswith("```"):
                            full_response = full_response[:-3]
                    
                    output_container.empty()
                    new_container = st.container()
                    with new_container:
                        st.markdown(full_response)
                
                # 获取结果
                if hasattr(thread, "exception") and thread.exception:
                    raise thread.exception
                
                logger.info("simplifier_result completed successfully")
                
                # 从 full_response 中提取分析结果
                processed_response = full_response
                if processed_response.startswith("```markdown"):
                    # 移除开头的```markdown和结尾的```
                    processed_response = processed_response.replace("```markdown", "", 1)
                    if processed_response.endswith("```"):
                        processed_response = processed_response[:-3]
                # 从 full_response 中提取分析结果
                return {
                    "status": "success",
                    "simplifier_result": processed_response
                }
                    
        except Exception as e:
            logger.error(f"simplifier_result processing error: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

class BrainstormingAgent:
    def __init__(self, api_key: str, prompt_templates: PromptTemplates):

        self.content_llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.content_model,  # 使用session state中的模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        self.prompt_templates = prompt_templates
        self.setup_chains()

    def setup_chains(self):        # 内容规划 Chain 
        creator_prompt = ChatPromptTemplate.from_messages([
            ("system", f"{self.prompt_templates.get_template('consultant_role2')}\n\n"
                      f"任务:\n{self.prompt_templates.get_template('consultant_task2')}\n\n"
                      f"请按照以下格式输出:\n{self.prompt_templates.get_template('output_format2')}"),
            ("human", "基于素材表document_content_simple：\n{document_content_simple}\n\n"
                     "成绩单transcript_analysis：\n{transcript_analysis}\n\n"
                     "申请方向school_plan：\n{school_plan}\n\n"
                     "定制需求custom_requirements：\n{custom_requirements}\n\n"
                     "请创建详细的内容规划。")
        ])
        
        self.creator_chain = LLMChain(
            llm=self.content_llm,
            prompt=creator_prompt,
            output_key="creator_output",
            verbose=True
        )

    def process_creator(self, document_content_simple: str, school_plan: str, transcript_analysis: str = "无成绩单", custom_requirements: str = "无定制需求") -> Dict[str, Any]:
        try:
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器，继承自 BaseCallbackHandler
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行LLM
            def run_llm():
                try:
                    result = self.creator_chain(
                        {
                            "document_content_simple": document_content_simple,  # 添加文档内容
                            "school_plan": school_plan,
                            "transcript_analysis": transcript_analysis,
                            "custom_requirements": custom_requirements
                        },
                        callbacks=[QueueCallbackHandler(message_queue)]
                    )
                    # 将结果存储在队列中
                    message_queue.put("\n\n规划完成！")
                    return result
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"Creator processing error: {str(e)}")
                    raise e
            
            # 启动线程
            thread = Thread(target=run_llm)
            thread.start()
            
            # 创建流式输出容器
            output_container = st.empty()
            
            # 流式输出
            with output_container:
                full_response = st.write_stream(token_generator())
            
            # 等待线程完成
            thread.join()
            # 清空原容器并使用markdown重新渲染完整响应
            if full_response:
                # 处理可能存在的markdown代码块标记
                if full_response.startswith("```markdown"):
                    # 移除开头的```markdown和结尾的```
                    full_response = full_response.replace("```markdown", "", 1)
                    if full_response.endswith("```"):
                        full_response = full_response[:-3]
                
                output_container.empty()
                new_container = st.container()
                with new_container:
                    st.markdown(full_response)
            # 获取结果
            if hasattr(thread, "_exception") and thread._exception:
                raise thread._exception
            
            logger.info("Creator analysis completed successfully")
            processed_response = full_response
            if processed_response.startswith("```markdown"):
                # 移除开头的```markdown和结尾的```
                processed_response = processed_response.replace("```markdown", "", 1)
                if processed_response.endswith("```"):
                    processed_response = processed_response[:-3]

            return {
                "status": "success",
                "creator_output": processed_response
            }
                
        except Exception as e:
            logger.error(f"Creator processing error: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }


def add_custom_css():
    st.markdown("""
    <style>
    /* 整体页面样式 */
    .main {
        padding: 2rem;
    }
    
    /* 标题样式 */
    h1, h2, h3 {
        color: #1e3a8a;
        font-weight: 600;
        margin-bottom: 1.5rem;
    }
    
    .page-title {
        text-align: center;
        font-size: 2.5rem;
        margin-bottom: 2rem;
        color: #1e3a8a;
        font-weight: bold;
        padding: 1rem;
        border-bottom: 3px solid #e5e7eb;
    }
    
    /* 文件上传区域样式 */
    .stFileUploader {
        margin-bottom: 2rem;
    }
    
    .stFileUploader > div > button {
        background-color: #f8fafc;
        color: #1e3a8a;
        border: 2px dashed #1e3a8a;
        border-radius: 8px;
        padding: 1rem;
        transition: all 0.3s ease;
    }
    
    .stFileUploader > div > button:hover {
        background-color: #f0f7ff;
        border-color: #2563eb;
    }
    
    /* 按钮样式 */
    .stButton > button {
        background-color: #1e3a8a;
        color: white;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 500;
        border: none;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .stButton > button:hover {
        background-color: #2563eb;
        transform: translateY(-1px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .stButton > button:disabled {
        background-color: #94a3b8;
        cursor: not-allowed;
    }
    
    /* 文本区域样式 */
    .stTextArea > div > div > textarea {
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        padding: 0.75rem;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #2563eb;
        box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
    }
    
    /* 分析结果区域样式 */
    .analysis-container {
        background-color: white;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e5e7eb;
    }
    
    /* 成功消息样式 */
    .stSuccess {
        background-color: #ecfdf5;
        color: #065f46;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #059669;
        margin: 1rem 0;
    }
    
    /* 错误消息样式 */
    .stError {
        background-color: #fef2f2;
        color: #991b1b;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #dc2626;
        margin: 1rem 0;
    }
    
    /* 模型信息样式 */
    .model-info {
        background-color: #f0f7ff;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        display: inline-block;
        font-size: 0.9rem;
        border: 1px solid #bfdbfe;
    }
    
    /* 双列布局样式 */
    .dual-column {
        display: flex;
        gap: 2rem;
        margin: 1rem 0;
    }
    
    .column {
        flex: 1;
        background-color: #f8fafc;
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
    }
    
    /* 分隔线样式 */
    hr {
        margin: 2rem 0;
        border: 0;
        height: 1px;
        background: linear-gradient(to right, transparent, #e5e7eb, transparent);
    }
    
    /* 标签页样式 */
    .stTabs {
        background-color: white;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .stTab {
        padding: 1rem;
    }
    
    /* 展开器样式 */
    .streamlit-expanderHeader {
        background-color: #f8fafc;
        border-radius: 8px;
        padding: 0.75rem;
        font-weight: 500;
        color: #1e3a8a;
        border: 1px solid #e5e7eb;
    }
    
    .streamlit-expanderContent {
        background-color: white;
        border-radius: 0 0 8px 8px;
        padding: 1rem;
        border: 1px solid #e5e7eb;
        border-top: none;
    }
    
    /* 加载动画样式 */
    .stSpinner > div {
        border-color: #2563eb transparent transparent transparent;
    }
    
    /* 文档分析区域样式 */
    .doc-analysis-area {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #e5e7eb;
    }
    
    .doc-analysis-area h3 {
        color: #1e3a8a;
        font-size: 1.25rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e5e7eb;
    }
    
    /* 调整列宽度 */
    .column-adjust {
        padding: 0 1rem;
    }
    </style>
    """, unsafe_allow_html=True)


def initialize_session_state():
    if 'templates' not in st.session_state:
        prompt_templates = PromptTemplates()
        st.session_state.templates = prompt_templates.default_templates.copy()
    
    if 'prompt_templates' not in st.session_state:
        st.session_state.prompt_templates = PromptTemplates()
    
    # 初始化学校研究模型
    if 'school_research_model' not in st.session_state:
        st.session_state.school_research_model = "google/gemini-2.0-flash-001"
    
    # 初始化支持文件分析模型
    if 'support_analysis_model' not in st.session_state:
        st.session_state.support_analysis_model = "qwen/qwen-max"
    
    # 初始化PS策略模型
    if 'ps_strategy_model' not in st.session_state:
        st.session_state.ps_strategy_model = "qwen/qwen-max"
    
    # 初始化内容创作模型
    if 'content_creation_model' not in st.session_state:
        st.session_state.content_creation_model = "qwen/qwen-max"
    
    # 初始化成绩单分析模型
    if 'transcript_model' not in st.session_state:
        st.session_state.transcript_model = "qwen/qwen-max"
    
    # 初始化简化器模型
    if 'simplifier_model' not in st.session_state:
        st.session_state.simplifier_model = "qwen/qwen-max"
        
    # 初始化内容模型
    if 'content_model' not in st.session_state:
        st.session_state.content_model = "qwen/qwen-max"
    
    # 初始化会话状态变量
    if 'school_name' not in st.session_state:
        st.session_state.school_name = ""
    
    if 'program_name' not in st.session_state:
        st.session_state.program_name = ""
    
    if 'research_result' not in st.session_state:
        st.session_state.research_result = None
    
    if 'research_done' not in st.session_state:
        st.session_state.research_done = False
    
    if 'ps_draft' not in st.session_state:
        st.session_state.ps_draft = None
    
    if 'support_file' not in st.session_state:
        st.session_state.support_file = None
    
    if 'support_analysis_result' not in st.session_state:
        st.session_state.support_analysis_result = None
    
    if 'support_analysis_done' not in st.session_state:
        st.session_state.support_analysis_done = False
    
    if 'ps_strategy_result' not in st.session_state:
        st.session_state.ps_strategy_result = None
    
    if 'ps_strategy_done' not in st.session_state:
        st.session_state.ps_strategy_done = False
    
    if 'content_creation_result' not in st.session_state:
        st.session_state.content_creation_result = None
    
    if 'content_creation_done' not in st.session_state:
        st.session_state.content_creation_done = False
    
    if 'show_research' not in st.session_state:
        st.session_state.show_research = False
    
    if 'show_support_analysis' not in st.session_state:
        st.session_state.show_support_analysis = False
    
    if 'show_ps_strategy' not in st.session_state:
        st.session_state.show_ps_strategy = False
    
    if 'show_content_creation' not in st.session_state:
        st.session_state.show_content_creation = False
    
    # 原有的状态变量
    if 'document_content' not in st.session_state:
        st.session_state.document_content = None
    if 'transcript_file' not in st.session_state:
        st.session_state.transcript_file = None
    if 'transcript_analysis_done' not in st.session_state:
        st.session_state.transcript_analysis_done = False
    if 'transcript_analysis_result' not in st.session_state:
        st.session_state.transcript_analysis_result = None
    if 'strategist_analysis_done' not in st.session_state:
        st.session_state.strategist_analysis_done = False
    if 'strategist_analysis_result' not in st.session_state:
        st.session_state.strategist_analysis_result = None
    if 'creator_analysis_done' not in st.session_state:
        st.session_state.creator_analysis_done = False
    if 'creator_analysis_result' not in st.session_state:
        st.session_state.creator_analysis_result = None
    if 'show_transcript_analysis' not in st.session_state:
        st.session_state.show_transcript_analysis = False
    if 'show_strategist_analysis' not in st.session_state:
        st.session_state.show_strategist_analysis = False
    if 'show_creator_analysis' not in st.session_state:
        st.session_state.show_creator_analysis = False
    if 'show_simplifier_analysis' not in st.session_state:
        st.session_state.show_simplifier_analysis = False
    if 'simplifier_analysis_done' not in st.session_state:
        st.session_state.simplifier_analysis_done = False
    if 'simplifier_result' not in st.session_state:
        st.session_state.simplifier_result = None

def main():
    initialize_session_state()
    
    # 设置API密钥
    try:
        openrouter_api_key = st.secrets["OPENROUTER_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("未找到 OPENROUTER_API_KEY。请在 Streamlit 设置中添加此密钥。")
        openrouter_api_key = ""
    
    try:
        serper_api_key = st.secrets["SERPER_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("未找到 SERPER_API_KEY。请在 Streamlit 设置中添加此密钥。")
        serper_api_key = ""
    
    try:
        smithery_api_key = st.secrets["SMITHERY_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("未找到 SMITHERY_API_KEY。请在 Streamlit 设置中添加此密钥。")
        smithery_api_key = ""
    
    try:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
        os.environ["LANGCHAIN_PROJECT"] = "PS助手平台"
    except (KeyError, FileNotFoundError):
        st.error("未找到 LANGCHAIN_API_KEY。请在 Streamlit 设置中添加此密钥。")
    
    st.set_page_config(page_title="PS助手平台", layout="wide")
    add_custom_css()
    st.markdown("<h1 class='page-title'>PS助手平台</h1>", unsafe_allow_html=True)
    
    # 初始化PromptTemplates
    if 'prompt_templates' not in st.session_state:
        st.session_state.prompt_templates = PromptTemplates()
    
    # 检查API密钥是否已设置
    if not openrouter_api_key:
        st.warning("请设置 OPENROUTER_API_KEY 以启用完整功能。")
        st.stop()
    
    # 显示模块状态通知
    if not MCP_AVAILABLE:
        st.warning("MCP模块不可用，部分高级功能将使用替代实现。学校研究功能可能会受到影响，但应用程序仍可运行。")
    
    tab1, tab2 = st.tabs(["PS助手", "提示词设置"])
    
    with tab1:
        # 第一步：学校和专业研究
        st.header("1️⃣ 学校和专业研究")
        
        col1, col2 = st.columns(2)
        with col1:
            school_name = st.text_input("学校名称", value=st.session_state.school_name)
            if school_name != st.session_state.school_name:
                st.session_state.school_name = school_name
        
        with col2:
            program_name = st.text_input("专业名称", value=st.session_state.program_name)
            if program_name != st.session_state.program_name:
                st.session_state.program_name = program_name
        
        # 研究按钮
        if st.button("开始学校和专业研究", key="start_research"):
            if not school_name or not program_name:
                st.error("请输入学校名称和专业名称")
            else:
                st.session_state.show_research = True
                st.session_state.research_done = False
                st.rerun()
        
        # 显示研究结果
        if st.session_state.show_research:
            with st.container():
                st.subheader("院校信息汇总报告")
                
                if not st.session_state.research_done:
                    try:
                        school_research_agent = SchoolResearchAgent(
                            api_key=openrouter_api_key,
                            serper_api_key=serper_api_key,
                            smithery_api_key=smithery_api_key,
                            prompt_templates=st.session_state.prompt_templates
                        )
                        
                        with st.spinner("正在研究学校和专业信息..."):
                            result = school_research_agent.process_school_research(
                                school_name=school_name,
                                program_name=program_name
                            )
                            
                            if result["status"] == "success":
                                st.session_state.research_result = result["research_result"]
                                st.session_state.research_done = True
                                st.success("✅ 学校和专业研究完成！")
                            else:
                                st.error(f"研究过程中出错: {result['message']}")
                    
                    except Exception as e:
                        st.error(f"处理过程中出错: {str(e)}")
                else:
                    st.markdown(st.session_state.research_result)
                    st.success("✅ 学校和专业研究完成！")
        
        # 第二步：PS文件上传和支持文件分析
        st.markdown("---")
        st.header("2️⃣ PS文件上传和支持文件分析")
        
        # PS初稿上传
        st.subheader("PS初稿上传")
        ps_file = st.file_uploader("上传PS初稿文档", type=['docx'])
        
        # 自动检查PS文件状态
        if ps_file:
            try:
                file_bytes = ps_file.read()
                file_stream = io.BytesIO(file_bytes)
                
                md = MarkItDown()
                raw_content = md.convert(file_stream)
                
                if raw_content:
                    st.session_state.ps_draft = raw_content
                    with st.expander("查看PS初稿内容", expanded=False):
                        st.markdown(raw_content, unsafe_allow_html=True)
                else:
                    st.error("无法读取PS初稿文件，请检查格式是否正确。")
            except Exception as e:
                st.error(f"处理PS初稿文件时出错: {str(e)}")
        else:
            st.session_state.ps_draft = None
        
        # 支持文件上传
        st.subheader("支持文件上传（可选）")
        support_file = st.file_uploader("上传支持文件（成绩单、简历等）", type=['pdf', 'docx', 'jpg', 'jpeg', 'png'])
        
        # 如果有支持文件，分析
        if support_file and st.session_state.school_name and st.session_state.program_name:
            if st.button("分析支持文件", key="analyze_support"):
                st.session_state.show_support_analysis = True
                st.session_state.support_analysis_done = False
                st.session_state.support_file = support_file
                st.rerun()
        
        # 显示支持文件分析结果
        if st.session_state.show_support_analysis:
            with st.container():
                st.subheader("支持文件分析报告")
                
                if not st.session_state.support_analysis_done:
                    try:
                        file = st.session_state.support_file
                        file_bytes = file.read()
                        file_name = file.name
                        file_type = ""
                        
                        # 根据文件扩展名确定类型
                        if file_name.endswith('.pdf'):
                            file_type = "pdf"
                        elif file_name.endswith('.docx'):
                            file_type = "docx"
                        elif file_name.endswith(('.jpg', '.jpeg', '.png')):
                            file_type = "image"
                        
                        support_analyzer = SupportFileAnalyzer(
                            api_key=openrouter_api_key,
                            prompt_templates=st.session_state.prompt_templates
                        )
                        
                        with st.spinner("正在分析支持文件..."):
                            result = support_analyzer.analyze_file(
                                file_bytes=file_bytes,
                                file_name=file_name,
                                file_type=file_type,
                                school_name=st.session_state.school_name,
                                program_name=st.session_state.program_name
                            )
                            
                            if result["status"] == "success":
                                st.session_state.support_analysis_result = result["support_analysis_result"]
                                st.session_state.support_analysis_done = True
                                st.success("✅ 支持文件分析完成！")
                            else:
                                st.error(f"支持文件分析出错: {result['message']}")
                    
                    except Exception as e:
                        st.error(f"处理过程中出错: {str(e)}")
                else:
                    st.markdown(st.session_state.support_analysis_result)
                    st.success("✅ 支持文件分析完成！")
        
        # 第三步：PS策略制定
        if st.session_state.ps_draft:
            st.markdown("---")
            st.header("3️⃣ PS改写策略")
            
            if st.button("制定PS改写策略", key="create_strategy"):
                if not st.session_state.school_name or not st.session_state.program_name:
                    st.error("请先完成学校和专业研究")
                else:
                    st.session_state.show_ps_strategy = True
                    st.session_state.ps_strategy_done = False
                    st.rerun()
            
            # 显示PS策略
            if st.session_state.show_ps_strategy:
                with st.container():
                    st.subheader("PS改写策略报告")
                    
                    if not st.session_state.ps_strategy_done:
                        try:
                            ps_strategy_agent = PSStrategyAgent(
                                api_key=openrouter_api_key,
                                prompt_templates=st.session_state.prompt_templates
                            )
                            
                            # 获取支持文件分析结果（如果有）
                            support_analysis = ""
                            if st.session_state.support_analysis_done and st.session_state.support_analysis_result:
                                support_analysis = st.session_state.support_analysis_result
                            
                            with st.spinner("正在制定PS改写策略..."):
                                result = ps_strategy_agent.create_strategy(
                                    ps_draft=st.session_state.ps_draft,
                                    support_analysis=support_analysis,
                                    school_name=st.session_state.school_name,
                                    program_name=st.session_state.program_name
                                )
                                
                                if result["status"] == "success":
                                    st.session_state.ps_strategy_result = result["ps_strategy_result"]
                                    st.session_state.ps_strategy_done = True
                                    st.success("✅ PS改写策略制定完成！")
                                else:
                                    st.error(f"PS策略制定出错: {result['message']}")
                        
                        except Exception as e:
                            st.error(f"处理过程中出错: {str(e)}")
                    else:
                        st.markdown(st.session_state.ps_strategy_result)
                        st.success("✅ PS改写策略制定完成！")
        
        # 第四步：内容创作
        if st.session_state.ps_strategy_done:
            st.markdown("---")
            st.header("4️⃣ 个人陈述创作")
            
            if st.button("开始创作", key="start_creation"):
                st.session_state.show_content_creation = True
                st.session_state.content_creation_done = False
                st.rerun()
            
            # 显示创作结果
            if st.session_state.show_content_creation:
                with st.container():
                    st.subheader("创作结果")
                    
                    if not st.session_state.content_creation_done:
                        try:
                            content_creation_agent = ContentCreationAgent(
                                api_key=openrouter_api_key,
                                prompt_templates=st.session_state.prompt_templates
                            )
                            
                            # 获取支持文件分析结果（如果有）
                            support_analysis = ""
                            if st.session_state.support_analysis_done and st.session_state.support_analysis_result:
                                support_analysis = st.session_state.support_analysis_result
                            
                            with st.spinner("正在创作个人陈述内容..."):
                                result = content_creation_agent.create_content(
                                    ps_strategy=st.session_state.ps_strategy_result,
                                    ps_draft=st.session_state.ps_draft,
                                    support_analysis=support_analysis,
                                    school_name=st.session_state.school_name,
                                    program_name=st.session_state.program_name
                                )
                                
                                if result["status"] == "success":
                                    st.session_state.content_creation_result = result["content_creation_result"]
                                    st.session_state.content_creation_done = True
                                    st.success("✅ 个人陈述创作完成！")
                                else:
                                    st.error(f"内容创作出错: {result['message']}")
                        
                        except Exception as e:
                            st.error(f"处理过程中出错: {str(e)}")
                    else:
                        st.markdown(st.session_state.content_creation_result)
                        st.success("✅ 个人陈述创作完成！")
        
        # 显示模型信息
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"<div class='model-info'>🤖 学校研究模型: <b>{st.session_state.school_research_model}</b></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='model-info'>🤖 支持文件分析模型: <b>{st.session_state.support_analysis_model}</b></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='model-info'>🤖 PS策略模型: <b>{st.session_state.ps_strategy_model}</b></div>", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<div class='model-info'>🤖 内容创作模型: <b>{st.session_state.content_creation_model}</b></div>", unsafe_allow_html=True)
    
    with tab2:
        st.title("提示词和模型设置")
        
        # 模型选择部分
        st.header("模型选择")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("学校研究模型")
            school_research_model = st.selectbox(
                "选择学校研究模型",
                ["google/gemini-2.0-flash-001", "google/gemini-2.0-flash-lite-001", "google/gemini-2.5-flash-preview", "google/gemini-2.5-flash-preview:thinking"],
                index=["google/gemini-2.0-flash-001", "google/gemini-2.0-flash-lite-001", "google/gemini-2.5-flash-preview", "google/gemini-2.5-flash-preview:thinking"].index(st.session_state.school_research_model)
            )
            if school_research_model != st.session_state.school_research_model:
                st.session_state.school_research_model = school_research_model
                st.success(f"已切换学校研究模型为: {school_research_model}")
            
            st.subheader("PS策略模型")
            ps_strategy_model = st.selectbox(
                "选择PS策略模型",
                ["qwen/qwen-max", "deepseek/deepseek-chat-v3-0324", "deepseek/deepseek-chat-v3-0324:free", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"],
                index=["qwen/qwen-max", "deepseek/deepseek-chat-v3-0324", "deepseek/deepseek-chat-v3-0324:free", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"].index(st.session_state.ps_strategy_model)
            )
            if ps_strategy_model != st.session_state.ps_strategy_model:
                st.session_state.ps_strategy_model = ps_strategy_model
                st.success(f"已切换PS策略模型为: {ps_strategy_model}")
        
        with col2:
            st.subheader("支持文件分析模型")
            support_analysis_model = st.selectbox(
                "选择支持文件分析模型",
                ["qwen/qwen-max", "deepseek/deepseek-chat-v3-0324", "deepseek/deepseek-chat-v3-0324:free", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"],
                index=["qwen/qwen-max", "deepseek/deepseek-chat-v3-0324", "deepseek/deepseek-chat-v3-0324:free", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"].index(st.session_state.support_analysis_model)
            )
            if support_analysis_model != st.session_state.support_analysis_model:
                st.session_state.support_analysis_model = support_analysis_model
                st.success(f"已切换支持文件分析模型为: {support_analysis_model}")
            
            st.subheader("内容创作模型")
            content_creation_model = st.selectbox(
                "选择内容创作模型",
                ["qwen/qwen-max", "deepseek/deepseek-chat-v3-0324", "deepseek/deepseek-chat-v3-0324:free", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"],
                index=["qwen/qwen-max", "deepseek/deepseek-chat-v3-0324", "deepseek/deepseek-chat-v3-0324:free", "anthropic/claude-3.7-sonnet", "anthropic/claude-3.5-haiku"].index(st.session_state.content_creation_model)
            )
            if content_creation_model != st.session_state.content_creation_model:
                st.session_state.content_creation_model = content_creation_model
                st.success(f"已切换内容创作模型为: {content_creation_model}")
        
        # 提示词设置
        st.markdown("---")
        st.header("提示词设置")
        
        prompt_templates = st.session_state.prompt_templates
        
        tab_school, tab_support, tab_strategy, tab_content = st.tabs(["学校研究", "支持文件分析", "PS策略", "内容创作"])
        
        with tab_school:
            st.subheader("学校研究")
            school_research_role = st.text_area(
                "角色设定",
                value=prompt_templates.get_template('school_research_role'),
                height=200,
                key="school_research_role"
            )
            school_research_task = st.text_area(
                "任务说明",
                value=prompt_templates.get_template('school_research_task'),
                height=200,
                key="school_research_task"
            )
            school_research_output = st.text_area(
                "输出格式",
                value=prompt_templates.get_template('school_research_output'),
                height=200,
                key="school_research_output"
            )
        
        with tab_support:
            st.subheader("支持文件分析")
            support_analysis_role = st.text_area(
                "角色设定",
                value=prompt_templates.get_template('support_analysis_role'),
                height=200,
                key="support_analysis_role"
            )
            support_analysis_task = st.text_area(
                "任务说明",
                value=prompt_templates.get_template('support_analysis_task'),
                height=200,
                key="support_analysis_task"
            )
            support_analysis_output = st.text_area(
                "输出格式",
                value=prompt_templates.get_template('support_analysis_output'),
                height=200,
                key="support_analysis_output"
            )
        
        with tab_strategy:
            st.subheader("PS策略")
            ps_strategy_role = st.text_area(
                "角色设定",
                value=prompt_templates.get_template('ps_strategy_role'),
                height=200,
                key="ps_strategy_role"
            )
            ps_strategy_task = st.text_area(
                "任务说明",
                value=prompt_templates.get_template('ps_strategy_task'),
                height=200,
                key="ps_strategy_task"
            )
            ps_strategy_output = st.text_area(
                "输出格式",
                value=prompt_templates.get_template('ps_strategy_output'),
                height=200,
                key="ps_strategy_output"
            )
        
        with tab_content:
            st.subheader("内容创作")
            content_creation_role = st.text_area(
                "角色设定",
                value=prompt_templates.get_template('content_creation_role'),
                height=200,
                key="content_creation_role"
            )
            content_creation_task = st.text_area(
                "任务说明",
                value=prompt_templates.get_template('content_creation_task'),
                height=200,
                key="content_creation_task"
            )
            content_creation_output = st.text_area(
                "输出格式",
                value=prompt_templates.get_template('content_creation_output'),
                height=200,
                key="content_creation_output"
            )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("更新提示词", key="update_prompts"):
                # 更新学校研究提示词
                prompt_templates.update_template('school_research_role', school_research_role)
                prompt_templates.update_template('school_research_task', school_research_task)
                prompt_templates.update_template('school_research_output', school_research_output)
                
                # 更新支持文件分析提示词
                prompt_templates.update_template('support_analysis_role', support_analysis_role)
                prompt_templates.update_template('support_analysis_task', support_analysis_task)
                prompt_templates.update_template('support_analysis_output', support_analysis_output)
                
                # 更新PS策略提示词
                prompt_templates.update_template('ps_strategy_role', ps_strategy_role)
                prompt_templates.update_template('ps_strategy_task', ps_strategy_task)
                prompt_templates.update_template('ps_strategy_output', ps_strategy_output)
                
                # 更新内容创作提示词
                prompt_templates.update_template('content_creation_role', content_creation_role)
                prompt_templates.update_template('content_creation_task', content_creation_task)
                prompt_templates.update_template('content_creation_output', content_creation_output)
                
                st.success("✅ 提示词已更新！")
        
        with col2:
            if st.button("重置为默认提示词", key="reset_prompts"):
                prompt_templates.reset_to_default()
                st.rerun()

class SchoolResearchAgent:
    def __init__(self, api_key: str, serper_api_key: str, smithery_api_key: str, prompt_templates: PromptTemplates):
        self.prompt_templates = prompt_templates
        self.smithery_api_key = smithery_api_key
        self.serper_api_key = serper_api_key
        self.openrouter_api_key = api_key  # 存储 OpenRouter API 密钥以供回退方案使用
        
        self.llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.school_research_model,  # 使用session state中的模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        
        # 设置Serper搜索工具
        self.serper_tool = SerperSearchResults(
            serper_api_key=serper_api_key
        )
        
        # 设置SearchSchoolInfo系统提示
        self.setup_chains()
        
    def setup_chains(self):
        # 创建学校研究的Chain
        research_prompt = ChatPromptTemplate.from_messages([
            ("system", f"{self.prompt_templates.get_template('school_research_role')}\n\n"
                     f"任务:\n{self.prompt_templates.get_template('school_research_task')}\n\n"
                     f"请按照以下格式输出:\n{self.prompt_templates.get_template('school_research_output')}"),
            ("human", "请研究以下学校和专业：\n学校名称：{school_name}\n专业名称：{program_name}")
        ])
        
        self.research_chain = LLMChain(
            llm=self.llm,
            prompt=research_prompt,
            output_key="research_result",
            verbose=True
        )
    
    async def run_mcp_thinking(self, task, callback_handler=None):
        """使用Smithery MCP进行结构化思考的异步方法"""
        # 检查MCP是否可用
        if not MCP_AVAILABLE:
            logger.warning("MCP不可用，使用替代实现")
            try:
                # 使用替代实现
                from mcp_fallback import run_sequential_thinking
                result = await run_sequential_thinking(
                    task, 
                    self.smithery_api_key, 
                    callback=lambda token: callback_handler.on_llm_new_token(token, **{}) if callback_handler else None
                )
                return result
            except Exception as e:
                logger.error(f"替代实现错误: {str(e)}")
                if callback_handler:
                    callback_handler.on_llm_new_token(f"替代实现错误: {str(e)}\n使用直接LLM调用...\n", **{})
                
                # 使用 LLM 直接处理任务
                messages = [
                    SystemMessage(content="你是一个专业的院校研究助手，擅长分析各国大学的专业项目信息。"),
                    HumanMessage(content=task)
                ]
                
                chat = ChatOpenAI(
                    temperature=0.1,
                    model="anthropic/claude-3-haiku-20240307",
                    api_key=self.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1",
                    streaming=True
                )
                
                response = chat.invoke(
                    messages,
                    callbacks=[callback_handler] if callback_handler else None
                )
                
                return response.content
        
        # 配置信息
        config = {
            "serperApiKey": self.serper_api_key
        }
        # 编码配置为base64
        config_b64 = base64.b64encode(json.dumps(config).encode()).decode()
        
        # 创建服务器URL
        url = f"https://server.smithery.ai/@marcopesani/mcp-server-sequential-thinking/mcp?config={config_b64}&api_key={self.smithery_api_key}"
        
        result = ""
        try:
            # 连接到服务器使用HTTP客户端
            async with streamablehttp_client(url) as (read_stream, write_stream, _):
                async with mcp.ClientSession(read_stream, write_stream) as session:
                    # 初始化连接
                    await session.initialize()
                    
                    # 执行思考任务
                    thinking_result = await session.run_tool(
                        "sequential-thinking",
                        {
                            "task": task
                        }
                    )
                    result = thinking_result
                    
                    if callback_handler:
                        # 将结果发送到回调处理器以流式显示
                        for token in str(result).split():  # 简单拆分为词作为token
                            callback_handler.on_llm_new_token(token + " ", **{})
        except Exception as e:
            logger.error(f"MCP服务调用失败: {str(e)}")
            if callback_handler:
                callback_handler.on_llm_new_token(f"MCP服务调用失败: {str(e)}\n使用备用方法...\n", **{})
            
            try:
                # 使用替代实现
                from mcp_fallback import run_sequential_thinking
                result = await run_sequential_thinking(
                    task, 
                    self.smithery_api_key, 
                    callback=lambda token: callback_handler.on_llm_new_token(token, **{}) if callback_handler else None
                )
            except Exception as fallback_error:
                logger.error(f"替代实现错误: {str(fallback_error)}")
                if callback_handler:
                    callback_handler.on_llm_new_token(f"替代实现错误: {str(fallback_error)}\n使用直接LLM调用...\n", **{})
                
                # 使用 LLM 直接处理任务
                messages = [
                    SystemMessage(content="你是一个专业的院校研究助手，擅长分析各国大学的专业项目信息。"),
                    HumanMessage(content=task)
                ]
                
                chat = ChatOpenAI(
                    temperature=0.1,
                    model="anthropic/claude-3-haiku-20240307",
                    api_key=self.openrouter_api_key,
                    base_url="https://openrouter.ai/api/v1",
                    streaming=True
                )
                
                response = chat.invoke(
                    messages,
                    callbacks=[callback_handler] if callback_handler else None
                )
                
                result = response.content
                
        return result
    
    def process_school_research(self, school_name: str, program_name: str) -> Dict[str, Any]:
        try:
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行调查
            def run_research():
                try:
                    # 首先执行搜索查询
                    search_queries = [
                        f"{school_name} {program_name} program description curriculum",
                        f"{school_name} {program_name} admission requirements",
                        f"{school_name} {program_name} research areas faculty",
                        f"{school_name} {program_name} career prospects alumni"
                    ]
                    
                    all_search_results = []
                    message_queue.put("正在进行网络搜索...\n\n")
                    
                    for query in search_queries:
                        try:
                            message_queue.put(f"搜索: {query}\n")
                            result = self.serper_tool.search(query)
                            all_search_results.append(result)
                            message_queue.put("✓ 搜索完成\n")
                        except Exception as e:
                            message_queue.put(f"× 搜索失败: {str(e)}\n")
                    
                    message_queue.put("\n正在分析搜索结果并生成报告...\n\n")
                    
                    # 整合搜索结果
                    combined_search_results = "\n\n".join([json.dumps(result) for result in all_search_results])
                    
                    try:
                        # 使用思考链进行系统的信息整合
                        callback_handler = QueueCallbackHandler(message_queue)
                        # 使用asyncio运行异步MCP函数
                        thinking_result = asyncio.run(self.run_mcp_thinking(
                            f"分析{school_name}的{program_name}专业信息，并按格式组织成院校信息汇总报告，基于以下搜索结果：\n\n{combined_search_results}",
                            callback_handler
                        ))
                        message_queue.put("\n\n思考分析完成，正在生成最终报告...\n\n")
                    except Exception as e:
                        logger.error(f"结构化思考过程中出错: {str(e)}")
                        message_queue.put(f"\n\n结构化思考过程中出错: {str(e)}\n跳过结构化思考阶段，直接生成报告...\n\n")
                        thinking_result = ""
                    
                    # 传递结果到研究链
                    result = self.research_chain(
                        {
                            "school_name": school_name,
                            "program_name": program_name,
                            "search_results": combined_search_results
                        },
                        callbacks=[QueueCallbackHandler(message_queue)]
                    )
                    
                    message_queue.put("\n\n院校信息汇总报告生成完成！")
                    thread.result = result["research_result"]
                    return result
                    
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"学校研究错误: {str(e)}")
                    thread.exception = e
                    raise e
            
            # 启动线程
            thread = Thread(target=run_research)
            thread.start()
            
            # 用于流式输出的容器
            output_container = st.empty()
            
            # 流式输出
            with output_container:
                full_response = st.write_stream(token_generator())
            
            # 等待线程完成
            thread.join()
            
            # 清空原容器并使用markdown重新渲染完整响应
            if hasattr(thread, "result"):
                output_container.empty()
                output_container.markdown(thread.result)
            
            # 获取结果
            if hasattr(thread, "exception") and thread.exception:
                raise thread.exception
            
            logger.info("学校研究完成")
            
            return {
                "status": "success",
                "research_result": thread.result if hasattr(thread, "result") else full_response
            }
                
        except Exception as e:
            logger.error(f"学校研究错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

class SupportFileAnalyzer:
    def __init__(self, api_key: str, prompt_templates: PromptTemplates):
        self.prompt_templates = prompt_templates
            
        self.llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.support_analysis_model,  # 使用session state中的模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        
        self.setup_chains()
    
    def extract_images_from_pdf(self, pdf_bytes):
        """从PDF中提取图像"""
        try:
            images = []
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                # 将页面直接转换为图像
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                # 将图像编码为base64字符串
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                images.append(img_base64)
            
            return images
        except Exception as e:
            logger.error(f"提取PDF图像时出错: {str(e)}")
            return []
    
    def setup_chains(self):
        # 创建支持文件分析的Chain
        analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", f"{self.prompt_templates.get_template('support_analysis_role')}\n\n"
                     f"任务:\n{self.prompt_templates.get_template('support_analysis_task')}\n\n"
                     f"请按照以下格式输出:\n{self.prompt_templates.get_template('support_analysis_output')}"),
            ("human", "请分析上传的支持文件：\n{file_content}\n\n目标学校和专业：\n学校：{school_name}\n专业：{program_name}")
        ])
        
        self.analysis_chain = LLMChain(
            llm=self.llm,
            prompt=analysis_prompt,
            output_key="support_analysis_result",
            verbose=True
        )
    
    def analyze_file(self, file_bytes, file_name, file_type, school_name, program_name) -> Dict[str, Any]:
        try:
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行分析
            def run_analysis():
                try:
                    file_content = ""
                    
                    # 根据文件类型处理文件内容
                    if file_type == "pdf":
                        # 提取PDF文本
                        pdf_reader = PdfReader(io.BytesIO(file_bytes))
                        text_content = ""
                        for page in pdf_reader.pages:
                            text_content += page.extract_text() + "\n"
                        
                        # 如果文本内容太少，可能是扫描的PDF，提取图像
                        if len(text_content.strip()) < 100:
                            images = self.extract_images_from_pdf(file_bytes)
                            if images:
                                # 使用图像进行分析
                                message_queue.put("文件似乎是扫描版PDF，正在使用图像识别进行分析...\n")
                                
                                messages = [
                                    SystemMessage(content=f"{self.prompt_templates.get_template('support_analysis_role')}\n\n"
                                                         f"任务:\n{self.prompt_templates.get_template('support_analysis_task')}"),
                                    HumanMessage(content=[  # 注意这里改成了列表
                                        {
                                            "type": "text",
                                            "text": f"请分析这份支持文件，提取关键信息。目标学校：{school_name}，目标专业：{program_name}"
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{images[0]}"
                                            }
                                        }
                                    ])
                                ]
                                
                                result = self.llm.invoke(
                                    messages,
                                    callbacks=[QueueCallbackHandler(message_queue)]
                                )
                                thread.result = result.content
                                return {"support_analysis_result": result.content}
                        else:
                            file_content = text_content
                    
                    elif file_type == "docx":
                        # 处理Word文档
                        try:
                            file_stream = io.BytesIO(file_bytes)
                            md = MarkItDown()
                            file_content = md.convert(file_stream)
                        except Exception as e:
                            doc = Document(io.BytesIO(file_bytes))
                            full_text = []
                            for para in doc.paragraphs:
                                full_text.append(para.text)
                            file_content = '\n'.join(full_text)
                    
                    elif file_type == "image":
                        # 处理图像文件
                        message_queue.put("正在分析图像文件...\n")
                        
                        image_base64 = base64.b64encode(file_bytes).decode('utf-8')
                        
                        messages = [
                            SystemMessage(content=f"{self.prompt_templates.get_template('support_analysis_role')}\n\n"
                                                 f"任务:\n{self.prompt_templates.get_template('support_analysis_task')}"),
                            HumanMessage(content=[  # 注意这里改成了列表
                                {
                                    "type": "text",
                                    "text": f"请分析这份支持文件，提取关键信息。目标学校：{school_name}，目标专业：{program_name}"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_base64}"
                                    }
                                }
                            ])
                        ]
                        
                        result = self.llm.invoke(
                            messages,
                            callbacks=[QueueCallbackHandler(message_queue)]
                        )
                        thread.result = result.content
                        return {"support_analysis_result": result.content}
                    
                    else:
                        file_content = "不支持的文件类型"
                    
                    # 对于文本内容，使用标准的分析链
                    if file_content:
                        result = self.analysis_chain(
                            {
                                "file_content": file_content,
                                "school_name": school_name,
                                "program_name": program_name
                            },
                            callbacks=[QueueCallbackHandler(message_queue)]
                        )
                        
                        thread.result = result["support_analysis_result"]
                        return result
                
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"支持文件分析错误: {str(e)}")
                    thread.exception = e
                    raise e
            
            # 启动线程
            thread = Thread(target=run_analysis)
            thread.start()
            
            # 用于流式输出的容器
            output_container = st.empty()
            
            # 流式输出
            with output_container:
                full_response = st.write_stream(token_generator())
            
            # 等待线程完成
            thread.join()
            
            # 清空原容器并使用markdown重新渲染完整响应
            if hasattr(thread, "result"):
                output_container.empty()
                output_container.markdown(thread.result)
            
            # 获取结果
            if hasattr(thread, "exception") and thread.exception:
                raise thread.exception
            
            logger.info("支持文件分析完成")
            
            return {
                "status": "success",
                "support_analysis_result": thread.result if hasattr(thread, "result") else full_response
            }
                
        except Exception as e:
            logger.error(f"支持文件分析错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

class PSStrategyAgent:
    def __init__(self, api_key: str, prompt_templates: PromptTemplates):
        self.prompt_templates = prompt_templates
            
        self.llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.ps_strategy_model,  # 使用session state中的模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        
        self.setup_chains()
    
    def setup_chains(self):
        # 创建PS策略的Chain
        strategy_prompt = ChatPromptTemplate.from_messages([
            ("system", f"{self.prompt_templates.get_template('ps_strategy_role')}\n\n"
                     f"任务:\n{self.prompt_templates.get_template('ps_strategy_task')}\n\n"
                     f"请按照以下格式输出:\n{self.prompt_templates.get_template('ps_strategy_output')}"),
            ("human", "请基于以下资料制定PS改写策略：\n\nPS初稿内容：\n{ps_draft}\n\n支持文件分析报告：\n{support_analysis}\n\n目标学校和专业：\n学校：{school_name}\n专业：{program_name}")
        ])
        
        self.strategy_chain = LLMChain(
            llm=self.llm,
            prompt=strategy_prompt,
            output_key="ps_strategy_result",
            verbose=True
        )
    
    def create_strategy(self, ps_draft: str, support_analysis: str, school_name: str, program_name: str) -> Dict[str, Any]:
        try:
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行策略制定
            def run_strategy():
                try:
                    # 如果支持文件分析结果为空，提供默认值
                    if not support_analysis:
                        support_analysis = "未提供支持文件分析报告"
                    
                    result = self.strategy_chain(
                        {
                            "ps_draft": ps_draft,
                            "support_analysis": support_analysis,
                            "school_name": school_name,
                            "program_name": program_name
                        },
                        callbacks=[QueueCallbackHandler(message_queue)]
                    )
                    
                    message_queue.put("\n\nPS改写策略报告生成完成！")
                    thread.result = result["ps_strategy_result"]
                    return result
                    
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"PS策略制定错误: {str(e)}")
                    thread.exception = e
                    raise e
            
            # 启动线程
            thread = Thread(target=run_strategy)
            thread.start()
            
            # 用于流式输出的容器
            output_container = st.empty()
            
            # 流式输出
            with output_container:
                full_response = st.write_stream(token_generator())
            
            # 等待线程完成
            thread.join()
            
            # 清空原容器并使用markdown重新渲染完整响应
            if hasattr(thread, "result"):
                output_container.empty()
                output_container.markdown(thread.result)
            
            # 获取结果
            if hasattr(thread, "exception") and thread.exception:
                raise thread.exception
            
            logger.info("PS策略制定完成")
            
            return {
                "status": "success",
                "ps_strategy_result": thread.result if hasattr(thread, "result") else full_response
            }
                
        except Exception as e:
            logger.error(f"PS策略制定错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

class ContentCreationAgent:
    def __init__(self, api_key: str, prompt_templates: PromptTemplates):
        self.prompt_templates = prompt_templates
            
        self.llm = ChatOpenAI(
            temperature=0.1,
            model=st.session_state.content_creation_model,  # 使用session state中的模型
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            streaming=True
        )
        
        self.setup_chains()
    
    def setup_chains(self):
        # 创建内容创作的Chain
        creation_prompt = ChatPromptTemplate.from_messages([
            ("system", f"{self.prompt_templates.get_template('content_creation_role')}\n\n"
                     f"任务:\n{self.prompt_templates.get_template('content_creation_task')}\n\n"
                     f"请按照以下格式输出:\n{self.prompt_templates.get_template('content_creation_output')}"),
            ("human", "请根据以下资料创作个人陈述内容：\n\nPS改写策略报告：\n{ps_strategy}\n\nPS初稿内容：\n{ps_draft}\n\n支持文件分析报告：\n{support_analysis}\n\n目标学校和专业：\n学校：{school_name}\n专业：{program_name}")
        ])
        
        self.creation_chain = LLMChain(
            llm=self.llm,
            prompt=creation_prompt,
            output_key="content_creation_result",
            verbose=True
        )
    
    def create_content(self, ps_strategy: str, ps_draft: str, support_analysis: str, school_name: str, program_name: str) -> Dict[str, Any]:
        try:
            # 创建一个队列用于流式输出
            message_queue = Queue()
            
            # 创建自定义回调处理器
            class QueueCallbackHandler(BaseCallbackHandler):
                def __init__(self, queue):
                    self.queue = queue
                    super().__init__()
                
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    self.queue.put(token)
            
            # 创建一个生成器函数，用于流式输出
            def token_generator():
                while True:
                    try:
                        token = message_queue.get(block=False)
                        yield token
                    except Empty:
                        if not thread.is_alive() and message_queue.empty():
                            break
                    time.sleep(0.01)
            
            # 在单独的线程中运行内容创作
            def run_creation():
                try:
                    # 如果支持文件分析结果为空，提供默认值
                    if not support_analysis:
                        support_analysis = "未提供支持文件分析报告"
                    
                    result = self.creation_chain(
                        {
                            "ps_strategy": ps_strategy,
                            "ps_draft": ps_draft,
                            "support_analysis": support_analysis,
                            "school_name": school_name,
                            "program_name": program_name
                        },
                        callbacks=[QueueCallbackHandler(message_queue)]
                    )
                    
                    message_queue.put("\n\n个人陈述内容创作完成！")
                    thread.result = result["content_creation_result"]
                    return result
                    
                except Exception as e:
                    message_queue.put(f"\n\n错误: {str(e)}")
                    logger.error(f"内容创作错误: {str(e)}")
                    thread.exception = e
                    raise e
            
            # 启动线程
            thread = Thread(target=run_creation)
            thread.start()
            
            # 用于流式输出的容器
            output_container = st.empty()
            
            # 流式输出
            with output_container:
                full_response = st.write_stream(token_generator())
            
            # 等待线程完成
            thread.join()
            
            # 清空原容器并使用markdown重新渲染完整响应
            if hasattr(thread, "result"):
                output_container.empty()
                output_container.markdown(thread.result)
            
            # 获取结果
            if hasattr(thread, "exception") and thread.exception:
                raise thread.exception
            
            logger.info("内容创作完成")
            
            return {
                "status": "success",
                "content_creation_result": thread.result if hasattr(thread, "result") else full_response
            }
                
        except Exception as e:
            logger.error(f"内容创作错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }

if __name__ == "__main__":
    main()