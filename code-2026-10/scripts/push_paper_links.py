#!/usr/bin/env python3
"""Wrapper: push outstanding paper links to WeChat"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "analysis"))
exec(open(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "analysis", "paper_link_pusher.py")).read().replace('if __name__ == "__main__":', 'if True:'))
