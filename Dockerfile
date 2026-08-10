FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=14002

EXPOSE 14002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "14002"]