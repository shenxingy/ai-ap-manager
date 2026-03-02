"""Gunicorn production configuration for the AP Manager backend."""
import multiprocessing

# ─── Worker config ───
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# ─── Bind ───
bind = "0.0.0.0:8000"

# ─── Timeouts ───
# LLM calls (especially claude_code subprocess) can take 60-90s; buffer at 120s
timeout = 120
graceful_timeout = 30
keepalive = 5

# ─── Logging ───
accesslog = "-"    # stdout
errorlog = "-"     # stderr
loglevel = "info"

# ─── Process naming ───
proc_name = "ap-manager-backend"
