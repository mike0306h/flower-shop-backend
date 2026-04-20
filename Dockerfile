FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3457

# 默认 DATABASE_URL（容器内网络用 flower-shop-postgres-1）
ENV DATABASE_URL=postgresql://postgres:postgres123@flower-shop-postgres-1:5432/flower_shop

# 单进程模式：确保登录限流等内存状态正确工作
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3457", "--workers", "1"]
