# Basic docker

FROM python:3.10-slim

WORKDIR /app

COPY weather-adaptor.py .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python", "weather-adaptor.py"]
