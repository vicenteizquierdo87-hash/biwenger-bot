import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from biwenger import BiwengerAPI
from scheduler import BiwengerScheduler
from persistence import Persistence
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configuración básica de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Instanciar el cliente de Biwenger y persistencia
biwenger_api = BiwengerAPI()
persistence = Persistence()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start"""
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de Biwenger.\n\n"
        "Te avisaré del inicio de las jornadas, alineaciones 5 minutos antes y puntos.\n\n"
        "*(El sistema automático aún está en construcción, usa /test para comprobar que funciono)*"
    )

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando simple de prueba"""
    await update.message.reply_text("✅ El bot está conectado y funcionando correctamente.")

async def liga_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para probar la conexión con Biwenger obteniendo la info de la liga."""
    await update.message.reply_text("⏳ Conectando con Biwenger... obteniendo info de tu liga...")
    info = biwenger_api.get_league_info()
    if info:
        nombre = info.get('name', 'Desconocida')
        competicion = info.get('competition', 'Desconocida')
        usuarios = len(info.get('users', []))
        await update.message.reply_text(
            f"🏆 *Liga:* {nombre}\n"
            f"⚽ *Competición:* {competicion}\n"
            f"👥 *Participantes:* {usuarios}\n\n"
            f"¡Conexión con Biwenger completada con éxito! ✅",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Ha ocurrido un error al conectar con la API de Biwenger. Revisa tus tokens.")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando temporal para obtener el ID del grupo."""
    chat_id = update.message.chat_id
    await update.message.reply_text(f"El ID de este chat es:\n`{chat_id}`", parse_mode='Markdown')

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú principal con botones."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Puntos Jornada", callback_data='menu_puntos'),
            InlineKeyboardButton("🏆 Info Liga", callback_data='menu_liga')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎮 *Panel de Control Biwenger*\nElige una opción:", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las pulsaciones de los botones del menú."""
    query = update.callback_query
    await query.answer()

    if query.data == 'menu_puntos':
        await query.message.reply_text("📊 Consultando puntos en directo...")
        await puntos_command(update, context)
    elif query.data == 'menu_liga':
        await liga_command(update, context)
    elif query.data == 'menu_mercado':
        await mercado_command(update, context)
    elif query.data == 'menu_records':
        await records_command(update, context)
    elif query.data == 'menu_ayuda':
        await query.message.reply_text(
            "📖 *Comandos disponibles:*\n"
            "/menu - Panel de control\n"
            "/puntos - Clasificación jornada\n"
            "/liga - Info de tu liga\n"
            "/comparar `A vs B` - Compara jugadores\n"
            "/records - Salón de la fama",
            parse_mode='Markdown'
        )

async def mercado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los jugadores que están actualmente en el mercado."""
    origin = update.message if update.message else update.callback_query.message
    await origin.reply_text("🏟 *Consultando el mercado de fichajes...*")
    
    market = biwenger_api.get_market()
    if not market or 'sales' not in market:
        await origin.reply_text("❌ No se ha podido obtener el mercado.")
        return

    sales = market.get('sales', [])
    if not sales:
        await origin.reply_text("📭 El mercado está vacío ahora mismo.")
        return

    txt = "🏟 *JUGADORES EN EL MERCADO*\n\n"
    # Filtrar solo jugadores de la liga (no del sistema, aunque Biwenger suele mezclarlos)
    for sale in sales[:12]: # Top 12 para no saturar
        player = sale.get('player', {})
        price = sale.get('price', 0)
        user = sale.get('user', {}).get('name', 'Sistema')
        
        txt += f"👤 *{player.get('name')}* ({player.get('position')})\n"
        txt += f"💰 `{price:,}€` | 🏠 {user}\n\n"

    txt += "_Fíchalos antes de que te los quiten_ 🏃‍♂️"
    await origin.reply_text(txt, parse_mode='Markdown')

async def puntos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para obtener la clasificación en vivo de la jornada actual."""
    await update.message.reply_text("📊 Consultando puntos en directo de la jornada...")
    data = biwenger_api.get_round_standings()
    if not data or 'league' not in data:
        await update.message.reply_text("❌ No se han podido obtener los puntos. ¿Ha empezado ya la jornada?")
        return

    standings = data['league'].get('standings', [])
    if not standings:
        await update.message.reply_text("📭 Todavía no hay puntos registrados para esta jornada.")
        return

    # Ordenar por puntos de la jornada
    standings.sort(key=lambda x: x.get('points', 0), reverse=True)

    txt = "🏆 *Puntos de la Jornada*\n\n"
    for i, user in enumerate(standings, 1):
        txt += f"{i}. *{user['name']}*: {user['points']} pts\n"
    
    txt += "\n_Puntos actualizados en tiempo real_ ⚽"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def comparar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /comparar JugadorA vs JugadorB"""
    if not context.args:
        await update.message.reply_text("Uso: /comparar [jugador1] vs [jugador2]")
        return
    
    query = " ".join(context.args)
    if " vs " not in query.lower():
        await update.message.reply_text("Debes separar los nombres con 'vs'. Ejemplo: /comparar Pedri vs Gavi")
        return
    
    nombres = query.lower().split(" vs ")
    await update.message.reply_text(f"🔍 Buscando estadísticas de {nombres[0].title()} y {nombres[1].title()}...")
    
    p1 = biwenger_api.search_player(nombres[0].strip())
    p2 = biwenger_api.search_player(nombres[1].strip())
    
    if not p1 or not p2:
        error_msg = "❌ No he podido encontrar a alguno de los jugadores. Intenta ser más específico."
        if not p1: error_msg += f"\n- No encontré a '{nombres[0].strip()}'"
        if not p2: error_msg += f"\n- No encontré a '{nombres[1].strip()}'"
        await update.message.reply_text(error_msg)
        return

    def get_fitness_text(fitness):
        if not fitness: return "Sin datos"
        return " ".join([str(x) if x is not None else "-" for x in fitness[:5]])

    keyboard = [
        [InlineKeyboardButton("🏟 Ver Mercado", callback_data='menu_mercado')],
        [InlineKeyboardButton("🎮 Volver al Menú", callback_data='menu_ayuda')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def records_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el salón de la fama."""
    records = persistence.load_records()
    max_pts = records["max_round_score"]
    
    msg = (
        f"🏆 *SALÓN DE LA FAMA* 🏆\n\n"
        f"💎 *Máxima Puntuación:* {max_pts['points']} pts\n"
        f"🏅 *Rey de la Colina:* {max_pts['user']}\n"
        f"📅 *Logrado en:* {max_pts['round']}\n\n"
        f"¡Esforzaos para superar estos números! 💪"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Silenciar logs del health check para no ensuciar la consola
        return

def run_health_check_server():
    port = int(os.getenv("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logger.info(f"Health check server running on port {port}")
    httpd.serve_forever()

def main():
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "tu_token_de_telegram_aqui":
        logger.error("No se ha configurado el TELEGRAM_BOT_TOKEN en el archivo .env")
        print("\n\n❌ ERROR: Por favor, configura tu TELEGRAM_BOT_TOKEN en el archivo .env antes de iniciar el bot.\n\n")
        return

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        logger.warning("\n⚠️ ATENCIÓN: No has configurado TELEGRAM_CHAT_ID en .env.")
        logger.warning("El bot funcionará y responderá a los comandos, pero NO podrá enviar alarmas automáticas a ningún grupo.\n")

    # Inicializar la aplicación del bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Iniciar el motor de tareas programadas
    scheduler = BiwengerScheduler(bot_application=application, biwenger_api=biwenger_api, chat_id=chat_id)
    scheduler.start()

    # Añadir manejadores de comandos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("liga", liga_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("puntos", puntos_command))
    application.add_handler(CommandHandler("comparar", comparar_command))
    application.add_handler(CommandHandler("records", records_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("mercado", mercado_command))
    
    # Manejador de botones
    application.add_handler(CallbackQueryHandler(button_handler))

    # Iniciar servidor de health check para Koyeb en un hilo separado
    health_thread = threading.Thread(target=run_health_check_server, daemon=True)
    health_thread.start()

    logger.info("Iniciando el bot...")
    print("🤖 Bot iniciado y esperando mensajes...\nPulsa Ctrl+C para detenerlo.")
    
    # Iniciar el bot (polling)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
