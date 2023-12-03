FROM python:3.8
WORKDIR /app
COPY . /app
# Install build essentials for compiling Python dependencies
RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install -r requirements.txt
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:flask_app"]

