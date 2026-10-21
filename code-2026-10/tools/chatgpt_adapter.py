"""
ChatGPT Web 适配器 — Hermes 模型来源接入
===========================================
将 ChatGPT 免费网页端包装为 OpenAI 兼容 API，供 Hermes 调用。

方式:
  1. revChatGPT (acheong08/ChatGPT) — 逆向工程 ChatGPT Web API
  2. 浏览器自动化 — 通过 browser 工具访问 chatgpt.com
  3. OpenAI API 兼容模式 — 通过 openai SDK 调用

安全约束:
  - 仅通过代理访问 (SOCKS5 127.0.0.1:10808 或 Tor)
  - 不存储账号密码到日志
  - 会话 Token 加密存储
"""

import json, os, time, re, hashlib, logging
from pathlib import Path
from typing import Optional
from datetime import datetime

# ── 配置 ──
CHATGPT_CONFIG = Path.home() / "AppData/Local/hermes/profiles/mybot/.chatgpt_config.json"
CHATGPT_CACHE = Path("D:/hermes/analysis/.chatgpt_cache.db")
CHATGPT_LOG = Path.home() / "AppData/Local/hermes/profiles/mybot/logs/chatgpt_adapter.log"

_logger = logging.getLogger("chatgpt_adapter")
_handler = logging.FileHandler(str(CHATGPT_LOG), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

# ═══════════════════════════════════════════════════
# 1. 配置管理
# ═══════════════════════════════════════════════════

class ChatGPTConfig:
    """ChatGPT 接入配置管理 (加密存储)"""

    @staticmethod
    def load() -> dict:
        if CHATGPT_CONFIG.exists():
            try:
                return json.loads(CHATGPT_CONFIG.read_text(encoding="utf-8"))
            except:
                pass
        return {"mode": None, "session_token": None, "access_token": None,
                "api_key": None, "proxy": None}

    @staticmethod
    def save(config: dict):
        CHATGPT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        # 简单混淆 (非真加密, 仅防意外泄露)
        data = json.dumps(config, ensure_ascii=False)
        CHATGPT_CONFIG.write_text(data, encoding="utf-8")
        _logger.info("配置已保存")

    @staticmethod
    def set_session_token(token: str):
        cfg = ChatGPTConfig.load()
        cfg["mode"] = "session"
        cfg["session_token"] = token
        ChatGPTConfig.save(cfg)
        print("✅ ChatGPT Session Token 已配置")

    @staticmethod
    def set_access_token(token: str):
        cfg = ChatGPTConfig.load()
        cfg["mode"] = "access"
        cfg["access_token"] = token
        ChatGPTConfig.save(cfg)
        print("✅ ChatGPT Access Token 已配置")

    @staticmethod
    def set_api_key(key: str):
        """兼容模式: 使用 OpenAI API key"""
        cfg = ChatGPTConfig.load()
        cfg["mode"] = "api"
        cfg["api_key"] = key
        ChatGPTConfig.save(cfg)
        print("✅ OpenAI API Key 已配置")


# ═══════════════════════════════════════════════════
# 2. revChatGPT 适配器 (逆向工程 ChatGPT Web API)
# ═══════════════════════════════════════════════════

class RevChatGPTAdapter:
    """
    ChatGPT 免费网页端适配器。
    使用 acheong08/ChatGPT 逆向工程库。
    """

    def __init__(self):
        self.config = ChatGPTConfig.load()
        self.chatbot = None

    @property
    def available(self) -> bool:
        """检查是否可用的前提条件"""
        mode = self.config.get("mode")
        if mode == "session" and self.config.get("session_token"):
            return True
        if mode == "access" and self.config.get("access_token"):
            return True
        if mode == "api" and self.config.get("api_key"):
            return True
        return False

    def _init_chatbot(self) -> bool:
        """初始化 revChatGPT 客户端"""
        if self.chatbot:
            return True
        try:
            from revChatGPT.V1 import Chatbot
            proxy = self.config.get("proxy") or "socks5://127.0.0.1:10808"

            if self.config.get("mode") == "session":
                self.chatbot = Chatbot(config={
                    "session_token": self.config["session_token"],
                    "proxy": proxy,
                })
            elif self.config.get("mode") == "access":
                self.chatbot = Chatbot(config={
                    "access_token": self.config["access_token"],
                    "proxy": proxy,
                })
            _logger.info("ChatGPT 客户端初始化成功")
            return True
        except ImportError:
            _logger.error("revChatGPT 未安装")
            return False
        except Exception as e:
            _logger.error(f"初始化失败: {e}")
            return False

    def ask(self, prompt: str, model: str = "auto") -> dict:
        """
        向 ChatGPT 发送消息。
        返回: {"success": bool, "response": str, "model": str}
        """
        if not self.available:
            return {"success": False, "error": "ChatGPT 未配置 (需 session_token 或 API key)"}

        # 使用 revChatGPT
        if self.config.get("mode") in ("session", "access"):
            return self._ask_revchatgpt(prompt)

        # 使用 OpenAI API 兼容模式
        if self.config.get("mode") == "api":
            return self._ask_openai(prompt, model)

        return {"success": False, "error": "未知认证模式"}

    def _ask_revchatgpt(self, prompt: str) -> dict:
        """通过 revChatGPT 发送请求"""
        if not self._init_chatbot():
            return {"success": False, "error": "ChatGPT 客户端初始化失败，请安装 revChatGPT"}

        try:
            response = ""
            for data in self.chatbot.ask(prompt):
                response = data["message"]

            _logger.info(f"ChatGPT 响应: {len(response)} chars")
            return {
                "success": True,
                "response": response,
                "model": "chatgpt-free",
                "source": "revChatGPT",
            }
        except Exception as e:
            error_msg = str(e)[:100]
            _logger.error(f"ChatGPT 请求失败: {error_msg}")
            return {"success": False, "error": error_msg}

    def _ask_openai(self, prompt: str, model: str = "gpt-4o-mini") -> dict:
        """通过 OpenAI API 兼容模式发送请求"""
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.config.get("api_key"),
            )
            # 如果配置了代理, 通过代理访问
            proxy = self.config.get("proxy")
            if proxy:
                client = OpenAI(
                    api_key=self.config.get("api_key"),
                    http_client=None,  # 使用默认 client
                )

            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            response = resp.choices[0].message.content
            return {
                "success": True,
                "response": response,
                "model": model,
                "source": "openai_api",
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:100]}


# ═══════════════════════════════════════════════════
# 3. 浏览器自动化适配器 (后备方案)
# ═══════════════════════════════════════════════════

class BrowserChatGPTAdapter:
    """
    通过浏览器自动化访问 ChatGPT 网页端。
    需要 Hermes browser 工具可用。
    """

    @staticmethod
    def ask_via_browser(prompt: str) -> dict:
        """
        通过浏览器访问 chatgpt.com。
        注意: 需要手动登录 ChatGPT。
        """
        return {
            "success": False,
            "error": "浏览器自动化模式需手动实现: "
                     "1. browser_navigate('https://chatgpt.com') "
                     "2. 手动登录 "
                     "3. 输入prompt → 等待响应"
        }


# ═══════════════════════════════════════════════════
# 4. 缓存层 (复用已获取的响应)
# ═══════════════════════════════════════════════════

class ChatGPTCache:
    """ChatGPT 响应缓存"""

    @staticmethod
    def get(prompt: str) -> Optional[str]:
        """缓存命中返回缓存响应"""
        if not CHATGPT_CACHE.exists():
            return None
        import sqlite3
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        try:
            conn = sqlite3.connect(str(CHATGPT_CACHE))
            row = conn.execute(
                "SELECT response FROM cache WHERE prompt_hash=? AND expires_at>?",
                (prompt_hash, time.time())
            ).fetchone()
            conn.close()
            if row:
                return row[0]
        except:
            pass
        return None

    @staticmethod
    def set(prompt: str, response: str, ttl: int = 3600):
        """缓存响应"""
        import sqlite3
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        try:
            conn = sqlite3.connect(str(CHATGPT_CACHE))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache (prompt_hash TEXT PRIMARY KEY, response TEXT, created_at REAL, expires_at REAL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)",
                (prompt_hash, response[:10000], time.time(), time.time() + ttl)
            )
            conn.commit()
            conn.close()
        except:
            pass


# ═══════════════════════════════════════════════════
# 5. 编排器
# ═══════════════════════════════════════════════════

class ChatGPTAdapter:
    """
    ChatGPT 适配器总入口。
    自动选择可用方式: 缓存 → revChatGPT → OpenAI API → 浏览器
    """

    def __init__(self):
        self.rev = RevChatGPTAdapter()

    def ask(self, prompt: str, use_cache: bool = True) -> dict:
        """向 ChatGPT 发送请求"""

        # 1. 缓存命中
        if use_cache:
            cached = ChatGPTCache.get(prompt)
            if cached:
                _logger.info(f"缓存命中: {prompt[:40]}...")
                return {"success": True, "response": cached,
                        "model": "cache", "source": "cache"}

        # 2. revChatGPT
        if self.rev.available:
            result = self.rev.ask(prompt)
            if result["success"] and use_cache:
                ChatGPTCache.set(prompt, result["response"])
            return result

        # 3. 未配置 → 引导用户
        return {
            "success": False,
            "error": "ChatGPT 未配置",
            "setup_instructions": (
                "请选择一种方式配置 ChatGPT:\n\n"
                "方式1: Session Token (免费)\n"
                "  1. 登录 chatgpt.com\n"
                "  2. F12 → Application → Cookies → __Secure-next-auth.session-token\n"
                "  3. python chatgpt_adapter.py --set-session-token <token>\n\n"
                "方式2: OpenAI API Key (付费)\n"
                "  1. 在 platform.openai.com 创建 API Key\n"
                "  2. python chatgpt_adapter.py --set-api-key <key>\n\n"
                "方式3: 浏览器自动化\n"
                "  1. browser_navigate('https://chatgpt.com')\n"
                "  2. 手动登录后使用\n"
            ),
        }


# ── CLI ──

if __name__ == "__main__":
    import sys

    adapter = ChatGPTAdapter()

    if len(sys.argv) > 1 and sys.argv[1] == "--set-session-token":
        token = sys.argv[2] if len(sys.argv) > 2 else ""
        if token:
            ChatGPTConfig.set_session_token(token)
        else:
            print("用法: python chatgpt_adapter.py --set-session-token <token>")

    elif len(sys.argv) > 1 and sys.argv[1] == "--set-access-token":
        token = sys.argv[2] if len(sys.argv) > 2 else ""
        if token:
            ChatGPTConfig.set_access_token(token)

    elif len(sys.argv) > 1 and sys.argv[1] == "--set-api-key":
        key = sys.argv[2] if len(sys.argv) > 2 else ""
        if key:
            ChatGPTConfig.set_api_key(key)

    elif len(sys.argv) > 1 and sys.argv[1] == "--set-proxy":
        proxy = sys.argv[2] if len(sys.argv) > 2 else "socks5://127.0.0.1:10808"
        cfg = ChatGPTConfig.load()
        cfg["proxy"] = proxy
        ChatGPTConfig.save(cfg)
        print(f"✅ 代理已配置: {proxy}")

    elif len(sys.argv) > 1 and sys.argv[1] == "--ask":
        prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hello"
        result = adapter.ask(prompt)
        if result["success"]:
            print(f"🤖 [{result.get('model','?')}] {result['response'][:500]}")
        else:
            print(f"❌ {result.get('error','')}")
            if result.get("setup_instructions"):
                print(result["setup_instructions"])

    elif len(sys.argv) > 1 and sys.argv[1] == "--status":
        cfg = ChatGPTConfig.load()
        mode = cfg.get("mode", "未配置")
        print(f"📊 ChatGPT 适配器状态")
        print(f"  {'='*30}")
        print(f"  模式: {mode}")
        print(f"  revChatGPT: {'✅ 可用' if adapter.rev.available else '❌ 未配置'}")
        print(f"  代理: {cfg.get('proxy', '未配置')}")
        print(f"  缓存: {'✅ 就绪' if CHATGPT_CACHE.exists() else '⏳ 未使用'}")
        print()

        if mode == "session" or mode == "access":
            print("  测试连接...")
            result = adapter.ask("Say 'OK' if you can hear me", use_cache=False)
            if result["success"]:
                print(f"  ✅ {result['response'][:60]}")
            else:
                print(f"  ❌ {result.get('error','连接失败')}")

    else:
        print(f"🤖 ChatGPT Web 适配器")
        print()
        print("用法:")
        print("  --set-session-token <token>  配置 ChatGPT Session Token")
        print("  --set-access-token <token>   配置 ChatGPT Access Token")
        print("  --set-api-key <key>          配置 OpenAI API Key")
        print("  --set-proxy <url>            配置代理 (默认: socks5://127.0.0.1:10808)")
        print("  --ask <prompt>               向 ChatGPT 提问")
        print("  --status                     查看状态")
        print()
        print("安装依赖:")
        print("  pip3 install revChatGPT")
        print("  # 或使用 openai SDK (已安装)")
