# 🤖 Biwenger Telegram Bot

¡Bienvenido al bot definitivo para gestionar tu comunidad de Biwenger! Este bot está diseñado para mantener a todos los participantes informados en tiempo real sobre lo que ocurre en la liga, automatizar avisos importantes y facilitar la consulta de estadísticas.

---

## 🚀 Funcionalidades Principales

El bot trabaja por ti las 24 horas del día para que no se te escape nada:

### 🔔 Notificaciones Automáticas
- **Inicio de Jornada:** Avisos antes de que empiece el primer partido para que nadie olvide su alineación.
- **Alineaciones Confirmadas:** Notificación 5 minutos antes del inicio de cada partido con el 11 titular confirmado.
- **Puntos en Tiempo Real:** Actualizaciones en vivo de los puntos que van sumando los jugadores durante los partidos.
- **Cambios de Estado:** Alertas inmediatas cuando un jugador cambia su estado (lesiones, recuperaciones, sanciones o dudas).
- **Resumen Diario:** Resumen diario de noticias relevantes de la liga.

### 🎮 Comandos e Interacción
- **Menú Interactivo (`/menu`):** Un panel de control con botones para acceder rápidamente a todas las funciones.
- **Consulta de Puntos (`/puntos`):** Mira la clasificación en vivo de la jornada actual.
- **Mercado de Fichajes (`/mercado`):** Consulta quién está a la venta sin entrar en la app.
- **Buscador de Jugadores (`/jugador [nombre]`):** Ficha técnica completa de cualquier jugador (valor, forma, estado, media de puntos).
- **Comparador (`/comparar A vs B`):** Compara las estadísticas de dos jugadores cara a cara.
- **Salón de la Fama (`/records`):** Consulta las puntuaciones máximas históricas de tu liga.

---

## 🛠️ Configuración y Requisitos

### 1. Obtención de Tokens
Para que el bot funcione, necesitas:
- **Telegram Bot Token:** Pídeselo a [@BotFather](https://t.me/botfather).
- **Biwenger Token:** Se obtiene inspeccionando el tráfico de red en la web de Biwenger (header `Authorization`).
- **Biwenger League ID:** El ID numérico de tu liga.
- **Telegram Chat ID:** El ID del grupo donde el bot enviará los avisos (puedes usar `/id` en el bot para saberlo).

### 2. Variables de Entorno
Crea un archivo `.env` basado en `.env.example`:
```env
TELEGRAM_BOT_TOKEN=tu_token_aqui
BIWENGER_TOKEN=tu_token_aqui
BIWENGER_LEAGUE_ID=tu_id_aqui
TELEGRAM_CHAT_ID=id_del_grupo_aqui
DEVELOPER_CHAT_ID=tu_id_para_sugerencias_aqui
```

---

## 📦 Instalación y Ejecución

### Local (Python)
1. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Ejecuta el bot:
   ```bash
   python src/main.py
   ```

### Docker (Recomendado)
```bash
docker-compose up -d --build
```

---

## ☁️ Despliegue
El bot está listo para ser desplegado en plataformas como **Render**, **Koyeb** o **Railway**.
- Puerto por defecto para Health Check: `8080` (configurado automáticamente).
- Incluye `Dockerfile` optimizado.

---

## 📩 Sugerencias
¿Tienes alguna idea para mejorar el bot? Usa el botón **"Enviar Sugerencia"** en el menú del bot y me llegará directamente. ✨

---
*Desarrollado con ❤️ para comunidades competitivas de Biwenger.*
