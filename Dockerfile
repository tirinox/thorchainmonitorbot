FROM python:3.8-slim-buster as production

# dont forget to map source to /app volume

WORKDIR /app
ADD ./app/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "./main.py" ]