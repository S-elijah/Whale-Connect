"""
Vercel Serverless Function Entry Point
This file is required for Vercel Python deployments
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app
from app import app

# Vercel expects the app to be exported as 'app'
__all__ = ['app']