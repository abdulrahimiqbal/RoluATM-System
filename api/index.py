"""
Vercel entry point for RoluATM Cloud API
"""

import sys
import os
import importlib.util

# Add the parent directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the app from cloud-api/main.py
spec = importlib.util.spec_from_file_location("main", os.path.join(os.path.dirname(__file__), '..', 'cloud-api', 'main.py'))
main_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_module)

app = main_module.app

# This is the entry point for Vercel
handler = app 