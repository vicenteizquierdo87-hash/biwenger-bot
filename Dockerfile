FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y habilitar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Instalar dependencias del sistema necesarias (si las hubiera, por ahora solo dependencias de pip)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Crear el directorio de datos si no existe (aunque se montará como volumen)
RUN mkdir -p data

# Exponer el puerto para el health check de Koyeb
EXPOSE 8080

# Ejecutar el bot
CMD ["python", "src/main.py"]
