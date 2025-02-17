FROM python:3.8-slim

WORKDIR /app

COPY bot_config.json bot.py ./

RUN pip install --no-cache-dir telepot requests matplotlib

CMD ["python", "bot.py"]
