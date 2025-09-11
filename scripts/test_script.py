#!/usr/bin/env python3
"""
Simple test script for debugging webapp script execution
"""

import sys
import os
from pathlib import Path

print("TEST SCRIPT STARTING")
print(f"Current working directory: {os.getcwd()}")
print(f"Script location: {__file__}")
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

# Test file access
project_root = Path.cwd()
print(f"Project root: {project_root}")
print(f"Project root exists: {project_root.exists()}")

# Check for key files
key_files = ['keys.json', 'data/database.db', 'scripts/', 'logs/']
for file_path in key_files:
    full_path = project_root / file_path
    print(f"{file_path}: exists={full_path.exists()}")

print("TEST SCRIPT COMPLETED SUCCESSFULLY")