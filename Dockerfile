FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py populateAppList.py home.html .

RUN useradd --uid 10001 --no-create-home appuser
USER 10001

# settings.json is mounted at /app/settings.json at runtime.
EXPOSE 8000
# A full compare makes one Steam lookup per uncached game, so it can run for minutes.
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "600", "--access-logfile", "-"]
