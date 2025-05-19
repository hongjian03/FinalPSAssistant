# Applicant Analysis Tool

通过AI驱动的应用程序分析申请人竞争力并推荐合适的UCL项目。

## 功能特点

- **成绩单分析**：上传成绩单图片，通过OpenRouter访问Qwen 2.5 VL视觉语言模型自动进行分析
- **竞争力分析**：通过多种可选AI模型获取详细的学术竞争力分析
- **项目推荐**：基于个人档案获取个性化的UCL项目推荐
- **网络搜索集成**：使用Serper MCP服务器搜索有关UCL项目的最新信息
- **提示词调试**：微调AI代理使用的提示词以自定义分析
- **多LLM支持**：通过OpenRouter选择各种模型进行分析和推荐
- **LangSmith监控**：监控和分析AI代理的输入输出，优化性能和质量

## 支持的模型

### 成绩单分析器
- 固定使用：**qwen/qwen2.5-vl-72b-instruct**（通过OpenRouter访问，专门用于视觉文档分析）

### 竞争力分析和咨询助手
- qwen/qwen-max
- qwen/qwen3-32b:free
- deepseek/deepseek-chat-v3-0324:free
- anthropic/claude-3.7-sonnet
- openai/gpt-4.1

## 技术要求

- Python 3.8+
- Streamlit
- LangChain
- LangSmith（监控和分析）
- MCP Client（用于Serper集成）
- 各种服务的API密钥（参见安装部分）

## 安装步骤

1. 克隆此存储库
2. 安装所需的软件包：
   ```
   pip install -r requirements.txt
   ```
3. 设置API密钥作为Streamlit secrets（创建`.streamlit/secrets.toml`文件）：
   ```toml
   # OpenRouter API (用于访问所有LLM模型，包括视觉模型)
   OPENROUTER_API_KEY = "your_openrouter_api_key"
   
   # Serper Web搜索 API (用于项目推荐)
   SERPER_API_KEY = "your_serper_api_key"
   SMITHERY_API_KEY = "your_smithery_api_key"
   
   # LangSmith监控 API (用于追踪AI代理)
   LANGSMITH_API_KEY = "your_langsmith_api_key"
   LANGSMITH_PROJECT = "applicant-analysis-tool"  # 可选项
   ```

## 使用方法

1. 运行Streamlit应用程序：
   ```
   streamlit run app.py
   ```
2. 在浏览器中打开终端中显示的URL（通常为`http://localhost:8501`）
3. 在"竞争力分析"选项卡中：
   - 选择您的大学
   - 输入您的专业
   - 选择预测的学位分类
   - 上传您的成绩单图片
   - 点击"提交"开始完整的分析过程
4. 在"AI模型和提示词配置"选项卡中：
   - 为竞争力分析和项目推荐选择AI模型
   - 根据需要修改提示词以自定义AI响应
5. 在"系统状态"选项卡中：
   - 检查API密钥的状态
   - 查看LangSmith监控的状态和配置
   - 管理Serper客户端连接
6. 系统将自动：
   - 使用Qwen 2.5 VL提取并显示成绩单数据
   - 使用您选择的模型生成竞争力分析报告
   - 基于分析提供UCL项目推荐
   - 通过LangSmith记录和监控关键AI交互

## 工作流程

应用程序遵循以下工作流程：

1. **成绩单分析**：Qwen 2.5 VL从上传的成绩单图片中提取结构化数据
2. **竞争力分析**：选定的LLM分析学生的档案并生成竞争力报告
3. **项目推荐**：第二个LLM搜索并推荐合适的UCL项目
4. **性能监控**：LangSmith记录整个过程中的关键指标和内容

## LangSmith监控功能

应用程序使用LangSmith追踪AI代理的输入和输出：

1. **竞争力分析追踪**：记录分析请求的输入参数（大学、专业、成绩单数据）和输出结果
2. **项目推荐追踪**：记录推荐请求的输入参数（竞争力报告）和输出的项目推荐
3. **监控面板**：通过LangSmith网站访问详细的监控面板和数据
4. **性能优化**：使用数据来优化提示词和模型选择

## Serper MCP服务器集成

应用程序使用Serper MCP服务器执行UCL项目信息的Web搜索。此集成：

1. 允许获取实时、最新的项目信息
2. 根据当前UCL提供的内容提供更准确的项目推荐
3. 如果搜索失败或API密钥未配置，则回退到模拟数据

## 开发说明

应用程序的结构如下：

- `app.py`：主Streamlit应用程序
- `agents/`：用于不同任务的AI代理
  - `transcript_analyzer.py`：使用Qwen 2.5 VL从成绩单图片中提取数据
  - `competitiveness_analyst.py`：分析学生竞争力
  - `consulting_assistant.py`：基于竞争力推荐UCL项目
  - `serper_client.py`：Serper MCP服务器集成的客户端
- `config/`：配置文件
  - `prompts.py`：管理提示词加载和保存
  - `prompts.json`：存储当前提示词（自动创建）

## 许可证

该项目根据MIT许可证授权 - 参见LICENSE文件了解详情。

# PS Assistant Tool (PS分稿测试助手)

这是一个基于AI的PS（Personal Statement）分析和改写工具，帮助申请者优化个人陈述文档。

## 功能特点

### 主要工作流程

本工具由四个核心智能代理组成，按顺序完成PS改写任务：

1. **Agent 1 (院校信息收集代理)**：
   - 搜索并分析目标院校和专业的信息
   - 使用MCP集成的网络搜索获取最新院校数据
   - 生成结构化的院校信息收集报告
   - 包含项目概览、申请要求、课程设置等信息

2. **Agent 2.1 (支持文件分析代理)**：
   - 分析用户上传的支持文件（简历、成绩单等）
   - 提取关键信息，如学术成就、研究经历、技能等
   - 生成支持文件分析报告

3. **Agent 2.2 (PS分析代理)**：
   - 分析用户上传的PS初稿
   - 结合院校信息和支持文件分析
   - 生成详细的PS改写策略报告

4. **Agent 3 (PS改写代理)**：
   - 根据改写策略完成PS的全面改写
   - 保留原稿核心信息，优化表达方式
   - 增强与目标院校的匹配度

### 技术特点

- 支持多种文件格式（PDF、DOC、DOCX、TXT、图片等）
- 各代理支持不同的AI模型选择（Claude、GPT-4、Qwen等）
- 使用MCP (Marcopesani Client Protocol) 进行网络搜索集成
- LangSmith集成用于跟踪和分析AI代理的工作过程
- 提供自定义提示词配置接口
- 所有报告可导出为Word文档

## 安装与运行

### 环境要求

- Python 3.8+
- 必要API密钥:
  - OpenRouter API密钥 (用于AI模型调用)
  - Serper API密钥 (用于网络搜索)
  - Smithery API密钥 (用于MCP服务器访问)
  - LangSmith API密钥 (用于追踪AI代理工作流程，可选)

### 安装步骤

1. 克隆仓库
```
git clone <repository-url>
cd FinalPSAssistant
```

2. 安装依赖
```
pip install -r requirements.txt
```

3. 设置API密钥
   - 复制`.streamlit/secrets.toml.example`文件为`.streamlit/secrets.toml`
   - 添加以下内容：
```toml
# OpenRouter API密钥 (用于访问所有LLM模型)
OPENROUTER_API_KEY = "your_openrouter_api_key_here"

# Serper Web搜索 API (用于项目推荐)
SERPER_API_KEY = "your_serper_api_key_here"
SMITHERY_API_KEY = "your_smithery_api_key_here"

# LangSmith监控 API (用于追踪AI代理的输入输出，可选)
LANGSMITH_API_KEY = "your_langsmith_api_key_here"
LANGSMITH_PROJECT = "applicant-analysis-tool"  # 可选项，默认项目名称
```

4. 运行应用
```
streamlit run ps_app.py
```

## 使用指南

1. **步骤1 - 院校信息收集**：
   - 输入目标院校和专业信息
   - 系统通过MCP搜索并整理相关申请要求和项目信息
   - 生成院校信息收集报告
   - 搜索进度和结果显示在主界面上

2. **步骤2 - 文件分析**：
   - 上传支持文件（简历、成绩单等，可选）
   - 上传PS初稿（必需）
   - 系统分析支持文件和PS初稿
   - 生成PS改写策略报告

3. **步骤3 - PS改写**：
   - 查看PS改写策略报告
   - 点击"开始改写PS"按钮
   - 系统根据策略改写PS
   - 展示和下载改写后的PS

## MCP网络搜索集成

该工具使用MCP (Marcopesani Client Protocol) 从Serper API获取最新的学校和专业信息：

- 通过streamablehttp_client建立与MCP服务器的连接
- 搜索院校和专业的最新信息和要求
- 在界面中显示搜索进度和结果
- 如果搜索失败，会回退到使用LLM已有知识生成报告

## LangSmith追踪

系统集成了LangSmith用于追踪和分析AI代理的工作过程：

- 记录每个代理的输入和输出
- 可通过LangSmith控制台查看详细的运行记录
- 帮助开发者分析和改进AI代理的性能
- 如未配置LangSmith密钥，该功能不会影响系统正常运行

## 提示词定制

工具提供了自定义提示词功能，您可以根据需要修改各代理的：
- 角色描述
- 任务描述
- 输出格式

所有更改将保存并用于后续的AI调用。

## 常见问题

- **支持的文件格式有哪些?**
  - PS初稿: PDF, DOC, DOCX, TXT
  - 支持文件: PDF, JPG, JPEG, PNG, TXT

- **如何选择不同的AI模型?**
  - 在"提示词调试"选项卡中可以为每个代理选择不同的AI模型

- **如果网络搜索失败怎么办?**
  - 系统会自动回退到使用LLM的已有知识生成院校信息报告
  - 请确保已正确配置SERPER_API_KEY和SMITHERY_API_KEY
  
- **搜索过程中出现滞后或无响应怎么办?**
  - 系统设置了30秒的超时时间，超时后会显示错误信息
  - 请检查网络连接和API密钥是否正确

## 注意事项

- 本工具需要互联网连接才能正常工作
- API调用可能产生费用，请确保OpenRouter账户有足够余额
- 所有生成的内容仅供参考，最终PS应由申请者自行决定

## MCP集成详情

### 最近修复的问题

1. **界面显示问题**：
   - 修复了进度条显示在侧边栏而非主UI的问题
   - 通过使用Streamlit容器改进了进度显示

2. **MCP连接问题**：
   - 更新了MCP客户端实现，从websocket_client改为streamablehttp_client
   - 增加了连接重试机制，最多重试3次
   - 添加了更详细的错误报告和状态反馈

3. **搜索工具适配**：
   - 添加了动态工具名称检测，自动识别并适配不同的搜索工具名称
   - 支持"google_search"、"search"、"web-search"等多种工具名
   - 添加了scrape工具作为搜索工具的备选方案
   - 改进了搜索结果格式化，确保统一的返回结构

4. **错误处理**：
   - 增强了错误恢复机制，防止搜索失败时应用崩溃
   - 即使在API调用失败时也能返回格式化的结果
   - 添加了更友好的错误提示

### MCP客户端配置

MCP (Marcopesani Client Protocol) 是一个灵活的协议，允许通过HTTP或WebSocket访问不同的AI服务。

本应用使用MCP实现特别需要以下配置：

1. **API密钥设置**：
   ```toml
   # Serper API密钥 (用于搜索内容)
   SERPER_API_KEY = "your_serper_api_key"
   
   # Smithery API密钥 (用于访问MCP服务器)
   SMITHERY_API_KEY = "your_smithery_api_key" 
   ```

2. **支持的搜索工具**：
   当前实现支持以下工具名：
   - `google_search` (优先使用)
   - `search`
   - `serper-search`
   - `web-search`
   - `google-search` 
   - `serper`
   - `scrape` (作为备用选项)

3. **格式化搜索结果**：
   无论使用何种搜索工具，搜索结果都被统一格式化为以下结构：
   ```json
   {
     "organic": [
       {
         "title": "搜索结果标题",
         "link": "https://result.url",
         "snippet": "结果摘要文本..."
       }
     ]
   }
   ```

4. **错误处理**：
   如果搜索失败，结果将被格式化为：
   ```json
   {
     "error": "错误信息",
     "organic": [
       {
         "title": "搜索失败",
         "link": "",
         "snippet": "错误描述..."
       }
     ]
   }
   ```

## 疑难解答

### MCP连接问题

如果遇到MCP连接问题：

1. **检查API密钥**：
   - 确认SERPER_API_KEY和SMITHERY_API_KEY已正确设置
   - 确认API密钥有效且未过期

2. **网络问题**：
   - 确认您的网络可以访问`https://server.smithery.ai`
   - 关闭可能阻止请求的代理或防火墙

3. **服务器状态**：
   - 检查MCP服务器是否在线
   - 如果服务器频繁离线，请考虑实现本地搜索备选方案

4. **重试与备选**：
   - 应用自动重试连接最多3次
   - 如果仍无法连接，会生成格式化的错误结果

### 搜索工具问题

如果工具名称不匹配：

1. **检查可用工具**：
   - 系统状态选项卡会显示服务器提供的可用工具
   - 确认服务器确实提供了搜索工具

2. **工具名称变更**：
   - 如果服务器更改了工具名称，应用会自动尝试识别
   - 对于包含"search"的工具名会自动适配

3. **使用备选工具**：
   - 如果没有搜索工具但有"scrape"工具，会自动切换使用 

## 主要特性

- 🎓 **大学和专业信息检索**：通过搜索引擎和网络抓取获取最新、最准确的大学和专业信息
- 🔍 **智能搜索**：使用Serper API进行网络搜索，并使用Jina Reader进行内容抓取，确保高质量结果
- 📄 **文档处理**：支持PDF、Word和图像文件的上传和分析
- 💬 **自然对话**：使用大型语言模型提供自然、连贯的对话体验
- 📊 **个性化匹配**：基于用户的学术背景、兴趣和偏好推荐合适的大学和专业
- 📋 **专业信息总结**：自动总结专业信息，包括课程设置、职业前景和录取要求

## 技术架构

### 核心组件

1. **Streamlit前端**：用户界面和交互
2. **Serper API**：网络搜索功能，获取最新大学和专业信息
3. **Jina Reader**：高效网页内容抓取，将HTML转换为Markdown格式
4. **OpenAI API**：提供对话和内容生成能力
5. **MCP**：Model Control Protocol，用于模型调用
6. **文档处理**：解析和提取PDF、Word和图像文件的内容

## 抓取技术

系统使用两种抓取方法获取网页内容：

1. **Jina Reader API抓取**：主要方法，将HTML内容转换为markdown格式，提供干净、结构化的内容
   - 支持自动图像描述
   - 处理复杂的网页布局
   - 高效率的内容提取
   
2. **直接抓取（备选方案）**：当Jina Reader失败时，使用自定义的抓取逻辑
   - 使用BeautifulSoup进行HTML解析
   - 提取大学项目的关键信息
   - 格式化输出为markdown文本 