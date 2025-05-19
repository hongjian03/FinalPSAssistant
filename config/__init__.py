# Config package initialization
# This file makes the config directory a proper Python package 

from . import prompts
from . import jina_config

__all__ = ['prompts', 'jina_config'] 