"""Wrapper: run gateway watchdog once (no args needed)"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from gateway_watchdog import run_once
run_once()
