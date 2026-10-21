"""Test GitHub MCP server and setup git config"""
import json, subprocess, os

# 1. Get token
env_file = "D:/hermes/hermes-data/profiles/mybot/.env"
token = None
with open(env_file) as f:
    for line in f:
        if line.startswith("GITHUB_TOKEN="):
            token = line.strip().split("=", 1)[1]
            break

if not token:
    print("❌ No GITHUB_TOKEN found")
else:
    print(f"✅ Token found: {token[:20]}...")
    
    # 2. Test API
    r = subprocess.run(
        ["curl", "-s", "--max-time", "10",
         "-H", f"Authorization: token {token}",
         "https://api.github.com/user"],
        capture_output=True, text=True, timeout=15
    )
    try:
        user = json.loads(r.stdout)
        print(f"✅ GitHub user: {user.get('login')}")
        
        # Set git config
        login = user.get("login", "user")
        subprocess.run(["git", "config", "--global", "user.name", login], check=True)
        print(f"✅ git user.name = {login}")
        
        # Get primary email
        r2 = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-H", f"Authorization: token {token}",
             "https://api.github.com/user/emails"],
            capture_output=True, text=True, timeout=15
        )
        emails = json.loads(r2.stdout)
        if isinstance(emails, list):
            primary = [e["email"] for e in emails if e.get("primary")]
            if primary:
                subprocess.run(["git", "config", "--global", "user.email", primary[0]], check=True)
                print(f"✅ git user.email = {primary[0]}")
        
        # Configure HTTPS instead of SSH
        safe_token = token.replace("@", "%40").replace(":", "%3A").replace("/", "%2F")
        url_replacement = f"https://{login}:{safe_token}@github.com/"
        subprocess.run(["git", "config", "--global", f"url.{url_replacement}.insteadOf",
                       "git@github.com:"], check=True)
        print("✅ git: SSH → HTTPS token auth configured")
        
        # List repos
        r3 = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-H", f"Authorization: token {token}",
             "https://api.github.com/user/repos?per_page=5&sort=updated"],
            capture_output=True, text=True, timeout=15
        )
        repos = json.loads(r3.stdout)
        if isinstance(repos, list):
            print(f"\n📦 Repos ({len(repos)}):")
            for repo in repos:
                print(f"  {repo['full_name']} [{repo['visibility']}]")
        else:
            print(f"\n⚠ Repo list: {repos.get('message', 'unknown')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

# 3. Final git config summary
print("\n" + "=" * 40)
print("Git Configuration:")
r4 = subprocess.run(["git", "config", "--global", "--list"], capture_output=True, text=True, timeout=5)
for line in r4.stdout.split("\n"):
    if any(k in line for k in ["user.name", "user.email", "url.", "credential"]):
        print(f"  {line}")
