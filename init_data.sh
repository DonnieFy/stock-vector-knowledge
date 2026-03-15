#!/bin/bash
set -e
cd /home/fy/myown/knowledge/stock-vector-knowledge
source .venv/bin/activate
pip install --default-timeout=1000 -i https://pypi.tuna.tsinghua.edu.cn/simple -e . 2>&1
echo "=== pip install completed ==="
svk collect --full 2>&1
echo "=== collect --full completed ==="
svk merge --all 2>&1
echo "=== merge --all completed ==="
svk vectorize --rebuild 2>&1
echo "=== vectorize --rebuild completed ==="
echo "=== ALL DONE ==="
