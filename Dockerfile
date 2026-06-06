FROM mcr.microsoft.com/playwright/python:v1.60.0-jammyWORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD gunicorn app:app --bind 0.0.0.0:$PORT
