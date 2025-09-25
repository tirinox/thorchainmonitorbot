# Use a supported base (Debian bookworm)
FROM python:3.11-slim AS production

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 2) Copy only requirements first to leverage Docker cache
COPY app/requirements.txt ./requirements.txt

# 3) Install Python deps
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir discord.py --no-dependencies

# 4) Copy the rest of your app (so CMD can find ./main.py)
COPY app/ .

# 5) Run
CMD ["python", "./main.py", "/config/config.yaml"]