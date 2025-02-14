
FROM python:3.10-slim


WORKDIR /app


COPY . .


RUN python -c "import json; config = json.load(open('config-weather-adaptor.json')); \
    import os; os.system(f'pip install --no-cache-dir ' + ' '.join(config['dependencies']))"


CMD ["python", "./weather_adaptor.py"]
