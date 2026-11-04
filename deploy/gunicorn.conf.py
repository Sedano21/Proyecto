"""V20: configuración de gunicorn medida con prueba de carga (docs/35). Se ajusta sola al número de procesadores.
Variables opcionales en /etc/operaciones/operaciones.env: GUNICORN_WORKERS, GUNICORN_THREADS."""
import multiprocessing
import os

bind = "127.0.0.1:8000"
worker_class = "gthread"            # hilos: una exportación o un PDF lento no bloquea a los demás usuarios del proceso
workers = int(os.environ.get("GUNICORN_WORKERS") or multiprocessing.cpu_count() + 1)
threads = int(os.environ.get("GUNICORN_THREADS") or 4)
timeout = 120                       # cargas grandes de Excel y reportes
graceful_timeout = 30
keepalive = 75                      # mayor que el de Caddy (30 s): evita conexiones cortadas entre ambos
max_requests = 2000                 # cada proceso se renueva cada tanto (libera memoria)
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
