#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes 证明材料/专利/论文 隐私保护引擎 — Certificate Privacy Guard v1.0
=======================================================================
对证明材料（营业执照/毕业证/证书/奖牌）、专利证书、论文中的
未公开敏感信息进行本地 Token 化脱敏，防止泄露到本机之外。

敏感实体类型:
  1A 不可逆脱敏 (无法还原):
    公司名 → [Company]     人名 → [Person-N]
    地址   → [Address]     电话  → [Phone]
  1B 可逆 Token (AES-256-GCM, 本地映射表可还原):
    专利号    → PAT-XXXXXXXX   证书号    → CERT-XXXXXXXX
    信用代码  → USCC-XXXXXXXX  身份证号  → ID-XXXXXXXX
    发明名称  → TIT-XXXXXXXX   授权公告号 → PUB-XXXXXXXX
    日期      → DAT-XXXXXXXX

用法:
  python certificate_privacy_guard.py --pipeline <文本或文件> [--session ID]
  python certificate_privacy_guard.py --batch <目录>            # 批量处理目录下所有txt
  python certificate_privacy_guard.py --restore-file <json>    # 还原Token
  python certificate_privacy_guard.py --check <文本>            # 泄漏检查
"""
import sys, os, re, json, hashlib, logging
from pathlib import Path
from datetime import datetime

# 复用 drawing_privacy_guard 的加密引擎
sys.path.insert(0, str(Path(__file__).resolve().parent))
from drawing_privacy_guard import CipherEngine, TokenMapper, _load_or_create_master_key

LOG_DIR = Path.home() / "AppData/Local/hermes/profiles/mybot/logs"
CACHE_DIR = Path("D:/hermes/analysis/certificate_cache")
LOG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger("certificate_privacy_guard")
_handler = logging.FileHandler(str(LOG_DIR / "certificate_privacy_guard.log"), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [CERT_PRIVACY v1] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

def _log(msg: str, **extra):
    extra_str = f" | {json.dumps(extra, ensure_ascii=False)}" if extra else ""
    _logger.info(f"{msg}{extra_str}")


# ═══════════════════════════════════════════════════
# 1. 敏感实体识别规则（证明材料/专利/论文专用）
# ═══════════════════════════════════════════════════

# 1A — 不可逆替换（直接遮蔽，无需映射表）
# 已知人名（证明材料中出现的高频人员）
KNOWN_PERSONS = "周雄|袁莺|欧阳艳青|邹宗永|罗桂海|乐兵生|曾东海|欧阳艳肯|欧网艳青|欧阢艳青|欧网艳青|申长雨|许玉昆|肖招明|陈昊|黎政秀"
IRREVERSIBLE_PATTERNS = [
    # 已知人名（精确名单，全文替换）— OCR可能把"罗桂\n海"拆断，故先归一化中文间空白
    (re.compile(f"({KNOWN_PERSONS})"), "[Person]"),
    # 公司名：已知公司 + 通用"公司/企业/厂"模式
    (re.compile(r"江西富鸿金属有限公司|富鸿金属|富鸿(?:金属)?(?:有限)?公司"), "[Company]"),
    (re.compile(r"[\u4e00-\u9fff]{2,20}(?:有限公司|有限责任公司|股份有限公司|集团有限公司|公司|工厂|厂)"), "[Company]"),
    # 人名：中文姓名（2-4字，前后边界）
    (re.compile(r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{2,4}(?:艳青|莺|宗永|桂海|兵生|东海|艳|莺|青|永|海|生))(?![\u4e00-\u9fff])"), "[Person]"),
    # 人名列表：完成人/发明人/设计人/参与人名单（空格或分号分隔的中文姓名，2-6个）
    (re.compile(r"(?:(?:主要完成人员|完成人员|发明人|设计人|参与人员|研制人员|开发人员|申报人员|负责人)[:：]?\s*)([\u4e00-\u9fff]{2,4}(?:[;；、\s]+[\u4e00-\u9fff]{2,4}){1,9})"), "[Person]"),
    # 连写人名名单（OCR无分隔符）：已知人名连续拼接（如"欧阳艳青袁莺许玉昆肖招明罗桂海陈昊黎政秀"）
    (re.compile(f"(?<![\u4e00-\u9fff])(?:{KNOWN_PERSONS}){{2,10}}(?![姓名]|[\u4e00-\u9fff])"), "[Person]"),
    # 地址：邮编 + 省市县街道模式（邮编必须紧跟省/市/区/县，避免吞手机号）
    (re.compile(r"(?<!\d)\d{5,6}(?!\d)\s*[\u4e00-\u9fff]{2,}(?:省|市|区|县)[\u4e00-\u9fff]{2,}(?:工业园|开发区|路|街|镇|乡|村|号)"), "[Address]"),
    (re.compile(r"(?:地址|住址|住所|址)[:：;；]?\s*[\u4e00-\u9fff]{2,40}"), "[Address]"),
    # 地址（无前缀独立出现）：省市县+街道
    (re.compile(r"[\u4e00-\u9fff]{2,}(?:省|市|区|县)[\u4e00-\u9fff]{2,}(?:工业园|开发区|路|街|镇|乡|村)[\u4e00-\u9fff0-9]{0,20}"), "[Address]"),
    # 商标注册号: TMZC开头或"商标注册证"后编号
    (re.compile(r"TMZC[A-Z0-9]{8,20}"), "[TrademarkNo]"),
    (re.compile(r"商标注册(?:证|号)[^A-Za-z0-9]{0,3}[A-Z0-9]{6,20}"), "[TrademarkNo]"),
    # 电话
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[Phone]"),
    (re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)"), "[Phone]"),
]

# 1B — 可逆 Token（AES加密映射）
REVERSIBLE_PATTERNS = [
    # 银行账号/卡号: 16-19位数字（卡号特征，前6位BIN+后4位）
    ("BANK", re.compile(r"\b\d{16,19}\b")),
    # 专利号: ZL 2021 1 0412916.8 / CN 113118234 B / 2018 1 1352693.5 (中文后\b失效→用(?<!\d))
    ("PAT", re.compile(r"(?<!\d)(?:ZL\s*)?\d{4}\s*[12]\s*\d{6,8}(?:\.\d+)?(?!\d)")),
    ("PAT", re.compile(r"(?<![A-Z0-9])CN\s*\d{8,9}\s*[ABU](?![A-Z0-9])")),
    # 授权公告号: CN 113118234 B
    ("PUB", re.compile(r"(?:授权公告号|公告号)[:：]?\s*(?:CN\s*\d{8,9}\s*[ABU]|\d{8,9}\s*[ABU])")),
    # 证书号: 第5480659号 / 证书号第XXXX号
    ("CERT", re.compile(r"第\s*\d{5,9}\s*号")),
    # 统一社会信用代码: 18位（字母数字）
    ("USCC", re.compile(r"\b[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}\b")),
    # 身份证号: 18位
    ("ID", re.compile(r"\b\d{17}[\dXx]\b")),
    # 日期（证明材料中的具体日期）
    ("DAT", re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")),
]

# 发明名称/实用新型名称/成果名称（包含未公开工艺信息）— 容忍OCR空格
TITLE_PATTERNS = [
    re.compile(r"(?:发\s*明\s*名\s*称|实用新型名称|外观设计名称|成果名称|项目名称|技术领域)[:：]?\s*[\u4e00-\u9fffA-Za-z0-9（）()\-_、，。]{4,60}"),
]

# ═══════════════════════════════════════════════════
# 2. Token化引擎
# ═══════════════════════════════════════════════════

class CertificateTokenizer:
    """证明材料脱敏器 — 顺序：先不可逆(公司/人名/地址)，再可逆Token(专利号/证书号/日期)"""
    def __init__(self, mapper: TokenMapper):
        self.mapper = mapper
        self.person_counter = 0
        self.title_counter = 0
        self.stats = {"irreversible": 0, "reversible": 0, "titles": 0}

    def sanitize_irreversible(self, text: str) -> str:
        """1A 不可逆替换"""
        for pat, repl in IRREVERSIBLE_PATTERNS:
            if pat.search(text):
                text = pat.sub(repl, text)
                self.stats["irreversible"] += 1
        return text

    def tokenize_reversible(self, text: str) -> str:
        """1B 可逆 Token化 — 专利号/证书号/信用代码/身份证/日期"""
        # 先处理较长的授权公告号（避免被专利号规则先截断）
        for prefix, pat in REVERSIBLE_PATTERNS:
            if prefix == "PUB":
                # PUB 已经包含前缀标签，直接提取编号部分
                def _pub_repl(m):
                    full = m.group(0)
                    num = re.search(r"(?:CN\s*)?(\d{8,9}\s*[ABU])", full)
                    val = num.group(1) if num else full
                    token = self.mapper.tokenize_value(val, prefix="PUB")
                    self.stats["reversible"] += 1
                    return f"PUB-{token.split('-',1)[1] if '-' in token else token}"
                text = pat.sub(_pub_repl, text)
                continue
            def _repl(m, p=prefix):
                self.stats["reversible"] += 1
                return self.mapper.tokenize_value(m.group(0), prefix=p)
            text = pat.sub(_repl, text)
        return text

    def tokenize_titles(self, text: str) -> str:
        """发明名称/成果名称 → TIT-Token（工艺信息是高危未公开部分）"""
        for pat in TITLE_PATTERNS:
            def _repl(m):
                self.title_counter += 1
                self.stats["titles"] += 1
                return f"TIT-{self.title_counter:04d}"
            text = pat.sub(_repl, text)
        return text

    def tokenize(self, text: str) -> str:
        """完整Token化管道（顺序: OCR归一化→BANK→不可逆→可逆→标题）"""
        # 0a. OCR归一化: 去除中文之间的空白（修复OCR断词 "罗桂\n海"→"罗桂海"）
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        # 0. 先提取长数字串（银行账号16-19位），防止被Phone规则截断
        def _bank_repl(m):
            self.stats["reversible"] += 1
            return self.mapper.tokenize_value(m.group(0), prefix="BANK")
        text = re.sub(r"(?<!\d)\d{16,19}(?!\d)", _bank_repl, text)
        # 1. 不可逆（公司/人名/地址/电话）
        text = self.sanitize_irreversible(text)
        # 2. 可逆Token
        text = self.tokenize_reversible(text)
        # 3. 标题
        text = self.tokenize_titles(text)
        return text


# ═══════════════════════════════════════════════════
# 3. 泄漏检测
# ═══════════════════════════════════════════════════

def check_for_leaks(text: str) -> list[str]:
    """检测文本中是否仍有敏感实体"""
    leaks = []
    # 已知人名（名单）
    if re.search(rf"(?<![\u4e00-\u9fff])({KNOWN_PERSONS})", text):
        leaks.append("人名")
    # 公司名
    if re.search(r"江西富鸿金属有限公司|[\u4e00-\u9fff]{2,20}(?:有限公司|有限责任公司|股份有限公司|集团有限公司|公司|工厂|厂)", text):
        leaks.append("公司")
    # 地址
    if re.search(r"\d{5,6}\s*[\u4e00-\u9fff]{2,}(?:省|市|区|县)[\u4e00-\u9fff]{2,}(?:工业园|开发区|路|街|镇|乡|村|号)", text) or \
       re.search(r"(?:地址|住址|住所|址)[:：]?\s*[\u4e00-\u9fff0-9]{6,40}", text):
        leaks.append("地址")
    # 电话
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)", text):
        leaks.append("电话")
    # 可逆Token类
    for prefix, pat in REVERSIBLE_PATTERNS:
        if pat.search(text):
            leaks.append(prefix)
    return leaks


# ═══════════════════════════════════════════════════
# 4. 会话管理
# ═══════════════════════════════════════════════════

def create_session(session_id: str = None) -> tuple[str, CipherEngine, TokenMapper, CertificateTokenizer]:
    session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    cipher = CipherEngine()
    mapper = TokenMapper(cipher)
    tokenizer = CertificateTokenizer(mapper)
    return session_id, cipher, mapper, tokenizer


def full_pipeline(text: str, session_id: str = None) -> dict:
    """完整管线: Token化 + 映射表加密存储"""
    session_id, cipher, mapper, tokenizer = create_session(session_id)
    tokenized = tokenizer.tokenize(text)
    saved = mapper.save_mapping(session_id)
    return {
        "session": session_id,
        "original_len": len(text),
        "tokenized_len": len(tokenized),
        "tokenized": tokenized,
        "stats": tokenizer.stats,
        "mapping_saved": saved,
        "leaks_after": check_for_leaks(tokenized),
    }


# ═══════════════════════════════════════════════════
# 5. 批量处理
# ═══════════════════════════════════════════════════

def batch_process(directory: Path, out_dir: Path = None) -> dict:
    """批量处理目录下所有 .txt 文件，输出脱敏文本 + 汇总报告"""
    out_dir = out_dir or (CACHE_DIR / "sanitized")
    out_dir.mkdir(parents=True, exist_ok=True)
    session_id, cipher, mapper, tokenizer = create_session(f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    results = []
    for f in sorted(directory.glob("*.txt")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            results.append({"file": f.name, "error": str(e)})
            continue
        tokenized = tokenizer.tokenize(text)
        out_file = out_dir / f"{f.stem}_sanitized.txt"
        out_file.write_text(tokenized, encoding="utf-8")
        results.append({
            "file": f.name,
            "orig_len": len(text),
            "safe_len": len(tokenized),
            "leaks": check_for_leaks(tokenized),
            "out": str(out_file),
        })

    mapper.save_mapping(session_id)
    report = {
        "session": session_id,
        "files": len(results),
        "total_stats": tokenizer.stats,
        "results": results,
    }
    report_file = CACHE_DIR / f"batch_report_{session_id}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ═══════════════════════════════════════════════════
# 6. CLI
# ═══════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "--pipeline":
        target = sys.argv[2]
        session = None
        if "--session" in sys.argv:
            session = sys.argv[sys.argv.index("--session") + 1]
        text = Path(target).read_text(encoding="utf-8") if Path(target).exists() else target
        result = full_pipeline(text, session)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd == "--batch":
        directory = Path(sys.argv[2])
        report = batch_process(directory)
        print(json.dumps(report, ensure_ascii=False, indent=2)[:5000])
    elif cmd == "--check":
        text = sys.argv[2]
        print(json.dumps({"leaks": check_for_leaks(text), "safe": not check_for_leaks(text)}, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
