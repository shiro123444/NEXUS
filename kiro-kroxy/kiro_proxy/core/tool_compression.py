"""工具压缩模块

当工具定义总大小超过目标阈值时，动态压缩工具 payload 以防止 Kiro API 500 错误。
压缩策略（参考 kiro.rs-fork tool_compression.rs）：
1. 简化 input_schema（仅保留 type/enum/required/properties/items）
2. 按比例压缩 description（最小 50 字符）
"""
import json
from typing import List, Any

# 工具压缩目标大小（20KB）
TOOL_COMPRESSION_TARGET_SIZE = 20 * 1024

# 压缩后描述最小长度
MIN_TOOL_DESCRIPTION_LENGTH = 50


def _calculate_tools_size(tools: List[dict]) -> int:
    """计算工具列表 JSON 序列化大小"""
    try:
        return len(json.dumps(tools, ensure_ascii=False))
    except Exception:
        return 0


def _simplify_schema(schema: Any) -> Any:
    """简化 input_schema，仅保留必要字段"""
    if not isinstance(schema, dict):
        return schema

    simplified = {}

    for key in ("type", "enum", "required"):
        if key in schema:
            simplified[key] = schema[key]

    if "properties" in schema and isinstance(schema["properties"], dict):
        simplified["properties"] = {
            k: _simplify_schema(v) for k, v in schema["properties"].items()
        }

    if "items" in schema:
        simplified["items"] = _simplify_schema(schema["items"])

    if "additionalProperties" in schema:
        simplified["additionalProperties"] = _simplify_schema(schema["additionalProperties"])

    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema and isinstance(schema[key], list):
            simplified[key] = [_simplify_schema(item) for item in schema[key]]

    return simplified


def _compress_description(description: str, target_length: int) -> str:
    """将描述截断到目标长度（UTF-8 安全）"""
    target = max(target_length, MIN_TOOL_DESCRIPTION_LENGTH)
    if len(description) <= target:
        return description
    trunc_len = target - 3
    # 安全截断到字符边界（Python str 是 Unicode，直接切片即可）
    return description[:trunc_len] + "..."


def compress_tools_if_needed(tools: List[dict]) -> List[dict]:
    """如果工具总大小超过阈值则压缩，返回压缩后的列表
    
    参考 kiro.rs-fork compress_tools_if_needed()
    """
    if not tools:
        return tools

    original_size = _calculate_tools_size(tools)
    if original_size <= TOOL_COMPRESSION_TARGET_SIZE:
        return tools

    print(f"[ToolCompression] 工具大小 {original_size} 字节超过目标 {TOOL_COMPRESSION_TARGET_SIZE} 字节，开始压缩")

    # 第一步：简化 input_schema
    compressed = []
    for tool in tools:
        # 处理两种工具格式：Kiro 格式（toolSpecification）和已转换格式
        if "toolSpecification" in tool:
            spec = tool["toolSpecification"]
            schema = spec.get("inputSchema", {}).get("json", {})
            compressed.append({
                "toolSpecification": {
                    "name": spec.get("name", ""),
                    "description": spec.get("description", ""),
                    "inputSchema": {"json": _simplify_schema(schema)},
                }
            })
        else:
            # web_search 或其他特殊工具，不压缩
            compressed.append(tool)

    size_after_schema = _calculate_tools_size(compressed)

    if size_after_schema <= TOOL_COMPRESSION_TARGET_SIZE:
        print(f"[ToolCompression] schema 简化后已达标: {size_after_schema} 字节")
        return compressed

    # 第二步：按比例压缩 description
    size_to_reduce = size_after_schema - TOOL_COMPRESSION_TARGET_SIZE
    total_desc_len = sum(
        len(t["toolSpecification"]["description"])
        for t in compressed
        if "toolSpecification" in t
    )

    if total_desc_len > 0:
        keep_ratio = max(0.0, min(1.0, 1.0 - size_to_reduce / total_desc_len))
        for tool in compressed:
            if "toolSpecification" in tool:
                desc = tool["toolSpecification"]["description"]
                target_len = int(len(desc) * keep_ratio)
                tool["toolSpecification"]["description"] = _compress_description(desc, target_len)

    final_size = _calculate_tools_size(compressed)
    pct = (original_size - final_size) / original_size * 100 if original_size else 0
    print(f"[ToolCompression] 压缩完成: {original_size} → {final_size} 字节 ({pct:.1f}% 减少)")
    return compressed
