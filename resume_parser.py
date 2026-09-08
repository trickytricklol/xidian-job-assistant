# -*- coding: utf-8 -*-
"""简历解析模块：从简历（PDF / TXT / MD）中提取 专业 / 技能 / 意向岗位。

纯本地规则实现，不调用任何大模型：
- 专业：在「教育背景」段落中匹配常见专业关键词（如 计算机、软件工程、人工智能…）
- 意向岗位：取「求职意向：」行的内容
- 技能：技能词典（显示名→别名）在简历全文中匹配 + 「技术栈：」行补充提取
"""
import os
import re
from typing import List

# ---------------------------------------------------------------- 专业词典
# 与 config.USER_MAJORS 对齐；命中即认为简历背景包含该专业方向
MAJOR_KEYWORDS = ["计算机", "软件工程", "人工智能", "电子信息", "通信", "自动化",
                  "集成电路", "微电子", "数学", "数据科学", "控制", "信息安全",
                  "网络工程"]

# ---------------------------------------------------------------- 技能词典
# 显示名 → 匹配别名（在简历全文与职位名中做子串匹配，均为小写）
SKILL_LEXICON = {
    "大模型": ["大模型", "llm", "gpt", "千问", "qwen", "deepseek", "生成式"],
    "Agent/多智能体": ["agent", "多智能体", "multi-agent", "function calling", "mcp"],
    "RAG检索": ["rag", "检索", "向量", "embedding", "召回", "重排序", "知识库"],
    "提示词工程": ["提示词", "prompt", "few-shot"],
    "模型训练/微调": ["微调", "sft", "dpo", "grpo", "ppo", "强化学习", "蒸馏",
                      "混合精度", "qlora"],
    "Python": ["python"],
    "PyTorch": ["pytorch", "torch"],
    "Java": ["java", "jvm"],
    "SpringBoot": ["springboot", "spring boot", "mybatis"],
    "MySQL": ["mysql"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", " ik分词", "elk"],
    "Kafka": ["kafka", "rocketmq", "消息队列"],
    "FastAPI": ["fastapi"],
    "LangChain": ["langchain"],
    "C/C++": ["c++", "c语言", "c/c++"],
    "算法/数据结构": ["算法", "数据结构", "递归", "动态规划", "leetcode"],
    "机器学习/数据挖掘": ["机器学习", "数据挖掘", "深度学习", "神经网络", "lstm"],
    "嵌入式/芯片": ["嵌入式", "fpga", "verilog", "芯片", "集成电路", "硬件"],
    "Web开发": ["前端", "后端", "全栈", "spring", "restful", "http"],
    "测试/运维": ["测试", "运维", "sre", "devops", "ci/cd"],
    "量化/部署优化": ["量化", "onnx", "部署", "推理优化", "tensorrt"],
}

MAX_SKILLS = 30  # 技能上限，避免噪音


def extract_text(path: str) -> str:
    """从 PDF / TXT / MD 提取纯文本"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".text"):
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t)
        return "\n".join(parts)
    # 未知类型：尝试按文本读
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _split_tokens(text: str) -> List[str]:
    """按常见分隔符拆分技能/岗位片段"""
    return [t.strip() for t in re.split(r"[,，、;；/| \n]+", text) if t.strip()]


def parse_resume(path: str) -> dict:
    """解析简历，返回画像：
    {
      "majors": [专业关键词...],
      "skills": [(显示名, [别名...]), ...],   # 含「技术栈：」补充的词条（别名即自身）
      "targets": [意向岗位...],
      "source": 文件路径,
    }
    简历缺失或解析失败时返回 None（调用方回退到 config.USER_MAJORS 规则）。
    """
    if not path or not os.path.exists(path):
        return None
    try:
        text = extract_text(path)
    except Exception as e:
        print(f"[resume_parser] 读取简历失败：{e}")
        return None
    if not text or not text.strip():
        return None

    low = text.lower()

    # 1. 专业：只在包含教育标记（学位/保研/硕士/博士/本科…）的行里匹配，
    #    避免把正文中"自动化归档""数学竞赛""专业性"等词误当专业。
    #    注意：部分 PDF 提取后小节标题与内容顺序错乱，因此不做段落切分，
    #    直接在全文中筛"教育行"。
    edu_markers = r"学位|保研|硕士|博士|本科|研究生|学制|主修"
    edu_lines = [ln for ln in re.split(r"\n+", text) if re.search(edu_markers, ln)]
    if not edu_lines:  # 兜底：取全文前半段
        edu_lines = [text[: max(len(text) // 2, 500)]]
    majors = []
    for kw in MAJOR_KEYWORDS:
        if any(kw in ln for ln in edu_lines):
            majors.append(kw)

    # 2. 意向岗位
    targets = []
    m = re.search(r"求职意向\s*[:：]\s*([^\n]+)", text)
    if m:
        targets = _split_tokens(m.group(1))
        targets = [t for t in targets if len(t) <= 20]

    # 3. 技能：词典匹配
    skills = []
    for name, alis in SKILL_LEXICON.items():
        if any(a in low for a in alis):
            skills.append((name, list(alis)))
    # 4. 「技术栈：」行补充提取（保留未见过的技术词条）
    extra = []
    seen_l = {s[0].lower() for s in skills}
    for line in re.findall(r"技术栈\s*[:：]\s*([^\n]+)", text):
        for tok in _split_tokens(line):
            tok_l = tok.lower()
            if len(tok) < 2 or re.fullmatch(r"[\d.]+", tok):
                continue  # 过滤过短词 / 纯版本号
            if tok_l in seen_l or any(tok_l == a for s in skills for a in s[1]):
                continue  # 已覆盖
            extra.append((tok, [tok_l]))
            seen_l.add(tok_l)
    skills = (skills + extra)[:MAX_SKILLS]

    return {
        "majors": majors,
        "skills": skills,
        "targets": targets,
        "source": os.path.abspath(path),
    }


def describe(profile: dict) -> str:
    """打印画像摘要（用于控制台日志）"""
    if not profile:
        return "未解析到简历，回退 USER_MAJORS 规则"
    majors = "/".join(profile["majors"]) or "-"
    skills = "、".join(s[0] for s in profile["skills"][:15]) or "-"
    targets = "/".join(profile["targets"]) or "-"
    return (f"专业[{majors}] 技能[{skills}] 意向[{targets}] "
            f"来源[{profile.get('source')}]")
