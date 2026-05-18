"""工具调用截断检测模块

当 Kiro API 达到输出 token 上限时，工具调用的 JSON 可能被截断，
导致参数不完整或无法解析。此模块检测截断并生成软失败消息引导重试。

参考 kiro.rs-fork truncation.rs
"""
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class TruncationType(Enum):
    NONE = "none"
    EMPTY_INPUT = "empty_input"
    INVALID_JSON = "invalid_json"
    MISSING_FIELDS = "missing_fields"
    INCOMPLETE_STRING = "incomplete_string"


@dataclass
class TruncationInfo:
    is_truncated: bool = False
    truncation_type: TruncationType = TruncationType.NONE
    tool_name: str = ""
    tool_use_id: str = ""
    raw_input: str = ""
    parsed_fields: Dict[str, str] = field(default_factory=dict)
    error_message: str = ""


# 已知的写入工具
_WRITE_TOOLS = frozenset({
    "Write", "write_to_file", "fsWrite", "create_file",
    "edit_file", "apply_diff", "str_replace_editor", "insert",
})

# 工具必需字段映射
_REQUIRED_FIELDS: Dict[str, tuple] = {
    "Write":             ("file_path", "content"),
    "write_to_file":     ("path", "content"),
    "fsWrite":           ("path", "content"),
    "create_file":       ("path", "content"),
    "edit_file":         ("path",),
    "apply_diff":        ("path", "diff"),
    "str_replace_editor": ("path", "old_str", "new_str"),
    "Bash":              ("command",),
    "execute":           ("command",),
    "run_command":       ("command",),
}


def _looks_like_truncated_json(raw: str) -> bool:
    if not raw.strip() or not raw.strip().startswith("{"):
        return False

    trimmed = raw.strip()
    if trimmed.count("{") > trimmed.count("}"):
        return True
    if trimmed.count("[") > trimmed.count("]"):
        return True
    if trimmed and trimmed[-1] in ('"', ":", ","):
        return True

    # 检查未闭合的字符串
    in_string = False
    escaped = False
    for ch in trimmed:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
    if in_string:
        return True

    return False


def _extract_partial_fields(raw: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    trimmed = raw.strip().lstrip("{")
    for part in trimmed.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        idx = part.index(":")
        key = part[:idx].strip().strip('"')
        val = part[idx+1:].strip()
        fields[key] = val[:50] + "..." if len(val) > 50 else val
    return fields


def _detect_content_truncation(obj: dict, raw_input: str) -> Optional[str]:
    content = obj.get("content")
    if not isinstance(content, str):
        return None
    if len(raw_input) > 1000 and len(content) < 100:
        return "content field appears suspiciously short compared to raw input size"
    if "```" in content and content.count("```") % 2 != 0:
        return "content contains unclosed code fence (```) suggesting truncation"
    return None


def detect_truncation(
    tool_name: str,
    tool_use_id: str,
    raw_input: str,
    parsed_input: Optional[Any] = None,
) -> TruncationInfo:
    """检测工具输入是否被截断"""
    info = TruncationInfo(
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        raw_input=raw_input,
    )

    # 场景 1: 输入完全为空
    if not raw_input or not raw_input.strip():
        info.is_truncated = True
        info.truncation_type = TruncationType.EMPTY_INPUT
        info.error_message = "Tool input was completely empty - API response may have been truncated"
        print(f"[Truncation] empty_input tool={tool_name} id={tool_use_id}")
        return info

    # 场景 2: JSON 解析失败
    parsed = None
    if isinstance(parsed_input, dict) and parsed_input:
        parsed = parsed_input
    
    if parsed is None and _looks_like_truncated_json(raw_input):
        info.is_truncated = True
        info.truncation_type = TruncationType.INVALID_JSON
        info.parsed_fields = _extract_partial_fields(raw_input)
        info.error_message = f"Tool input JSON was truncated mid-transmission ({len(raw_input)} bytes received)"
        print(f"[Truncation] invalid_json tool={tool_name} id={tool_use_id} raw_len={len(raw_input)}")
        return info

    # 场景 3: 缺少必需字段
    if parsed is not None:
        required = _REQUIRED_FIELDS.get(tool_name)
        if required:
            missing = [f for f in required if f not in parsed]
            if missing:
                info.is_truncated = True
                info.truncation_type = TruncationType.MISSING_FIELDS
                info.parsed_fields = {k: str(v)[:50] for k, v in parsed.items()}
                info.error_message = f"Tool '{tool_name}' missing required fields: {', '.join(missing)}"
                print(f"[Truncation] missing_fields tool={tool_name} id={tool_use_id} missing={missing}")
                return info

        # 场景 4: 写入工具内容截断
        if tool_name in _WRITE_TOOLS:
            msg = _detect_content_truncation(parsed, raw_input)
            if msg:
                info.is_truncated = True
                info.truncation_type = TruncationType.INCOMPLETE_STRING
                info.parsed_fields = {k: str(v)[:50] for k, v in parsed.items()}
                info.error_message = msg
                print(f"[Truncation] incomplete_string tool={tool_name} id={tool_use_id}: {msg}")
                return info

    return info


def build_soft_failure_result(info: TruncationInfo) -> str:
    """构建软失败工具结果消息，引导模型重试并分块写入"""
    max_line_hint = {
        TruncationType.EMPTY_INPUT: 200,
        TruncationType.INVALID_JSON: 250,
        TruncationType.MISSING_FIELDS: 300,
        TruncationType.INCOMPLETE_STRING: 350,
        TruncationType.NONE: 300,
    }.get(info.truncation_type, 300)

    reason = {
        TruncationType.EMPTY_INPUT: "Your tool call was too large and the input was completely lost during transmission.",
        TruncationType.INVALID_JSON: "Your tool call was truncated mid-transmission, resulting in incomplete JSON.",
        TruncationType.MISSING_FIELDS: "Your tool call was partially received but critical fields were cut off.",
        TruncationType.INCOMPLETE_STRING: "Your tool call content was truncated - the full content did not arrive.",
        TruncationType.NONE: "Your tool call was truncated by the API due to output size limits.",
    }.get(info.truncation_type, "Your tool call was truncated.")

    lines = [
        "TOOL_CALL_INCOMPLETE",
        f"status: incomplete",
        f"reason: {reason}",
    ]

    if info.parsed_fields:
        ctx = ", ".join(f"{k}={v[:30]}..." if len(v) > 30 else f"{k}={v}"
                       for k, v in info.parsed_fields.items())
        lines.append(f"context: Received partial data: {ctx}")

    lines += [
        "",
        "CONCLUSION: Split your output into smaller chunks and retry.",
        "",
        "REQUIRED APPROACH:",
        f"1. For file writes: Write in chunks of ~{max_line_hint} lines maximum",
        "2. For new files: First create with initial chunk, then append remaining sections",
        "3. For edits: Make surgical, targeted changes - avoid rewriting entire files",
        "",
        "DO NOT attempt to write the full content again in a single call.",
        "The API has a hard output limit that cannot be bypassed.",
    ]

    return "\n".join(lines)
