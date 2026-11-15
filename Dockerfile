FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then \
      PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi \
    && useradd --uid 10001 --create-home clinic
COPY --chown=clinic:clinic . .
RUN mkdir -p /app/.data && chown clinic:clinic /app /app/.data && chmod 700 /app/.data
USER clinic
# Static collection uses development settings during image build; no production secrets are embedded.
RUN python manage.py collectstatic --noinput && rm -f .local-secret
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--forwarded-allow-ips", ""]
