import subprocess, time, os, json

# Wait for this session to end
time.sleep(10)

# Try to restart the gateway
result = subprocess.run(
    ["hermes", "gateway", "restart", "--profile", "qqbot2"],
    capture_output=True, text=True, timeout=30
)
print(f"exit: {result.returncode}")
print(f"stdout: {result.stdout}")
print(f"stderr: {result.stderr}")

# If restart fails, try run --replace
if result.returncode != 0:
    result2 = subprocess.run(
        ["hermes", "gateway", "run", "--replace", "--profile", "qqbot2"],
        capture_output=True, text=True, timeout=60
    )
    print(f"run exit: {result2.returncode}")
