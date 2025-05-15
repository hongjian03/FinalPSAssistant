import os
import io
import base64
from PIL import Image
from typing import Dict, Any, Optional
import requests
import json
import streamlit as st

class TranscriptAnalyzer:
    """
    Agent responsible for analyzing and extracting data from transcript images.
    Uses Qwen 2.5 VL vision-language model to read and interpret transcript data.
    """
    
    def __init__(self):
        """Initialize the Transcript Analyzer agent with Qwen 2.5 VL model via OpenRouter."""
        # Get API key from Streamlit secrets
        self.api_key = st.secrets.get("OPENROUTER_API_KEY", "")
        self.model_name = "qwen/qwen2.5-vl-72b-instruct"
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
    def encode_image(self, image: Image.Image) -> str:
        """
        Encode image to base64 for API transmission.
        
        Args:
            image: PIL Image object
            
        Returns:
            Base64 encoded image string
        """
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
        
    def extract_transcript_data(self, image: Image.Image) -> str:
        """
        Extract transcript data from an uploaded image using Qwen 2.5 VL via OpenRouter.
        
        Args:
            image: The transcript image uploaded by the user
            
        Returns:
            String representation of the extracted transcript data
        """
        try:
            # Encode image to base64
            base64_image = self.encode_image(image)
            
            # Create prompt for the Qwen model
            prompt = """Please analyze this academic transcript image. 
            Extract all the following information:
            - Student name and ID
            - University and program
            - Course names, codes, and grades
            - GPA or overall average
            - Academic year or semester
            
            Format this information in a clear, structured way that's easy to read.
            Only include information that is actually present in the image.
            """
            
            # Prepare the API request payload for OpenRouter
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                "max_tokens": 2000
            }
            
            # Set up headers with OpenRouter API key
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://applicant-analysis.streamlit.app",  # Optional: Replace with your actual app URL
                "X-Title": "Applicant Analysis Tool"  # Optional: Your application name
            }
            
            # Make API request
            with st.spinner("AI analyzing transcript with Qwen 2.5 VL..."):
                response = requests.post(self.api_url, headers=headers, json=payload)
                
                # Check for successful response
                if response.status_code == 200:
                    result = response.json()
                    transcript_text = result["choices"][0]["message"]["content"]
                    return transcript_text
                else:
                    # If real API fails, provide informative error and use mock data
                    st.error(f"OpenRouter API Error: {response.status_code} - {response.text}")
                    return self.get_mock_transcript()
                    
        except Exception as e:
            st.error(f"Error extracting transcript data: {str(e)}")
            return self.get_mock_transcript()
    
    def get_mock_transcript(self) -> str:
        """
        Return mock transcript data as a fallback.
        
        Returns:
            Mock transcript text string
        """
        mock_transcript = """
        Student Name: Zhang Wei
        Student ID: 2022XJU456
        University: Xi'an Jiaotong-Liverpool University
        Program: Computer Science
        Academic Year: 2023-2024
        
        Courses:
        - CSE101 Introduction to Programming: A (90%)
        - CSE102 Data Structures and Algorithms: A- (85%)
        - MTH201 Linear Algebra: B+ (78%)
        - CSE201 Database Systems: A (92%)
        - CSE205 Computer Networks: B (75%)
        - ENG101 Academic English: B+ (79%)
        
        Current GPA: 3.76/4.0
        """
        
        return mock_transcript 