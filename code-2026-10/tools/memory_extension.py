#!/usr/bin/env python3
"""
Hermes 记忆空间扩展 — Redis 四层记忆架构

参考 Anthropic Claude Code 泄露代码的记忆系统设计：
  - 结构化记忆条目 (type/importance/source/ttl)
  - 四层记忆层级 (工作/短时/长时/向量)
  - 重要性门控 + 衰减 + 合并
  - 跨会话语义检索

架构:
  Tier 1: Working Memory (当前会话, 系统提示注入)        ← MEMORY.md/USER.md 已有
  Tier 2: Short-term Cache (Redis, 24h-7d TTL)          ← hermes_cache.py 扩展
  Tier 3: Long-term Store (Redis Hash, importance持久)   ← 新增: memory_extension.py
  Tier 4: Vector Memory (ChromaDB, 语义检索)             ← 新增: memory_extension.py

使用:
  from memory_extension import MemoryEngine
  me = MemoryEngine()
  
  # 保存高重要性事实
  me.save_fact("用户偏好", "用户喜欢结构化表格回复", importance=0.8)
  
  # 跨会话检索
  results = me.retrieve("微信连接问题", top_k=5)
  
  # 获取当前会话注入块
  context = me.get_context_block("微信连接诊断")

依赖: redis>=4.0, chromadb>=1.5
"""

import json
import logging
import os
import time
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

# ── 配置 ──────────────────────────────────────────

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_MEMORY_DB", "1"))  # 与cache分离
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

# 自动从Hermes .env读取
if not REDIS_PASSWORD:
    for env_path in [
        Path.home() / "AppData/Local/hermes/profiles/mybot/.env",
        Path.home() / "AppData/Local/hermes/.env",
    ]:
        if env_path.exists():
            with open(env_path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("REDIS_PASSWORD="):
                        REDIS_PASSWORD = line.split("=", 1)[1].strip().strip("'\"")
                        break

CHROMA_PATH = os.environ.get("CHROMA_PATH",
    str(Path.home() / "AppData/Local/hermes/chroma_memory"))

# 记忆层级配置
TIER_CONFIG = {
    "working": {"max_entries": 20, "char_limit": 3000},     # 系统提示内
    "short_term": {"ttl": 86400, "max_entries": 200},       # 24h
    "long_term": {"ttl": None, "max_entries": 5000},         # 持久
    "vector": {"top_k": 5, "similarity_min": 0.25},          # 语义
}

# 重要性门控 (Anthropic模式)
IMPORTANCE_THRESHOLDS = {
    "trivial": 0.0,    # 不保存
    "low": 0.3,        # 仅 short-term
    "medium": 0.6,     # short-term + long-term
    "high": 0.8,       # 全部层级
    "critical": 0.95,  # 全部层级 + 标记永久
}

# 衰减参数
DECAY_RATE = 0.05        # 每次合并衰减
DECAY_DAYS = 30          # 未访问30天降级
REINFORCE_BOOST = 0.1    # 再次提及时提升

# ── 日志 ──────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("memory_extension")


# ── Redis 连接 ────────────────────────────────────

_redis_pool = None

def get_redis() -> Optional[Any]:
    """获取Redis连接(带延迟初始化+缓存池)"""
    global _redis_pool
    if _redis_pool is None:
        try:
            import redis as redis_mod
            kwargs = dict(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                decode_responses=True, socket_connect_timeout=3,
                socket_timeout=5, retry_on_timeout=True,
                health_check_interval=30,
            )
            if REDIS_PASSWORD:
                kwargs["password"] = REDIS_PASSWORD
            _redis_pool = redis_mod.Redis(**kwargs)
            _redis_pool.ping()
            logger.info(f"✓ Redis connected ({REDIS_HOST}:{REDIS_PORT}/{REDIS_DB})")
        except Exception as e:
            logger.warning(f"✗ Redis unavailable: {e}")
            _redis_pool = False
    return _redis_pool if _redis_pool is not False else None


def _r() -> Optional[Any]:
    return get_redis()


# ── ChromaDB 向量存储 ─────────────────────────────

_chroma_collection = None

def get_chroma() -> Optional[Any]:
    """获取ChromaDB集合(用于向量语义检索)"""
    global _chroma_collection
    if _chroma_collection is None:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            _chroma_collection = client.get_or_create_collection(
                name="hermes_memory",
                metadata={"hnsw:space": "cosine"},
            )
            # 确保ChromaDB索引存在
            count = _chroma_collection.count()
            logger.info(f"✓ ChromaDB ready ({count} vectors)")
        except Exception as e:
            logger.warning(f"✗ ChromaDB unavailable: {e}")
            _chroma_collection = False
    return _chroma_collection if _chroma_collection is not False else None


# ── 记忆条目结构 ──────────────────────────────────

MEMORY_SCHEMA = {
    "id": str,              # 唯一ID: mem_<sha256[:16]>
    "type": str,            # fact|preference|decision|lesson|context
    "content": str,         # 记忆内容
    "importance": float,    # 0.0-1.0
    "source": str,          # session_id 或 "user" 或 "system"
    "created_at": float,    # timestamp
    "accessed_at": float,   # 最后访问
    "access_count": int,    # 访问次数
    "ttl": Optional[int],   # None=永久
    "tags": List[str],      # 标签
    "expires_at": Optional[float],  # 过期时间
}

VALID_TYPES = {"fact", "preference", "decision", "lesson", "context", "observation"}
VALID_TAGS = {"user_pref", "environment", "workflow", "error", "fix", "tool", 
              "security", "weixin", "gateway", "cron", "skill", "memory"}


# ── 记忆引擎 ──────────────────────────────────────

class MemoryEngine:
    """
    四层记忆引擎 (Anthropic Claude Code模式)
    
    使用方式:
        me = MemoryEngine()
        me.save("fact", "用户偏好结构化输出", importance=0.8, tags=["user_pref"])
        ctx = me.retrieve_context("用户偏好的输出格式")
    """

    def __init__(self):
        self._r = _r()
        self._chroma = get_chroma()
        self._embed_cache = {}

    # ── 公开API ──────────────────────────────────────

    def save(self,
             type_: str,
             content: str,
             importance: float = 0.5,
             source: str = "current",
             tags: Optional[List[str]] = None,
             ttl: Optional[int] = None) -> Dict[str, Any]:
        """
        保存一条记忆 (自动路由到合适层级)
        
        Args:
            type_: 类型 (fact|preference|decision|lesson|context|observation)
            content: 记忆内容
            importance: 重要性 0.0-1.0
            source: 来源session
            tags: 标签列表
            ttl: 过期秒数 (None=自动)
        
        Returns: {id, tier, success}
        """
        if type_ not in VALID_TYPES:
            type_ = "observation"
        
        if not content or len(content.strip()) < 5:
            return {"success": False, "error": "内容太短"}
        
        importance = max(0.0, min(1.0, importance))
        tags = tags or []
        
        # 生成唯一ID
        mem_id = self._make_id(content)
        
        # 构建条目
        now = time.time()
        entry = {
            "id": mem_id,
            "type": type_,
            "content": content.strip(),
            "importance": importance,
            "source": source,
            "created_at": now,
            "accessed_at": now,
            "access_count": 1,
            "ttl": ttl,
            "tags": tags,
            "expires_at": (now + ttl) if ttl else None,
        }
        
        # 按重要性路由到不同层级
        tiers_written = []
        
        # Tier 2: Short-term (always, TTL=24h)
        if self._r:
            try:
                st_key = f"mem:st:{mem_id}"
                # Redis 3.0 不支持 mapping= 关键字，用位置参数
                for k, v in entry.items():
                    self._r.hset(st_key, k, self._serialize(v))
                self._r.expire(st_key, ttl or TIER_CONFIG["short_term"]["ttl"])
                # 加入类型索引
                self._r.sadd(f"mem:idx:type:{type_}", mem_id)
                self._r.sadd("mem:idx:all", mem_id)
                # 标签索引
                for tag in tags:
                    self._r.sadd(f"mem:idx:tag:{tag}", mem_id)
                tiers_written.append("short_term")
            except Exception as e:
                logger.warning(f"Redis short-term write failed: {e}")
        
        # Tier 3: Long-term (importance >= 0.3)
        if importance >= IMPORTANCE_THRESHOLDS["low"] and self._r:
            try:
                lt_key = f"mem:lt:{mem_id}"
                entry_lt = dict(entry)
                if importance >= IMPORTANCE_THRESHOLDS["high"]:
                    entry_lt["ttl"] = None  # 高重要性永久保留
                    entry_lt["expires_at"] = None
                # Redis 3.0 兼容: 逐个字段写入
                for k, v in entry_lt.items():
                    self._r.hset(lt_key, k, self._serialize(v))
                if entry_lt.get("ttl"):
                    self._r.expire(lt_key, entry_lt["ttl"])
                # 重要度排序集
                self._r.zadd("mem:lt:by_importance", {mem_id: importance})
                tiers_written.append("long_term")
            except Exception as e:
                logger.warning(f"Redis long-term write failed: {e}")
        
        # Tier 4: Vector (importance >= 0.6)
        if importance >= IMPORTANCE_THRESHOLDS["medium"] and self._chroma:
            try:
                self._chroma_add(mem_id, content, {
                    "type": type_,
                    "importance": importance,
                    "source": source,
                    "tags": ",".join(tags),
                    "created_at": now,
                })
                tiers_written.append("vector")
            except Exception as e:
                logger.warning(f"ChromaDB write failed: {e}")
        
        return {
            "success": True,
            "id": mem_id,
            "tiers": tiers_written,
            "importance": importance,
        }

    def save_fact(self, content: str, importance: float = 0.6,
                  tags: Optional[List[str]] = None, source: str = "system"):
        """快捷保存事实性知识"""
        return self.save("fact", content, importance=importance, 
                        tags=tags, source=source)

    def save_preference(self, content: str, importance: float = 0.7,
                        source: str = "user"):
        """快捷保存用户偏好"""
        return self.save("preference", content, importance=importance,
                        tags=["user_pref"], source=source)

    def save_lesson(self, content: str, importance: float = 0.7,
                    tags: Optional[List[str]] = None):
        """快捷保存经验教训"""
        return self.save("lesson", content, importance=importance,
                        tags=(tags or []) + ["lesson"])

    # ── 检索 ────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 5,
                 min_importance: float = 0.0,
                 type_filter: Optional[str] = None,
                 tag_filter: Optional[str] = None) -> List[Dict]:
        """
        多层级检索 (Anthropic模式: 向量优先 + Redis回退)
        
        1. 向量检索 (ChromaDB) → 语义最相关
        2. Redis keyword匹配 → 精确匹配
        3. 合并 + 去重 + 排序
        """
        results = []
        seen_ids = set()
        
        # Tier 4: 向量检索 (语义)
        if self._chroma:
            try:
                vector_results = self._chroma_query(query, top_k)
                for vr in vector_results:
                    mem_id = vr.get("id", "")
                    if mem_id and mem_id not in seen_ids:
                        seen_ids.add(mem_id)
                        # 从Redis获取完整条目
                        full = self._get_full_entry(mem_id)
                        if full:
                            full["_score"] = vr.get("distance", 0)
                            full["_retrieval"] = "vector"
                            results.append(full)
            except Exception as e:
                logger.debug(f"Vector retrieval failed: {e}")
        
        # Tier 3/2: Redis关键词检索
        if self._r:
            try:
                # 在long-term中搜索
                keyword_results = self._redis_search(query, seen_ids)
                results.extend(keyword_results)
            except Exception as e:
                logger.debug(f"Redis search failed: {e}")
        
        # 排序: 重要度 * 相关性
        results.sort(key=lambda x: (
            x.get("importance", 0) * 0.4 + 
            (1.0 - x.get("_score", 0.5)) * 0.6
        ), reverse=True)
        
        # 过滤
        if type_filter:
            results = [r for r in results if r.get("type") == type_filter]
        if tag_filter:
            results = [r for r in results if tag_filter in r.get("tags", [])]
        if min_importance > 0:
            results = [r for r in results if r.get("importance", 0) >= min_importance]
        
        # 更新访问计数
        for r in results[:top_k]:
            self._touch(r.get("id", ""))
        
        return results[:top_k]

    def retrieve_context(self, query: str, top_k: int = 5) -> str:
        """
        获取格式化的记忆上下文块 (用于注入系统提示)
        
        返回 Markdown 格式的 [Memory Context] 块
        """
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return ""
        
        lines = ["\n[Memory Context — 相关历史记忆]"]
        for i, r in enumerate(results[:top_k], 1):
            content = r.get("content", "")
            importance = r.get("importance", 0)
            type_ = r.get("type", "?")
            tags = r.get("tags", [])
            source = r.get("source", "?")[:16]
            
            # 截取过长的内容
            if len(content) > 200:
                content = content[:197] + "..."
            
            importance_bar = "█" * int(importance * 10) + "░" * (10 - int(importance * 10))
            tag_str = f" [{','.join(tags[:3])}]" if tags else ""
            
            lines.append(f"  [{i}] [{type_}] ⭐{importance:.1f} {importance_bar}{tag_str}")
            lines.append(f"       {content}")
        
        lines.append("[/Memory Context]")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计"""
        stats = {"tiers": {}}
        
        if self._r:
            try:
                st_count = self._r.scard("mem:idx:all") or 0
                lt_count = len(self._r.zrange("mem:lt:by_importance", 0, -1)) if self._r.exists("mem:lt:by_importance") else 0
                info = self._r.info()
                stats["tiers"]["short_term"] = st_count
                stats["tiers"]["long_term"] = lt_count
                stats["redis_memory"] = info.get("used_memory_human", "?")
                stats["redis_keys"] = self._r.dbsize()
            except Exception as e:
                stats["redis_error"] = str(e)
        
        if self._chroma:
            try:
                stats["tiers"]["vector"] = self._chroma.count()
            except Exception as e:
                stats["chroma_error"] = str(e)
        
        return stats

    # ── 维护 ────────────────────────────────────────

    def consolidate(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        记忆合并 (Anthropic模式)
        
        1. 低重要性降级 → short-term TTL延长
        2. 同类条目合并 → 生成综合摘要
        3. 衰减计算 → 长期未访问降低重要度
        4. 过期清理
        """
        report = {
            "downgraded": 0,
            "merged": 0,
            "decayed": 0,
            "purged": 0,
            "errors": [],
        }
        
        if not self._r:
            return report
        
        now = time.time()
        
        try:
            # Step 1: 衰减扫描 (长期存储)
            lt_ids = self._r.zrange("mem:lt:by_importance", 0, -1)
            for mem_id in lt_ids:
                lt_key = f"mem:lt:{mem_id}"
                entry = self._r.hgetall(lt_key)
                if not entry:
                    continue
                
                entry = {k: self._deserialize(k, v) for k, v in entry.items()}
                accessed_at = entry.get("accessed_at", 0)
                importance = entry.get("importance", 0.5)
                age_days = (now - accessed_at) / 86400
                
                # 长期未访问 → 降低重要度
                if age_days > DECAY_DAYS and importance > 0.3:
                    new_importance = max(0.1, importance - DECAY_RATE * (age_days / DECAY_DAYS))
                    if not dry_run:
                        entry["importance"] = new_importance
                        self._r.hset(lt_key, "importance", str(new_importance))
                        self._r.zadd("mem:lt:by_importance", {mem_id: new_importance})
                    report["decayed"] += 1
                
                # 重要度低于阈值 → 降级到short-term
                if importance < IMPORTANCE_THRESHOLDS["low"] and not dry_run:
                    # 移到short-term
                    st_key = f"mem:st:{mem_id}"
                    self._r.hset(st_key, mapping={k: self._serialize(v) for k, v in entry.items()})
                    self._r.expire(st_key, TIER_CONFIG["short_term"]["ttl"])
                    # 从long-term移除
                    self._r.delete(lt_key)
                    self._r.zrem("mem:lt:by_importance", mem_id)
                    report["downgraded"] += 1
            
            # Step 2: 过期清理 (short-term)
            # Redis TTL自动处理过期, 但需要清理索引
            st_ids = self._r.smembers("mem:idx:all") or set()
            for mem_id in list(st_ids)[:500]:  # 限制每次检查数量
                if not self._r.exists(f"mem:st:{mem_id}") and not self._r.exists(f"mem:lt:{mem_id}"):
                    self._r.srem("mem:idx:all", mem_id)
                    self._r.srem(f"mem:idx:type:{entry.get('type', 'unknown')}", mem_id)
                    report["purged"] += 1
            
        except Exception as e:
            logger.error(f"Consolidation error: {e}")
            report["errors"].append(str(e))
        
        return report

    # ── 内部方法 ────────────────────────────────────

    def _make_id(self, content: str) -> str:
        """基于内容生成唯一ID"""
        raw = f"{content.strip()}:{time.time():.0f}"
        return "mem_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _serialize(self, value: Any) -> str:
        """序列化Redis Hash值"""
        if isinstance(value, (list, tuple)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, float):
            return str(value)
        if value is None:
            return ""
        return str(value)

    def _deserialize(self, key: str, value: Any) -> Any:
        """反序列化Redis Hash值"""
        if key in ("tags",):
            try:
                return json.loads(value) if value else []
            except (json.JSONDecodeError, TypeError):
                return []
        if key in ("importance", "created_at", "accessed_at", "expires_at"):
            try:
                return float(value) if value else 0.0
            except (ValueError, TypeError):
                return 0.0
        if key in ("access_count",):
            try:
                return int(value) if value else 0
            except (ValueError, TypeError):
                return 0
        return value

    def _get_full_entry(self, mem_id: str) -> Optional[Dict]:
        """从Redis获取完整条目(先查long-term再查short-term)"""
        if not self._r:
            return None
        
        for prefix in ["lt", "st"]:
            raw = self._r.hgetall(f"mem:{prefix}:{mem_id}")
            if raw:
                entry = {}
                for k, v in raw.items():
                    entry[k] = self._deserialize(k, v)
                return entry
        return None

    def _touch(self, mem_id: str):
        """更新访问时间和计数"""
        if not self._r:
            return
        for prefix in ["lt", "st"]:
            key = f"mem:{prefix}:{mem_id}"
            if self._r.exists(key):
                try:
                    self._r.hincrby(key, "access_count", 1)
                    self._r.hset(key, "accessed_at", str(time.time()))
                except Exception:
                    pass

    def _redis_search(self, query: str, seen_ids: set) -> List[Dict]:
        """Redis关键词搜索 (TF回退)"""
        results = []
        keywords = set(re.findall(r'\w+', query.lower()))
        if len(keywords) < 2:
            return results
        
        # 在long-term中搜索
        lt_ids = self._r.zrange("mem:lt:by_importance", 0, -1) or []
        for mem_id in lt_ids:
            if mem_id in seen_ids:
                continue
            entry = self._get_full_entry(mem_id)
            if not entry:
                continue
            
            content = entry.get("content", "").lower()
            # 简单关键词匹配
            match_count = sum(1 for kw in keywords if kw in content)
            if match_count >= 1:  # 至少匹配1个关键词
                score = 1.0 - (match_count / max(len(keywords), 1))
                entry["_score"] = score
                entry["_retrieval"] = "keyword"
                seen_ids.add(mem_id)
                results.append(entry)
        
        return results

    def _chroma_add(self, mem_id: str, content: str, metadata: dict):
        """向ChromaDB添加向量"""
        if not self._chroma:
            return
        self._chroma.add(
            ids=[mem_id],
            documents=[content],
            metadatas=[metadata],
        )

    def _chroma_query(self, query: str, top_k: int) -> List[Dict]:
        """从ChromaDB检索"""
        if not self._chroma:
            return []
        try:
            results = self._chroma.query(
                query_texts=[query],
                n_results=min(top_k * 2, 20),
            )
            ids = results.get("ids", [[]])[0] if results.get("ids") else []
            distances = results.get("distances", [[]])[0] if results.get("distances") else []
            metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            
            output = []
            for i, mid in enumerate(ids):
                dist = distances[i] if i < len(distances) else 1.0
                # cosine距离→相似度
                similarity = 1.0 - dist
                if similarity >= TIER_CONFIG["vector"]["similarity_min"]:
                    output.append({
                        "id": mid,
                        "distance": similarity,
                        "metadata": metadatas[i] if i < len(metadatas) else {},
                    })
            return output
        except Exception as e:
            logger.debug(f"ChromaDB query error: {e}")
            return []

    def clear_all(self, confirm: bool = False):
        """清空所有记忆 (危险操作)"""
        if not confirm:
            return {"success": False, "error": "需要 confirm=True"}
        
        if self._r:
            try:
                self._r.flushdb()
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if self._chroma:
            try:
                self._chroma.delete(where={})
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        return {"success": True, "message": "所有记忆已清空"}


# ── 记忆注入器 (用于系统提示) ────────────────────

class MemoryInjector:
    """
    会话级记忆注入器
    
    在每轮LLM调用前, 用当前query检索相关记忆并格式化为context block。
    用法:
        injector = MemoryInjector()
        ctx = injector.inject("用户问题")
        # → 追加到system prompt
    """
    
    def __init__(self):
        self.engine = MemoryEngine()
        self._session_memory = []  # 当前会话记忆缓存
    
    def inject(self, query: str, top_k: int = 3) -> str:
        """生成注入块"""
        context = self.engine.retrieve_context(query, top_k=top_k)
        return context
    
    def record_interaction(self, query: str, response: str, 
                          importance: float = 0.3):
        """记录一次交互到短期记忆"""
        content = f"Q: {query[:200]} → A: {response[:200]}"
        self.engine.save("context", content, importance=importance,
                        source="session")
        self._session_memory.append({
            "query": query[:100],
            "time": time.time(),
        })


# ── 诊断工具 ──────────────────────────────────────

def diagnose() -> Dict[str, Any]:
    """完整诊断报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "redis": {"status": "unknown"},
        "chroma": {"status": "unknown"},
        "memory": {},
    }
    
    # Redis
    r = _r()
    if r:
        try:
            info = r.info()
            report["redis"] = {
                "status": "connected",
                "version": info.get("redis_version"),
                "memory_used": info.get("used_memory_human"),
                "total_keys": r.dbsize(),
                "uptime_days": info.get("uptime_in_seconds", 0) // 86400,
            }
        except Exception as e:
            report["redis"] = {"status": "error", "error": str(e)}
    else:
        report["redis"] = {"status": "not_available"}
    
    # ChromaDB
    c = get_chroma()
    if c is not False and c is not None:
        try:
            count = c.count()
            report["chroma"] = {"status": "connected", "vectors": count}
        except Exception as e:
            report["chroma"] = {"status": "error", "error": str(e)}
    else:
        report["chroma"] = {"status": "not_available"}
    
    # 记忆统计
    me = MemoryEngine()
    report["memory"] = me.get_stats()
    
    return report


# ── 自测 / CLI ────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if "--diagnose" in sys.argv:
        report = diagnose()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0)
    
    if "--clear" in sys.argv:
        me = MemoryEngine()
        result = me.clear_all(confirm="--force" in sys.argv)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    
    print("=" * 50)
    print("Hermes Memory Extension — 自测")
    print("=" * 50)
    
    me = MemoryEngine()
    
    # Test 1: 保存
    print("\n1. 保存测试...")
    r1 = me.save_fact("用户喜欢结构化表格回复和Mermaid图表", 
                      importance=0.8, tags=["user_pref"])
    print(f"   ✓ {r1}")
    
    r2 = me.save_lesson("WeChat iLink API需要ssl.CERT_NONE绕过自签名证书",
                        importance=0.85, tags=["weixin", "fix"])
    print(f"   ✓ {r2}")
    
    r3 = me.save("preference", "用户偏好代码优先模式",
                 importance=0.7, tags=["user_pref", "workflow"])
    print(f"   ✓ {r3}")
    
    # Test 2: 检索
    print("\n2. 检索测试...")
    results = me.retrieve("表格和图表输出风格")
    print(f"   ✓ {len(results)} results")
    for r in results:
        print(f"     [{r.get('type','?')}] ⭐{r.get('importance',0):.1f} {r.get('content','')[:60]}...")
    
    # Test 3: 上下文块
    print("\n3. 上下文注入块:")
    ctx = me.retrieve_context("微信连接问题")
    print(ctx if ctx else "   (无相关记忆)")
    
    # Test 4: 统计
    print("\n4. 系统统计:")
    stats = me.get_stats()
    print(f"   Redis: {json.dumps(stats.get('tiers',{}), ensure_ascii=False)}")
    
    # Test 5: 诊断
    print("\n5. 完整诊断:")
    diag = diagnose()
    print(f"   Redis: {diag['redis'].get('status','?')} ({diag['redis'].get('total_keys',0)} keys)")
    print(f"   Chroma: {diag['chroma'].get('status','?')} ({diag['chroma'].get('vectors',0)} vectors)")
    
    print("\n✅ 自测完成")
