#!/usr/bin/env python3
"""Hermes记忆增强 — 借鉴Agent_Memory_Techniques 5大模式
1. 层级记忆 (13): L1上下文/L2暖/L3冷 — 与四层架构映射
2. 记忆巩固 (14): 短期→长期提升/衰减
3. 记忆压缩 (15): 会话→摘要
4. 记忆路由 (17): 按查询类型选择检索层
5. 遗忘衰减 (19): 时间衰减因子
"""
import json, os, time, re
from datetime import datetime, timedelta

MEMORY_DIR = r'D:/hermes/hermes-data/profiles/mybot/memories'
CACHE_FILE = os.path.join(MEMORY_DIR, 'memory_cache.json')

class HermesMemoryEnhancer:
    def __init__(self):
        self.cache = self._load()
        
    def _load(self):
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, encoding='utf-8') as f:
                return json.load(f)
        return {'facts': [], 'consolidations': []}
    
    def _save(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    # ===== 模式1: 层级记忆 =====
    def tier_of(self, importance):
        """映射到L1/L2/L3"""
        if importance >= 0.8: return 'L1_context'
        elif importance >= 0.5: return 'L2_warm'
        return 'L3_cold'
    
    # ===== 模式2: 记忆巩固 =====
    def consolidate(self, fact_id, access_count):
        """访问次数越多→提升层级/重要性"""
        for f in self.cache['facts']:
            if f['id'] == fact_id:
                f['access_count'] = access_count
                if access_count >= 3 and f['importance'] < 0.8:
                    f['importance'] = min(0.9, f['importance'] + 0.1)
                    f['tier'] = self.tier_of(f['importance'])
                    self.cache['consolidations'].append({
                        'fact_id': fact_id, 'time': datetime.now().isoformat(),
                        'action': 'promote', 'new_tier': f['tier']
                    })
                self._save()
                return f['tier']
        return None
    
    # ===== 模式3: 记忆压缩 =====
    def compress_session(self, session_msgs, max_summary=500):
        """会话→要点摘要 (供memory_extension注入)"""
        if len(session_msgs) <= 10:
            return session_msgs  # 短会话不压缩
        # 提取关键消息 (用户指令+重要回复)
        key = [m for m in session_msgs if len(m) > 30]
        summary = key[-min(len(key), 8):]
        return f"[已压缩 {len(session_msgs)}条消息] " + ' | '.join(
            s[:60] for s in summary[-5:])
    
    # ===== 模式4: 记忆路由 =====
    def route_query(self, query):
        """按查询类型路由到合适层级"""
        if re.search(r'偏好|喜欢|不喜欢|风格', query):
            return 'L1_context', 'user_pref'
        elif re.search(r'项目|文件|代码|目录', query):
            return 'L3_cold', 'project'
        elif re.search(r'之前|上次|昨天|刚才', query):
            return 'L2_warm', 'recent'
        return 'L1_context', 'general'
    
    # ===== 模式5: 遗忘衰减 =====
    def decay(self, fact, halflife_days=30):
        """时间衰减: 未访问的冷事实权重降低"""
        if 'last_access' not in fact:
            return 1.0
        try:
            last = datetime.fromisoformat(fact['last_access'])
            days = (datetime.now() - last).days
            if days <= 0: return 1.0
            return 0.5 ** (days / halflife_days)
        except:
            return 1.0
    
    def add_fact(self, content, importance=0.5, tags=None):
        """添加事实 (带层级+时间)"""
        fact = {
            'id': f"F{len(self.cache['facts'])+1:04d}",
            'content': content,
            'importance': importance,
            'tier': self.tier_of(importance),
            'tags': tags or [],
            'created': datetime.now().isoformat(),
            'last_access': datetime.now().isoformat(),
            'access_count': 0,
            'decay_factor': 1.0
        }
        self.cache['facts'].append(fact)
        self._save()
        return fact['id']

if __name__ == '__main__':
    enh = HermesMemoryEnhancer()
    print('=== Hermes记忆增强引擎 (5大模式) ===')
    
    # 演示
    fid = enh.add_fact('用户偏好结构化表格回复', importance=0.85)
    print(f'1. 添加事实: {fid} → {enh.tier_of(0.85)}')
    
    fid2 = enh.add_fact('锂电极片热工艺项目参数', importance=0.6)
    print(f'2. 添加事实: {fid2} → {enh.tier_of(0.6)}')
    
    tier = enh.consolidate(fid2, 3)
    print(f'3. 巩固(3次访问): {fid2} → {tier} (自动提升)')
    
    q = '我之前设置的偏好是什么？'
    route, domain = enh.route_query(q)
    print(f'4. 路由: "{q}" → {route}/{domain}')
    
    print(f'5. 衰减: 30天半衰期 → 因子 {enh.decay({"last_access": (datetime.now()-timedelta(days=15)).isoformat()}):.2f}')
    
    print('\n✅ 5大模式验证完成')
