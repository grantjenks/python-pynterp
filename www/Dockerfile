FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG PYNTERP_VERSION=0.3.3

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
        "flask==3.*" \
        "gunicorn==25.*" \
        "pynterp==${PYNTERP_VERSION}"

COPY app.py /app/
COPY templates /app/templates

ARG FLAG_VALUE

RUN mkdir -p /challenge \
    && test -n "$FLAG_VALUE" \
    && printf '%s\n' "$FLAG_VALUE" > /challenge/flag.txt \
    && chmod 0444 /challenge/flag.txt

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "15", "app:app"]
