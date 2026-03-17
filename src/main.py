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
 
# Estados para la captura de sugerencias
SUGGESTION_WAITING = 1

# Cargar variables de entorno
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEV_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")

# Instanciar el cliente de Biwenger y persistencia
biwenger_api = BiwengerAPI()
persistence = Persistence()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start"""
    msg = (
        "👋 *¡HOLA! BIENVENIDO A TU BOT DE BIWENGER* ⚽\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Estaré vigilando tu liga las 24 horas para avisarte de:\n"
        "🚀 Inicio de jornadas\n"
        "📋 Alineaciones confirmadas (5 min antes)\n"
        "📊 Puntos en tiempo real\n"
        "🚑 Cambios de estado (Lesiones/Bajas)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎮 Usa `/menu` para ver todas las opciones.\n"
        "¡Mucha suerte! 🍀"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando simple de prueba"""
    await update.message.reply_text("✅ El bot está conectado y funcionando correctamente.")

async def liga_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para probar la conexión con Biwenger obteniendo la info de la liga."""
    msg_target = update.effective_message
    await msg_target.reply_text("⏳ Conectando con Biwenger... obteniendo info de tu liga...")
    info = biwenger_api.get_league_info()
    if info:
        nombre = info.get('name', 'Desconocida')
        competicion = info.get('competition', 'Desconocida')
        usuarios = len(info.get('users', []))
        msg = (
            f"🏆 *INFORMACIÓN DE LA LIGA* 🏆\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏟 *Nombre:* {nombre}\n"
            f"⚽ *Competición:* {competicion}\n"
            f"👥 *Participantes:* {usuarios}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"¡Conexión con Biwenger lista! ✅"
        )
        keyboard = [
            [InlineKeyboardButton("📩 Enviar Sugerencia", callback_data='menu_sugerencia')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg_target.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await msg_target.reply_text("❌ Ha ocurrido un error al conectar con la API de Biwenger. Revisa tus tokens.")

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
        ],
        [
            InlineKeyboardButton("⚖️ Comparar Jugadores", callback_data='menu_comparar'),
            InlineKeyboardButton("🔍 Buscar Jugador", callback_data='menu_jugador')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎮 *Panel de Control Biwenger*\nElige una opción:", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las pulsaciones de los botones del menú."""
    query = update.callback_query
    await query.answer()

    if query.data == 'menu_puntos':
        await puntos_command(update, context)
    elif query.data == 'menu_liga':
        await liga_command(update, context)
    elif query.data == 'menu_comparar':
        await query.message.reply_text(
            "⚖️ *Comparativa de Jugadores*\n\n"
            "Escribe el comando así:\n"
            "`/comparar Jugador1 vs Jugador2`",
            parse_mode='Markdown'
        )
    elif query.data == 'menu_jugador':
        await query.message.reply_text(
            "🔍 *Búsqueda de Jugador*\n\n"
            "Escribe el comando seguido del nombre:\n"
            "`/jugador Pedri`",
            parse_mode='Markdown'
        )
    elif query.data == 'menu_sugerencia':
        context.user_data['state'] = SUGGESTION_WAITING
        await query.message.reply_text(
            "📩 *ENVIAR SUGERENCIA*\n\n"
            "Escribe a continuación tu idea o sugerencia para mejorar el bot. "
            "Vicente la recibirá directamente en su chat privado. ✨",
            parse_mode='Markdown'
        )
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

async def suggestion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura y reenvía sugerencias al desarrollador."""
    if context.user_data.get('state') != SUGGESTION_WAITING:
        return

    msg = update.effective_message
    dev_id = os.getenv("DEVELOPER_CHAT_ID")
    
    if not dev_id:
        await msg.reply_text("❌ El sistema de sugerencias no está configurado (falta DEVELOPER_CHAT_ID en Render).")
        context.user_data['state'] = None
        return

    user = update.effective_user
    username = f"@{user.username}" if user.username else user.full_name
    
    forward_msg = (
        f"📩 *NUEVA SUGERENCIA DEL BOT* 📩\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *De:* {username} (ID: `{user.id}`)\n"
        f"📝 *Mensaje:*\n"
        f"\"{msg.text}\"\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"_Enviado desde el bot de Biwenger_ ⚽"
    )
    
    try:
        await context.bot.send_message(chat_id=dev_id, text=forward_msg, parse_mode='Markdown')
        await msg.reply_text("✅ ¡Muchas gracias! Tu sugerencia ha sido enviada con éxito. Vicente la revisará pronto.")
    except Exception as e:
        logger.error(f"Error reenviando sugerencia: {e}")
        await msg.reply_text("❌ No se ha podido enviar la sugerencia en este momento. Inténtalo más tarde.")
    
    context.user_data['state'] = None

async def jugador_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la ficha detallada de un jugador."""
    msg_target = update.effective_message
    if not context.args:
        await msg_target.reply_text("Uso: `/jugador [nombre]` (ej: `/jugador Gavi`)", parse_mode='Markdown')
        return
    
    query = " ".join(context.args).strip()
    await msg_target.reply_text(f"🔍 Buscando a *{query.title()}*...", parse_mode='Markdown')
    
    player = biwenger_api.search_player(query)
    if not player:
        await msg_target.reply_text(f"❌ No he podido encontrar a *{query}*. Intenta ser más específico.", parse_mode='Markdown')
        return

    # Formatear el estado
    st_emojis = {"injured": "🚑 Lesionado", "warned": "⚠️ Dudoso", "suspended": "🟥 Sancionado", "doubt": "❓ Duda", "ok": "✅ Disponible"}
    estado = st_emojis.get(player.get('status'), "✅ Disponible")

    # Formatear la posición
    pos_names = {"1": "Portero", "2": "Defensa", "3": "Centrocampista", "4": "Delantero"}
    posicion = pos_names.get(str(player.get('position')), "Jugador")

    # Construir el mensaje "Bonito"
    msg = (
        f"🌟 *FICHA DE JUGADOR* 🌟\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *{player['name'].upper()}*\n"
        f"🛡 *{player.get('teamName', 'La Liga')}* | 🏃‍♂️ *{posicion}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Valor:* `{player.get('price', 0):,}€`\n"
        f"📢 *Estado:* {estado}\n"
        f"🔥 *Forma:* `{get_fitness_text(player.get('fitness'))}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Puntos Totales:* {player.get('points', 0)} pts\n"
        f"📈 *Media:* {player.get('pointsPerGame', 0)} pts/partido\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"_Información actualizada de Biwenger_ ⚽"
    )

    keyboard = [
        [InlineKeyboardButton("⚖️ Comparar con otro", callback_data='menu_comparar')],
        [InlineKeyboardButton("🎮 Volver al Menú", callback_data='menu_ayuda')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg_target.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

def get_fitness_text(fitness):
    if not fitness: return "Sin datos"
    # Convertir puntos a círculos o iconos (verde si >= 6, amarillo si >= 2, rojo si < 2)
    icons = []
    for f in fitness[:5]:
        if f is None:
            icons.append("⚪")
            continue
        try:
            val = float(f)
            if val >= 6: icons.append("🟢")
            elif val >= 2: icons.append("🟡")
            else: icons.append("🔴")
        except (ValueError, TypeError):
            icons.append("⚪")
    return " ".join(icons)

async def puntos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para obtener la clasificación en vivo de la jornada actual."""
    msg_target = update.effective_message
    await msg_target.reply_text("📊 Consultando puntos en directo de la jornada...")
    data = biwenger_api.get_round_standings()
    if not data or 'league' not in data:
        await msg_target.reply_text("❌ No se han podido obtener los puntos. ¿Ha empezado ya la jornada?")
        return

    standings = data['league'].get('standings', [])
    if not standings:
        await msg_target.reply_text("📭 Todavía no hay puntos registrados para esta jornada.")
        return

    # Ordenar por puntos de la jornada
    standings.sort(key=lambda x: x.get('points', 0), reverse=True)

    txt = "🏆 *PUNTOS DE LA JORNADA* 🏆\n"
    txt += "━━━━━━━━━━━━━━━━━━━\n"
    for i, user in enumerate(standings, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
        txt += f"{medal} *{user['name']}*: {user['points']} pts\n"
    
    txt += "━━━━━━━━━━━━━━━━━━━\n"
    txt += "_Puntos actualizados en tiempo real_ ⚽"
    await msg_target.reply_text(txt, parse_mode='Markdown')

async def comparar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /comparar JugadorA vs JugadorB"""
    msg_target = update.effective_message
    if not context.args:
        await msg_target.reply_text("Uso: /comparar [jugador1] vs [jugador2]")
        return
    
    query = " ".join(context.args)
    if " vs " not in query.lower():
        await msg_target.reply_text("Debes separar los nombres con 'vs'. Ejemplo: /comparar Pedri vs Gavi")
        return
    
    nombres = query.lower().split(" vs ")
    await msg_target.reply_text(f"🔍 Buscando estadísticas de {nombres[0].title()} y {nombres[1].title()}...")
    
    p1 = biwenger_api.search_player(nombres[0].strip())
    p2 = biwenger_api.search_player(nombres[1].strip())
    
    if not p1 or not p2:
        error_msg = "❌ No he podido encontrar a alguno de los jugadores. Intenta ser más específico."
        if not p1: error_msg += f"\n- No encontré a '{nombres[0].strip()}'"
        if not p2: error_msg += f"\n- No encontré a '{nombres[1].strip()}'"
        await msg_target.reply_text(error_msg)
        return

    msg = (
        f"⚖️ *COMPARATIVA DE CRACKS* ⚖️\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *{p1['name']}* vs *{p2['name']}*\n"
        f"📍 *Pos:* {p1['position']} | {p2['position']}\n"
        f"📈 *Media:* {p1.get('points', 0)} | {p2.get('points', 0)} pts\n"
        f"🔥 *Forma:* `{get_fitness_text(p1.get('fitness'))}`\n"
        f"🔥 *Forma:* `{get_fitness_text(p2.get('fitness'))}`\n"
        f"📢 *Estado:* {p1.get('status', 'ok')} | {p2.get('status', 'ok')}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
    )

    keyboard = [
        [InlineKeyboardButton("🏟 Ver Mercado", callback_data='menu_mercado')],
        [InlineKeyboardButton("🎮 Volver al Menú", callback_data='menu_ayuda')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_target = update.effective_message
    await msg_target.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def records_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el salón de la fama."""
    records = persistence.load_records()
    max_pts = records["max_round_score"]
    
    msg = (
        f"🏆 *SALÓN DE LA FAMA* 🏆\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💎 *Máxima Puntuación Total:*\n"
        f"   *{max_pts['points']} pts*\n\n"
        f"🏅 *Rey de la Colina:* {max_pts['user']}\n"
        f"📅 *Logrado en:* {max_pts['round']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
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
    application.add_handler(CommandHandler("jugador", jugador_command))
    
    # Manejador de sugerencias (mensajes de texto que no son comandos)
    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, suggestion_handler))
    
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
