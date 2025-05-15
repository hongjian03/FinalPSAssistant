import os
import json
import base64
import asyncio
from typing import Dict, Any, List, Optional
import streamlit as st

import mcp
from mcp.client.websocket import websocket_client

class SerperClient:
    """
    Client for interacting with the Serper MCP server for web search capabilities.
    This allows the consulting assistant to search for up-to-date information about UCL programs.
    """
    
    def __init__(self):
        """Initialize the Serper MCP client with configuration from Streamlit secrets."""
        # Get API keys from Streamlit secrets
        self.serper_api_key = st.secrets.get("SERPER_API_KEY", "")
        self.smithery_api_key = st.secrets.get("SMITHERY_API_KEY", "")
        
        # Server config
        self.config = {
            "serperApiKey": self.serper_api_key
        }
        
        # Base64 encode the config
        self.config_b64 = base64.b64encode(json.dumps(self.config).encode()).decode()
        
        # Create server URL
        self.url = f"wss://server.smithery.ai/@marcopesani/mcp-server-serper/ws?config={self.config_b64}&api_key={self.smithery_api_key}"
        
        # Keep a record of tools
        self.available_tools = []
    
    async def initialize(self):
        """Initialize the connection to the MCP server and get available tools."""
        try:
            # Connect to the server using websocket client
            async with websocket_client(self.url) as streams:
                async with mcp.ClientSession(*streams) as session:
                    # Initialize the connection
                    await session.initialize()
                    
                    # List available tools
                    tools_result = await session.list_tools()
                    self.available_tools = [t.name for t in tools_result.tools]
                    return True
        except Exception as e:
            st.error(f"Error initializing Serper MCP client: {e}")
            return False
    
    async def search_web(self, query: str) -> Dict[str, Any]:
        """
        Perform a web search using the Serper MCP server.
        
        Args:
            query: The search query
            
        Returns:
            Dictionary containing search results
        """
        try:
            # Connect to the server using websocket client
            async with websocket_client(self.url) as streams:
                async with mcp.ClientSession(*streams) as session:
                    # Initialize the connection
                    await session.initialize()
                    
                    # Call the web search tool
                    result = await session.call_tool("web-search", arguments={
                        "query": query,
                        "numResults": 5
                    })
                    
                    return result.result if hasattr(result, 'result') else {}
        except Exception as e:
            error_msg = f"执行Web搜索时出错: {str(e)}"
            st.error(error_msg)
            return {"error": error_msg}
    
    async def search_ucl_programs(self, keywords: List[str]) -> List[Dict[str, str]]:
        """
        Search for UCL programs using the web search tool.
        
        Args:
            keywords: List of keywords to search for
            
        Returns:
            List of program information dictionaries
        """
        try:
            # Construct search query
            search_query = f"UCL University College London postgraduate programs {' '.join(keywords)}"
            
            # Perform search
            search_results = await self.search_web(search_query)
            
            # Check for errors
            if "error" in search_results:
                return [{"error": search_results["error"]}]
            
            # Process actual search results
            programs = []
            
            # Extract relevant information from search results
            if "organic" in search_results:
                for result in search_results["organic"][:5]:
                    programs.append({
                        "title": result.get("title", "无标题"),
                        "url": result.get("link", "无链接"),
                        "description": result.get("snippet", "无描述")
                    })
            
            # Return real search results
            return programs
            
        except Exception as e:
            error_msg = f"搜索UCL项目时出错: {str(e)}"
            st.error(error_msg)
            return [{"error": error_msg}]
    
    def run_async(self, coroutine):
        """Helper method to run async methods synchronously."""
        return asyncio.run(coroutine) 