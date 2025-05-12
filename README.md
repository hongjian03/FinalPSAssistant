# PS助手平台 (Personal Statement Assistant Platform)

这是一个使用Streamlit构建的个人陈述(Personal Statement)辅助工具，旨在帮助用户研究学校和专业信息，分析支持文件，并生成高质量的个人陈述文档。

## 功能特点

- **学校和专业研究**: 自动搜索、整合和分析学校和专业信息
- **支持文件分析**: 分析成绩单、简历等支持文件，提取有用信息
- **PS策略制定**: 根据初稿和支持文件分析，制定个性化的改进策略
- **内容创作**: 根据策略指导创作高质量的个人陈述内容

## 如何使用

1. 输入目标学校和专业名称，开始学校和专业研究
2. 上传PS初稿和支持文件（如有）
3. 生成PS改写策略
4. 根据策略生成最终的PS内容

## 技术栈

- Streamlit
- LangChain框架
- OpenRouter API集成
- 多种文档处理库 (python-docx, PyPDF2, PyMuPDF)

## 安装和运行

```bash
pip install -r requirements.txt
streamlit run fengao_brainstorming.py
```

## 注意事项

使用前请确保已正确设置API密钥，包括:
- OPENROUTER_API_KEY
- SERPER_API_KEY
- SMITHERY_API_KEY
- LANGCHAIN_API_KEY 

## 依赖说明

该应用程序使用了多个依赖库，其中一些可能在某些环境中难以安装：

### MCP (Machine Conversation Protocol)

应用程序优先使用MCP连接Smithery的sequential thinking服务进行院校研究。如果MCP不可用，程序会自动使用以下备选方案：

1. 首先尝试使用`mcp_fallback.py`中的简化实现
2. 如果备选方案失败，则使用直接的LLM调用

### 部署注意事项

在Streamlit Cloud上部署时可能会遇到依赖问题。本代码库已经做了以下优化：

1. 移除了对`langchain-callbacks-streamlit`的依赖
2. 对MCP提供了完整的备选实现
3. 简化了依赖关系

如果在部署过程中遇到问题，请尝试：

1. 首先通过`pip install -r requirements.txt`安装依赖
2. 如果某些依赖安装失败，应用程序会自动使用备选实现 