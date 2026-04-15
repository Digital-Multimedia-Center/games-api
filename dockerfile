FROM python:3.11-slim

# Install cron (Debian slim uses apt)
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Setup Cron for Debian
RUN echo "0 3 * * * root . /etc/environment; /usr/local/bin/python /app/main.py >> /var/log/cron.log 2>&1" > /etc/cron.d/python-cron
RUN chmod 0644 /etc/cron.d/python-cron
RUN touch /var/log/cron.log

RUN ln -sf /dev/stdout /var/log/cron.log
CMD ["sh", "-c", "printenv > /etc/environment && /usr/local/bin/python /app/main.py && cron -f"]
