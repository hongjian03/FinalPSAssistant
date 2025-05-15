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