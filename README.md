# A股题材向量知识库 (Stock Vector Knowledge)

A股上市公司题材向量知识库，支持自动化数据采集、LLM驱动的题材筛选摘要、向量化查询与聚类分析。

## ✨ 核心能力

1. **📡 插件化数据采集** - 内置东方财富/同花顺采集器（基于akshare），支持扩展更多数据源
2. **🤖 SKILL驱动的LLM筛选** - 提供标准化SKILL文件，由Claude Code/openClaw半自动化完成题材提炼
3. **🔍 向量化查询** - 基于ChromaDB的题材向量数据库，支持相似查询和拓扑聚类

## 📁 目录结构

```
├── src/                    # 源码
│   ├── collectors/         # 插件化数据采集器
│   ├── processors/         # 数据处理辅助工具
│   └── vectordb/           # 向量化与查询
├── data/
│   ├── drafts/             # 草稿箱(原始采集数据)
│   ├── summaries/          # 最终摘要(每股一个MD)
│   ├── vectordb/           # ChromaDB持久化
│   └── jiuyangongshe/      # 韭研公社异动数据
│       └── action/         # 每日异动(按日期存储JSON)
├── .agent/skills/          # Claude Code SKILL文件
└── prompts/examples/       # 提示词样例
```

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd stock-vector-knowledge

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -e .

# 复制配置文件
cp config.example.yaml config.yaml
```

### 使用

```bash
# 1. 全量采集数据 (首次)
svk collect --full

# 2. 增量采集 (日常)
svk collect --incremental

# 3. 合并多来源草稿
svk merge --all

# 4. 用 Claude Code 执行题材筛选和摘要 (参见 .agent/skills/)

# 5. 向量化写入
svk vectorize --rebuild

# 6. 查询
svk query "光伏组件" --top 10        # 文本相似查询
svk similar 600519 --top 10          # 股票相似查询
svk cluster 600519 000001 300750     # 拓扑聚类

# 7. 韭研公社异动数据
svk jiuyangongshe-action                          # 采集今天
svk jiuyangongshe-action --date 2025-01-23         # 指定日期
svk jiuyangongshe-action --start 2025-01-20 --end 2025-01-23  # 批量采集
svk jiuyangongshe-industry                                    # 产业异动(增量合并)
svk jiuyangongshe-timeline                                    # 事件时间线(增量合并)
```

## ⚙️ 配置

复制 `config.example.yaml` 为 `config.yaml`：

```yaml
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"   # 嵌入模型
  device: "cpu"                            # cpu/cuda/mps

collectors:
  enabled: ["eastmoney", "ths"]
  request_interval: 1.0

jiuyangongshe:
  phone: "手机号"        # 自动登录用
  password: "密码"
  token: "从浏览器获取"   # 首次需手动填入，后续自动刷新
  timestamp: "..."
  cookies: "..."
```

## 🔌 扩展采集器

创建新文件继承 `BaseCollector` 并用 `@register_collector` 装饰器注册：

```python
from src.collectors.base import BaseCollector
from src.collectors.registry import register_collector

@register_collector
class MyCollector(BaseCollector):
    name = "my_source"
    # 实现 collect_full / collect_incremental
```

## 📝 License

MIT
