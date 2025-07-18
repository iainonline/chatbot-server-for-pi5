import os
from dotenv import load_dotenv

load_dotenv()

bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8080')
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = 'eventlet'
worker_connections = 1000
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
max_requests = 1000
max_requests_jitter = 50
preload_app = True
