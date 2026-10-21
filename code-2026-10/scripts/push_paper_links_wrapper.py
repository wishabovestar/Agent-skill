"""
Wrapper: push outstanding paper links to qqbot2 WeChat
"""
import sys, os
sys.path.insert(0, "D:/hermes/analysis")
from paper_link_pusher import push_domain_filtered
n = push_domain_filtered()
print(f"Pushed {n} paper links")
