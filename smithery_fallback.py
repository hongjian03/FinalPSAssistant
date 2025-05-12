"""
This module simply re-exports the run_sequential_thinking function from mcp_fallback.py.
It exists for backward compatibility.
"""

import logging
from mcp_fallback import run_sequential_thinking

logger = logging.getLogger(__name__)
logger.info("Loaded smithery_fallback module (wrapper around mcp_fallback)") 