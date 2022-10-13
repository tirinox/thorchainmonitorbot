FROM python:3.10-slim-buster as production

WORKDIR /app
ADD ./app/requirements.txt .

RUN apt-get update -y && \
    apt-get install git build-essential cmake pkg-config -y

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir discord.py --no-dependencies

CMD [ "python", "./main.py", "/config/config.yaml" ]