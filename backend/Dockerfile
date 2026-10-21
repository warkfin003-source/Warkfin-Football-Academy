# Optional container deployment; Render currently uses the native Python runtime.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home academy
COPY --chown=academy:academy . .
# Run the web process without root privileges.
USER academy
EXPOSE 8000
# Database migrations and static collection must run as release/build steps first.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-"]
