"""Gateway launcher - SSL patch, profile set via env, direct start_gateway call."""
import ssl, sys, os, asyncio

# Patch SSL 
ssl._create_default_https_context = ssl._create_unverified_context

# Set profile via env (bypasses CLI --profile parsing)
os.environ['HERMES_PROFILE'] = 'mybot'

# Direct call to start_gateway (proven to work)
from gateway.run import start_gateway
success = asyncio.run(start_gateway(replace=True))
sys.exit(0 if success else 1)
