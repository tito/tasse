FROM python:3.9-buster
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.1.13

RUN apt update && apt-get install -y build-essential
WORKDIR /tmp
RUN pip install "poetry==$POETRY_VERSION"

RUN mkdir -p /app
WORKDIR /app
COPY pyproject.toml poetry.lock /app/
RUN poetry install --no-dev --no-root --no-interaction --no-ansi
COPY server.py /app/
CMD ["poetry", "run", "python", "/app/server.py"]