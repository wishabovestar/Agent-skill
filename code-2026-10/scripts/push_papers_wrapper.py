"""Wrapper: run paper_link_pusher push"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "analysis"))
from paper_link_pusher import push_domain_filtered
n = push_domain_filtered()
print(f"Pushed papers: {n}")
