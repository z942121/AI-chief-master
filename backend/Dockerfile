FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（Chroma 需要原生库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml ./

# 安装 Python 依赖
# 注：oss2 为阿里云 OSS 旧版 SDK，代码中使用 import oss2
# pyproject.toml 中的 alibabacloud-oss-v2 是新版 SDK，import 路径不同
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e . && \
    pip install --no-cache-dir oss2

# 复制应用代码
COPY app ./app
COPY data ./data

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
