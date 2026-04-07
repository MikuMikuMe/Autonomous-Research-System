#!/usr/bin/env python3
"""
Start the Autonomous Research System GUI server.
Open http://127.0.0.1:8000 in your browser.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

if __name__ == "__main__":
    import uvicorn
    print("Autonomous Research System — GUI")
    print("Open http://127.0.0.1:8000 in your browser")
    print("-" * 40)
    uvicorn.run("gui.server:app", host="127.0.0.1", port=8000, reload=False)
