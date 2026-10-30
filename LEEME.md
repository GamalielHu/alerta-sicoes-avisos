# Avisos SICOES

Servidor de avisos de la app Alerta SICOES. GitHub Actions revisa el SICOES cada 15 minutos (`servidor/vigilar.py`) y avisa por Firebase y ntfy. El estado vive en la rama `avisos-estado`.

Secrets: `FIREBASE_CUENTA` (opcional) y `NTFY_TEMA` (opcional).
