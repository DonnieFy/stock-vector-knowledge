"""摘要格式验证"""

import re
from pathlib import Path

from rich.console import Console

from src.config import get_config

console = Console()

# 摘要必须包含的章节
REQUIRED_SECTIONS = [
    "所属板块",
    "主营业务",
    "题材标签",
]


def validate_summary(file_path: Path) -> list[str]:
    """
    验证单个摘要文件的格式。

    Args:
        file_path: 摘要MD文件路径

    Returns:
        问题列表（空列表表示通过）
    """
    issues = []

    if not file_path.exists():
        return [f"文件不存在: {file_path}"]

    content = file_path.read_text(encoding="utf-8")

    if not content.strip():
        return ["文件内容为空"]

    # 检查标题
    if not re.search(r"^#\s+\d{6}\s+", content, re.MULTILINE):
        issues.append("缺少标准标题格式 '# 股票代码 股票名称'")

    # 检查必需章节
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in content:
            issues.append(f"缺少必需章节: ## {section}")

    # 检查内容长度
    if len(content) < 50:
        issues.append("内容过短，可能数据不完整")

    return issues


def validate_all_summaries() -> dict[str, list[str]]:
    """
    验证所有摘要文件。

    Returns:
        {文件名: 问题列表} 的字典（仅包含有问题的文件）
    """
    config = get_config()
    summaries_dir = config.summaries_dir

    if not summaries_dir.exists():
        console.print("[yellow]摘要目录不存在[/yellow]")
        return {}

    results: dict[str, list[str]] = {}
    total = 0
    passed = 0

    for md_file in sorted(summaries_dir.glob("*.md")):
        total += 1
        issues = validate_summary(md_file)
        if issues:
            results[md_file.name] = issues
        else:
            passed += 1

    console.print(
        f"[{'green' if not results else 'yellow'}]"
        f"验证完成: {total} 个文件, {passed} 个通过, {len(results)} 个有问题"
        f"[/{'green' if not results else 'yellow'}]"
    )

    for filename, issues in results.items():
        console.print(f"  [red]{filename}[/red]:")
        for issue in issues:
            console.print(f"    - {issue}")

    return results
