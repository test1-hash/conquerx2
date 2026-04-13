FROM caddy:2.10.0 AS caddy

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=caddy /usr/bin/caddy /usr/bin/caddy

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/railway-entrypoint.sh

CMD ["/app/railway-entrypoint.sh"]
