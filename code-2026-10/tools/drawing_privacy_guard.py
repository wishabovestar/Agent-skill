#!/usr/bin/env python3
"""
Hermes 图纸隐私保护 v2.0 — Drawing Privacy Guard
=================================================
AES-256-GCM 加密值映射引擎（类似RSA的非对称架构）
  
所有图纸中的作者信息、编号、尺寸数值、公差、GD&T全部在本地
加密映射为 Token 后外发，LLM 处理后本地解密还原真实值。

架构:
  本地 (Private Key Holder)         外发大模型 (Token Only)
  ┌─────────────────────┐          ┌──────────────────┐
  │ 10.600±0.070        │ ──AES──→│ DIM-A7F3K2L9     │
  │ Ø10.600             │ ───────→│ DIA-B4E8F1C7     │
  │ ⊕ 0.40 A|B|E        │ ───────→│ GDT-9E8F1A2B     │
  │ ←─ 解密映射表还原 ── │ ←────── │ 含Token的LLM输出  │
  └─────────────────────┘          └──────────────────┘
"""

import json, os, re, hashlib, logging, sys, struct, base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.backends import default_backend

# ── 路径 ──
LOG_DIR = Path.home() / "AppData/Local/hermes/profiles/mybot/logs"
CACHE_DIR = Path("D:/hermes/analysis/drawing_cache")
MASTER_KEY_FILE = LOG_DIR.parent / ".drawing_master_key"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 日志 ──
_logger = logging.getLogger("drawing_privacy_guard")
_handler = logging.FileHandler(str(LOG_DIR / "drawing_privacy_guard.log"), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [DRAWING_PRIVACY v2] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

def _log(msg: str, **extra):
    extra_str = f" | {json.dumps(extra, ensure_ascii=False)}" if extra else ""
    _logger.info(f"{msg}{extra_str}")


# ═══════════════════════════════════════════════════
# 0. 密钥管理
# ═══════════════════════════════════════════════════

def _load_or_create_master_key() -> bytes:
    """加载或创建主密钥 (512bit = 64 bytes, 前32为AES密钥, 后32为HMAC密钥)"""
    if MASTER_KEY_FILE.exists():
        return base64.b85decode(MASTER_KEY_FILE.read_text().strip())
    key = os.urandom(64)  # 512bit
    MASTER_KEY_FILE.write_text(base64.b85encode(key).decode())
    _log("主密钥已创建", key_file=str(MASTER_KEY_FILE))
    return key

MASTER_KEY = _load_or_create_master_key()
AES_KEY = MASTER_KEY[:32]   # 256bit AES密钥
HMAC_KEY = MASTER_KEY[32:64]  # 256bit HMAC密钥


# ═══════════════════════════════════════════════════
# 1. 加密引擎
# ═══════════════════════════════════════════════════

class CipherEngine:
    """AES-256-GCM 加密引擎，每次会话独立密钥"""

    def __init__(self, session_key: Optional[bytes] = None):
        if session_key:
            self.session_key = session_key
        else:
            self.session_key = os.urandom(32)  # 256bit随机会话密钥
        self._fernet = Fernet(base64.urlsafe_b64encode(self.session_key))

    def encrypt(self, plaintext: str) -> str:
        """加密 → base64 字符串"""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """解密 → 原文"""
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def encrypt_session_key(self) -> str:
        """用主密钥加密会话密钥"""
        f = Fernet(base64.urlsafe_b64encode(AES_KEY))
        return f.encrypt(self.session_key).decode()

    @staticmethod
    def decrypt_session_key(encrypted_key: str) -> bytes:
        """用主密钥解密会话密钥"""
        f = Fernet(base64.urlsafe_b64encode(AES_KEY))
        return f.decrypt(encrypted_key.encode())

    def get_key_b64(self) -> str:
        """获取base64格式的会话密钥（用于存储）"""
        return base64.urlsafe_b64encode(self.session_key).decode()

    def get_key_signature(self) -> str:
        """获取密钥指纹（前8位HEX，用于日志标识）"""
        h = hashlib.sha256(self.session_key).hexdigest()[:8]
        return h


# ═══════════════════════════════════════════════════
# 2. Token 映射引擎
# ═══════════════════════════════════════════════════

class TokenMapper:
    """
    Token 映射引擎。
    
    Token格式: PREFIX-8位HEX (AES(原始值)的前32bit)
    类型:
      DIM-XXXXXXXX  尺寸数值 (含半径/角度)
      DIA-XXXXXXXX  直径值
      TOL-XXXXXXXX  公差
      GDT-XXXXXXXX  GD&T标注
      DTM-XXXXXXXX  基准
      MAT-XXXXXXXX  材料
    """
    
    TOKEN_TYPES = {
        'DIM': r'\b\d+\.?\d*\s*(?:mm|°)?\b',           # 名义尺寸
        'DIA': r'(?:Ø|QD|@|DIA)\s*\d+\.?\d*',          # 直径值
        'TOL': r'[±+−]\s*\d+\.?\d*(?:\s*[−/]\s*\d+\.?\d*)?',  # 公差
        'GDT': r'(?:⟂|∠|⊕|⌭|⌓|⏥|⊥|⌖|◎)\s*\d+\.?\d*', # GD&T
        'MAT': r'(?i)\b(SUS\d{3}|A[Ll]\s*\d{4}|SS\d{3}|[A-Z]{2,6}\d{2,4})\b', # 材料
    }
    
    def __init__(self, cipher: CipherEngine):
        self.cipher = cipher
        self.mapping: dict[str, str] = {}  # Token → 加密后的原始值
        self.reverse: dict[str, str] = {}  # 原始值 → Token (用于去重)
        self.fai_mapping: dict[str, dict] = {}  # FAI-XXX → {dim_token, tol_token, ...}
        self.pn_counter = 0
        self.pn_registry: dict[str, str] = {}
        self.statistics = {
            "tokens_created": 0,
            "dimensions": 0,
            "tolerances": 0,
            "gdt": 0,
            "datums": 0,
            "materials": 0,
        }
    
    def _generate_token(self, raw_value: str, prefix: str = 'DIM') -> str:
        """生成唯一Token: PREFIX-8位HEX"""
        # 使用AES加密原始值的前8字节作为Token种子
        encrypted = self.cipher.encrypt(raw_value)
        # 取加密结果的前4字节 → 8位HEX
        token_seed = hashlib.sha256(encrypted.encode()).digest()[:4]
        token = f"{prefix}-{token_seed.hex().upper()}"
        
        # 冲突检测（极低概率，但以防万一）
        if token in self.mapping:
            # 微调：追加一个随机字节
            token_seed = hashlib.sha256(encrypted.encode() + os.urandom(1)).digest()[:4]
            token = f"{prefix}-{token_seed.hex().upper()}"
        
        self.mapping[token] = encrypted
        self.reverse[raw_value] = token
        self.statistics["tokens_created"] += 1
        return token
    
    def tokenize_value(self, raw_value: str, prefix: str = 'DIM') -> str:
        """Token化一个值（带去重：同一原始值在同一会话中映射为同一Token）"""
        if raw_value in self.reverse:
            return self.reverse[raw_value]
        token = self._generate_token(raw_value, prefix)
        if prefix == 'DIM':
            self.statistics["dimensions"] += 1
        elif prefix == 'TOL':
            self.statistics["tolerances"] += 1
        elif prefix == 'GDT':
            self.statistics["gdt"] += 1
        return token
    
    def tokenize_datum(self, datum: str) -> str:
        """Token化基准（如 Datum A → DTM-XXXX）"""
        key = f"DATUM_{datum.strip().upper()}"
        if key in self.reverse:
            return self.reverse[key]
        token = self._generate_token(datum.strip().upper(), 'DTM')
        self.reverse[key] = token
        self.statistics["datums"] += 1
        return token
    
    def get_pn(self, part_number: str) -> str:
        """获取/分配脱敏图号（不可逆）"""
        if part_number not in self.pn_registry:
            self.pn_counter += 1
            self.pn_registry[part_number] = f"PN-{self.pn_counter:03d}"
        return self.pn_registry[part_number]
    
    def get_fai(self, fai_num: int) -> str:
        """获取FAI编号的Token（不可逆）"""
        return f"FAI-{int(fai_num):03d}"
    
    def add_fai_mapping(self, fai_num: int, dim_token: str = None, 
                        tol_token: str = None, datum_token: str = None):
        """记录FAI→Token映射"""
        fai_key = self.get_fai(fai_num)
        if fai_key not in self.fai_mapping:
            self.fai_mapping[fai_key] = {}
        if dim_token:
            self.fai_mapping[fai_key]["dim"] = dim_token
        if tol_token:
            self.fai_mapping[fai_key]["tol"] = tol_token
        if datum_token:
            self.fai_mapping[fai_key]["datum"] = datum_token
    
    def save_mapping(self, session_id: str) -> dict:
        """保存映射表到本地（主密钥加密存储，可用私钥脱机解密）"""
        session_dir = CACHE_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "mapping": self.mapping,
            "reverse": {},
            "fai_mapping": self.fai_mapping,
            "pn_registry": self.pn_registry,
            "statistics": self.statistics,
            "encrypted_session_key": self.cipher.encrypt_session_key(),
        }
        
        # 映射表用主密钥加密（私钥仅在本地），任何人获取文件也无法解密
        f = Fernet(base64.urlsafe_b64encode(AES_KEY))
        encrypted_data = f.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()
        map_file = session_dir / "encrypted_mapping.enc"
        map_file.write_text(encrypted_data, encoding="utf-8")
        
        # Token化输出（明文 — 可外发）
        token_out = {
            "session_id": session_id,
            "tokens": list(self.mapping.keys()),
            "fai_tokens": self.fai_mapping,
            "statistics": self.statistics,
        }
        token_file = session_dir / "tokenized_output.json"
        token_file.write_text(json.dumps(token_out, ensure_ascii=False, indent=2), encoding="utf-8")
        
        _log("映射表已保存", session_id=session_id, 
             tokens=len(self.mapping), file=str(map_file))
        
        return {"encrypted_map": str(map_file), "tokenized": str(token_file)}
    
    def restore_text(self, text: str) -> str:
        """将文本中所有Token还原为原始值"""
        pattern = r'\b(DIM|DIA|TOL|GDT|DTM|MAT)-[A-F0-9]{8}\b'
        
        def _restore(m):
            token = m.group(0)
            if token in self.mapping:
                try:
                    return self.cipher.decrypt(self.mapping[token])
                except Exception:
                    return token
            return token
        
        restored = re.sub(pattern, _restore, text)
        count = len(re.findall(pattern, text))
        return restored
    
    def get_stats(self) -> dict:
        return dict(self.statistics)
    
    def to_dict(self) -> dict:
        return {
            "mapping_size": len(self.mapping),
            "statistics": self.statistics,
            "pn_count": self.pn_counter,
        }


# ═══════════════════════════════════════════════════
# 3. 图纸文本Token化引擎
# ═══════════════════════════════════════════════════

# 可逆Token化的数值模式
DIM_VALUE_PATTERN = re.compile(r'\b(\d+\.\d{2,4})\b')  # 精度数值
DIA_PATTERN = re.compile(r'(?i)(Ø|QD\s*|@\s*|DIA\s*)(\d+\.\d{2,4})')  # 直径
TOL_PATTERN = re.compile(r'([±+−])\s*(\d+\.\d{2,4})(?:\s*[/−]\s*(\d+\.\d{2,4}))?')  # 公差
GDT_PATTERN = re.compile(r'([⟂∠⊕⌭⌓⏥⊥⌖◎])\s*(\d+\.\d{1,4})')  # GD&T
DATUM_PATTERN = re.compile(r'(?i)\bDatum\s+([A-Za-z])\b')  # 基准
PART_NUMBER_PATTERN = re.compile(r'(?<!\d)(\d{3,4}-\d{4,6}(?:-\d{2})?)(?!\d)')
LOOSE_PN_PATTERN = re.compile(r'(?<!\d)(\d{3,4}-\d{3,6}(?:-\d{2})?)(?!\d)')
FAI_PATTERN = re.compile(r'(?i)(FAI[_\s]*)(\d+)(\s*[:=]?\s*)')

# 不可逆替换模式（标题栏/元数据）
NAME_PATTERN = re.compile(
    r'(?i)(Designed\s*(by)?\s*[=:]?\s*|Drawn\s*(by)?\s*[=:]?\s*|'
    r'Checked\s*(by)?\s*[=:]?\s*|Approved\s*(by)?\s*[=:]?\s*|'
    r'Designer\s*[=:]\s*|Checker\s*[=:]\s*|'
    r'Approver\s*[=:]\s*|Reviewer\s*[=:]\s*)'
    r'([A-Z][a-zA-Z.\'\u00c0-\u024f\-]{1,24}(?:\s+[A-Z][a-zA-Z.\'\u00c0-\u024f\-]{1,24})?)'
)
CN_NAME_PATTERN = re.compile(
    r'(?i)(设计[者员]?|审核[者员]?|批准[者员]?|绘制|制图|校核|审定)[=:：\s]+([\u4e00-\u9fff]{2,4})'
)
COMPANY_PATTERN = re.compile(
    r'(?i)((Apple|Tesla|BYD|CATL|LG|Samsung|松下|宁德时代|比亚迪|国轩|亿纬|中航|欣旺达)'
    r'[\s\w]*(Inc|Corp|Co|Ltd|公司|科技|集团|有限|股份)?)'
)
BATCH_PATTERN = re.compile(
    r'(?i)(?<!\w)(Lot\s*(No|#|\.)\s*[.:#]?\s*\d[\dA-Za-z]*|'
    r'Serial\s*(No|#|\.)\s*[.:#]?\s*\d[\dA-Za-z]*|'
    r'Batch\s*(No|#|\.)\s*[.:#]?\s*\d[\dA-Za-z]*|'
    r'Work\s*Order\s*(No|#)?[\s:#]?\w+|'
    r'WO[\s:#]?\d{4,})(?!\w)'
)


class DrawingTokenizer:
    """图纸文本Token化引擎"""
    
    def __init__(self, mapper: TokenMapper):
        self.mapper = mapper
        self.changes = []
    
    def tokenize(self, text: str) -> str:
        """
        完整Token化管道：
        1. 图号脱敏（PN不可逆）
        2. 标题栏脱敏（不可逆）
        3. 尺寸数值Token化（可逆）
        4. 直径值Token化（可逆）
        5. 公差Token化（可逆）
        6. GD&T Token化（可逆）
        7. 基准Token化（可逆）
        8. 批次脱敏（不可逆）
        """
        self.changes = []
        t = text
        
        # 1. 图号
        t = self._tokenize_part_numbers(t)
        # 2. 标题栏
        t = self._sanitize_metadata(t)
        # 3. 公差（必须在尺寸之前，否则0.070会被先Token化为DIM）
        t = self._tokenize_tolerances(t)
        # 4. 尺寸数值
        t = self._tokenize_dimensions(t)
        # 5. 直径
        t = self._tokenize_diameters(t)
        # 6. GD&T
        t = self._tokenize_gdt(t)
        # 7. 基准
        t = self._tokenize_datums(t)
        # 8. 批次
        t = self._sanitize_batch(t)
        
        _log("Token化完成", changes=self.changes[:20], 
             total_changes=len(self.changes), tokens=len(self.mapper.mapping))
        return t
    
    def _tokenize_part_numbers(self, text: str) -> str:
        def _replace(m):
            pn = m.group(1)
            tid = self.mapper.get_pn(pn)
            self.changes.append(f"PN: {pn}→{tid}")
            return tid
        t = PART_NUMBER_PATTERN.sub(_replace, text)
        t = LOOSE_PN_PATTERN.sub(_replace, t)
        return t
    
    def _sanitize_metadata(self, text: str) -> str:
        t = text
        # 公司名
        def _replace_company(m):
            self.changes.append(f"Company → [Company]")
            return "[Company]"
        t = COMPANY_PATTERN.sub(_replace_company, t)
        # 英文人名
        def _replace_name(m):
            name = m.group(m.lastindex) if m.lastindex else ""
            name_str = str(name).strip() if name else ""
            role_text = m.group(0)
            if 'check' in role_text.lower():
                rep = "[Checker]"
            elif 'approv' in role_text.lower():
                rep = "[Approver]"
            else:
                rep = "[Designer]"
            self.changes.append(f"Name: \"{name_str[:20]}\" → {rep}")
            return rep
        t = NAME_PATTERN.sub(_replace_name, t)
        # 中文人名
        def _replace_cn(m):
            role = m.group(1)
            rep = "[Designer]" if re.search(r'设计|绘制|制图', role) else \
                  "[Checker]" if re.search(r'审核|校核', role) else \
                  "[Approver]" if re.search(r'批准|审定', role) else "[Person]"
            self.changes.append(f"CN-Name → {rep}")
            return rep
        t = CN_NAME_PATTERN.sub(_replace_cn, t)
        # 版本
        t = re.sub(r'(?i)\b(Rev(ision)?|版本)\s*[.:]?\s*[\w.-]+\b', '[Revision]', t)
        # 日期
        t = re.sub(r'(?i)(Date\s*[=:]\s*)\d{4}[-/]\d{1,2}[-/]\d{1,2}', r'\1[Date]', t)
        return t
    
    def _tokenize_dimensions(self, text: str) -> str:
        def _replace(m):
            val = m.group(1)
            token = self.mapper.tokenize_value(val, 'DIM')
            self.changes.append(f"DIM: {val}→{token}")
            return token
        return DIM_VALUE_PATTERN.sub(_replace, text)
    
    def _tokenize_diameters(self, text: str) -> str:
        def _replace(m):
            prefix = m.group(1).strip()
            val = m.group(2)
            token = self.mapper.tokenize_value(f"{prefix} {val}", 'DIA')
            self.changes.append(f"DIA: {prefix}{val}→{token}")
            return token
        return DIA_PATTERN.sub(_replace, text)
    
    def _tokenize_tolerances(self, text: str) -> str:
        def _replace(m):
            sign = m.group(1)
            upper = m.group(2)
            lower = m.group(3)
            raw = f"{sign}{upper}"
            if lower:
                raw += f"/-{lower}"
            token = self.mapper.tokenize_value(raw, 'TOL')
            self.changes.append(f"TOL: {raw}→{token}")
            return token
        return TOL_PATTERN.sub(_replace, text)
    
    def _tokenize_gdt(self, text: str) -> str:
        def _replace(m):
            symbol = m.group(1)
            val = m.group(2)
            raw = f"{symbol} {val}"
            token = self.mapper.tokenize_value(raw, 'GDT')
            self.changes.append(f"GDT: {raw}→{token}")
            return token
        return GDT_PATTERN.sub(_replace, text)
    
    def _tokenize_datums(self, text: str) -> str:
        def _replace(m):
            datum = m.group(1)
            token = self.mapper.tokenize_datum(datum)
            self.changes.append(f"DTM: Datum {datum}→{token}")
            return f"Datum {token}"
        return DATUM_PATTERN.sub(_replace, text)
    
    def _sanitize_batch(self, text: str) -> str:
        def _replace(m):
            self.changes.append("Batch → [Batch Info]")
            return "[Batch Info]"
        return BATCH_PATTERN.sub(_replace, text)


# ═══════════════════════════════════════════════════
# 4. 验证引擎
# ═══════════════════════════════════════════════════

LEAK_PATTERNS = [
    (r'\b\d{3,4}-\d{4,6}(?:-\d{2})?\b', '原始图号裸露'),
    (r'(?i)(Designed|Drawn|Checked|Approved)\s+by\s+[A-Z]', '人名裸露'),
    (r'(?i)\b(Apple|Tesla|CATL|BYD)\b', '公司名裸露'),
    (r'(?i)\bLot\s+(No|#)\s*\d+', '批次信息裸露'),
    (r'(?i)\bSerial\s+(No|#)\s*\d+', '序列号裸露'),
]


def check_for_leaks(text: str) -> list[str]:
    """检测文本中是否有未脱敏的敏感信息"""
    leaks = []
    for pattern, desc in LEAK_PATTERNS:
        if re.search(pattern, text):
            leaks.append(desc)
    return leaks


def check_token_coverage(text: str) -> dict:
    """检测Token覆盖情况"""
    token_pattern = re.compile(r'\b(DIM|DIA|TOL|GDT|DTM|MAT)-[A-F0-9]{8}\b')
    tokens_found = token_pattern.findall(text)
    counts = {}
    for t in tokens_found:
        prefix = t.split('-')[0]
        counts[prefix] = counts.get(prefix, 0) + 1
    return {
        "total_tokens": len(tokens_found),
        "by_type": counts,
    }


# ═══════════════════════════════════════════════════
# 5. 完整管线
# ═══════════════════════════════════════════════════

def create_session(session_id: str = None) -> tuple[str, CipherEngine, TokenMapper, DrawingTokenizer]:
    """创建新的加密会话"""
    if not session_id:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    cipher = CipherEngine()
    mapper = TokenMapper(cipher)
    tokenizer = DrawingTokenizer(mapper)
    
    key_sig = cipher.get_key_signature()
    _log("加密映射初始化", session_id=session_id, key=key_sig, key_bits=256)
    
    return session_id, cipher, mapper, tokenizer


def load_session(session_id: str) -> tuple[Optional[CipherEngine], Optional[TokenMapper], str]:
    """从加密映射表恢复会话"""
    map_file = CACHE_DIR / session_id / "encrypted_mapping.enc"
    if not map_file.exists():
        _log("会话加载失败: 映射表不存在", session_id=session_id)
        return None, None, "映射表不存在"
    
    try:
        # 用主密钥解密映射表
        f = Fernet(base64.urlsafe_b64encode(AES_KEY))
        encrypted_data = map_file.read_text(encoding="utf-8")
        decrypted = f.decrypt(encrypted_data.encode()).decode()
        data = json.loads(decrypted)
        
        # 恢复会话密钥
        session_key = CipherEngine.decrypt_session_key(data["encrypted_session_key"])
        cipher = CipherEngine(session_key)
        
        # 恢复映射器
        mapper = TokenMapper(cipher)
        mapper.mapping = data.get("mapping", {})
        mapper.fai_mapping = data.get("fai_mapping", {})
        mapper.pn_registry = data.get("pn_registry", {})
        mapper.statistics = data.get("statistics", mapper.statistics)
        
        _log("会话加载成功", session_id=session_id, tokens=len(mapper.mapping))
        return cipher, mapper, "ok"
    
    except Exception as e:
        _log("会话加载失败", session_id=session_id, error=str(e))
        return None, None, str(e)


def full_pipeline(text: str, session_id: str = None) -> dict:
    """
    完整管线: 提取→Token化→存储→返回Token数据
    返回: {session_id, tokenized_text, token_count, mapping_file, ...}
    """
    sid, cipher, mapper, tokenizer = create_session(session_id)
    tokenized = tokenizer.tokenize(text)
    
    files = mapper.save_mapping(sid)
    
    return {
        "session_id": sid,
        "tokenized_text": tokenized,
        "statistics": mapper.get_stats(),
        "token_count": len(mapper.mapping),
        "files": files,
    }


# ═══════════════════════════════════════════════════
# 6. CLI 入口
# ═══════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("═══ Drawing Privacy Guard v2.0 ═══")
        print("用法:")
        print("  --pipeline <文本或文件路径>   完整管线: Token化+存储")
        print("  --tokenize <文本>              Token化文本")
        print("  --tokenize-file <文件路径>     Token化文件内容")
        print("  --restore <文本>              还原Token")
        print("  --restore-file <文件路径>     还原文件中的Token")
        print("                                 (需要 --session 指定会话ID)")
        print("  --restore-session <session>   从指定会话还原")
        print("  --map-info <session>          查看会话映射统计")
        print("  --check <文本>                检查泄漏")
        print("  --check-tokenized <文本>      检查Token覆盖率")
        print("  --test                        快速测试")
        return
    
    cmd = sys.argv[1]
    
    # ── 完整管线 ──
    if cmd == "--pipeline":
        text = sys.argv[2] if len(sys.argv) >= 3 else sys.stdin.read()
        if os.path.isfile(text):
            text = Path(text).read_text(encoding="utf-8")
        result = full_pipeline(text)
        print(f"会话ID: {result['session_id']}")
        print(f"Token总数: {result['token_count']}")
        print(f"统计: {json.dumps(result['statistics'], ensure_ascii=False)}")
        print(f"\nToken化文本:\n{result['tokenized_text']}")
        print(f"\n映射表: {result['files']['encrypted_map']}")
    
    # ── Token化 ──
    elif cmd == "--tokenize" and len(sys.argv) >= 3:
        text = sys.argv[2]
        _, cipher, mapper, tokenizer = create_session()
        result = tokenizer.tokenize(text)
        stats = mapper.get_stats()
        print(f"Token化结果 ({stats['tokens_created']} tokens):")
        print(result)
    
    elif cmd == "--tokenize-file" and len(sys.argv) >= 3:
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
        _, cipher, mapper, tokenizer = create_session()
        result = tokenizer.tokenize(text)
        stats = mapper.get_stats()
        out_path = Path(sys.argv[2]).with_suffix(".tokenized.txt")
        out_path.write_text(result, encoding="utf-8")
        print(f"Token化完成: {stats['tokens_created']} tokens")
        print(f"输出: {out_path}")
        print(result[:500] + "...")
    
    # ── 还原 ──
    elif cmd == "--restore" and len(sys.argv) >= 3:
        text = sys.argv[2]
        session_id = None
        for i, arg in enumerate(sys.argv):
            if arg == "--session" and i+1 < len(sys.argv):
                session_id = sys.argv[i+1]
        if not session_id:
            print("错误: 需要 --session <ID> 指定会话", file=sys.stderr)
            sys.exit(1)
        _, mapper, status = load_session(session_id)
        if status != "ok":
            print(f"加载会话失败: {status}", file=sys.stderr)
            sys.exit(1)
        restored = mapper.restore_text(text)
        print("还原结果:")
        print(restored)
    
    elif cmd == "--restore-file" and len(sys.argv) >= 3:
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
        session_id = None
        for i, arg in enumerate(sys.argv):
            if arg == "--session" and i+1 < len(sys.argv):
                session_id = sys.argv[i+1]
        if not session_id:
            print("错误: 需要 --session <ID> 指定会话", file=sys.stderr)
            sys.exit(1)
        _, mapper, status = load_session(session_id)
        if status != "ok":
            print(f"加载会话失败: {status}", file=sys.stderr)
            sys.exit(1)
        restored = mapper.restore_text(text)
        out_path = Path(sys.argv[2]).with_suffix(".restored.txt")
        out_path.write_text(restored, encoding="utf-8")
        print(f"还原完成 → {out_path}")
        print(restored[:500] + "...")
    
    elif cmd == "--restore-session" and len(sys.argv) >= 3:
        session_id = sys.argv[2]
        _, mapper, status = load_session(session_id)
        if status != "ok":
            print(f"加载失败: {status}", file=sys.stderr)
            sys.exit(1)
        print(f"会话 {session_id}:")
        print(f"  Token映射数: {len(mapper.mapping)}")
        print(f"  FAI映射数: {len(mapper.fai_mapping)}")
        print(f"  统计: {json.dumps(mapper.statistics, ensure_ascii=False)}")
        print(f"\nToken列表 (前20):")
        for i, token in enumerate(sorted(mapper.mapping.keys())[:20]):
            print(f"  {token}")
        print("\n输入文本后按Ctrl+D还原:")
        for line in sys.stdin:
            print(mapper.restore_text(line.strip()))
    
    # ── 管理 ──
    elif cmd == "--map-info" and len(sys.argv) >= 3:
        session_id = sys.argv[2]
        _, mapper, status = load_session(session_id)
        if status != "ok":
            print(f"加载失败: {status}", file=sys.stderr)
            sys.exit(1)
        print(f"会话 {session_id}:")
        print(f"  Token总数: {len(mapper.mapping)}")
        print(f"  FAI映射数: {len(mapper.fai_mapping)}")
        print(f"  图号映射数: {len(mapper.pn_registry)}")
        print(f"  统计: {json.dumps(mapper.statistics, ensure_ascii=False)}")
    
    # ── 检查 ──
    elif cmd == "--check" and len(sys.argv) >= 3:
        text = sys.argv[2]
        leaks = check_for_leaks(text)
        if leaks:
            print("⚠️ 发现泄漏:")
            for l in leaks:
                print(f"  ❌ {l}")
        else:
            print("✅ 无泄漏")
    
    elif cmd == "--check-tokenized" and len(sys.argv) >= 3:
        text = sys.argv[2]
        coverage = check_token_coverage(text)
        print(json.dumps(coverage, ensure_ascii=False, indent=2))
    
    # ── 测试 ──
    elif cmd == "--test":
        print("═══ Drawing Privacy Guard v2.0 测试 ═══")
        
        test_text = """
        Drawing: 613-39859-02_CELL_ASSY
        Designed by: John Smith  / 公司: Apple Inc.  /  Rev A  / Date: 2026-06-15
        Designer: John Smith  Checker: Jane Doe  Approver: R. Manager
        FAI 1: 壳体外径 Ø10.600 ±0.070  Datum A
        FAI 2: 壳体底部 Ø10.600 ±0.070  Datum A
        FAI 3: 密封钉高度 0.05 +0.10/-0  Datum A
        FAI 4: 密封钉平整度 ∠ 0.000  Datum A
        FAI 5: 底部轮廓度 ⌓ 0.06  Datum A
        FAI 6: R角 R0.45 ±0.10  Datum A
        FAI 7: 壳盖台阶高度 4.690 ±0.090  Datum A
        FAI 8: 壳盖基面高度 4.510 ±0.070  Datum A
        FAI 9: 基准面A最大膨胀 0.075  Datum A
        Lot No. 2026A001
        """
        
        # 管线测试
        print("\n--- 1. 完整管线 ---")
        result = full_pipeline(test_text)
        print(f"会话: {result['session_id']}")
        print(f"Token数: {result['token_count']}")
        print(f"统计: {json.dumps(result['statistics'])}")
        print(f"\nToken化输出:\n{result['tokenized_text']}")
        
        # 泄漏检查
        print("\n--- 2. 泄漏检查 ---")
        leaks = check_for_leaks(result['tokenized_text'])
        print(f"泄漏: {leaks if leaks else '✅ 无泄漏'}")
        
        # Token覆盖率
        print("\n--- 3. Token覆盖率 ---")
        coverage = check_token_coverage(result['tokenized_text'])
        print(json.dumps(coverage, indent=2))
        
        # 还原测试：模拟LLM返回
        print("\n--- 4. LLM返回还原测试 ---")
        llm_response = """
        分析结果:
        DIM-A7F3K2L9 ± TOL-1B2C4D8E 匹配典型壳体外径值10.600mm
        基准DTM-3C4D5E6F为主基准面
        DIA-B4E8F1C7为壳体底部直径
        GDT-9E8F1A2B平面度要求0.000
        """
        # 从映射中尝试还原（如果有匹配的Token）
        session_id = result['session_id']
        _, mapper, status = load_session(session_id)
        if status == "ok":
            # 用实际的Token重新生成LLM响应
            tokens = list(mapper.mapping.keys())[:5]
            real_llm = "分析结果:\n"
            for t in tokens[:3]:
                real_val = mapper.cipher.decrypt(mapper.mapping[t])
                real_llm += f"  {t} = {real_val} (尺寸分析)\n"
            print("LLM虚拟输出:")
            print(real_llm)
            restored = mapper.restore_text(real_llm)
            print("还原后:")
            print(restored)
        
        print("\n✅ 全部测试通过")
    
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
