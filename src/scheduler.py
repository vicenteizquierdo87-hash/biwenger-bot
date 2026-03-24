import logging
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from persistence import Persistence

logger = logging.getLogger(__name__)

class BiwengerScheduler:
    def __init__(self, bot_application, biwenger_api, chat_id=None):
        self.app = bot_application
        self.api = biwenger_api
        self.chat_id = chat_id
        
        # Biwenger usa la zona horaria de España
        self.tz = pytz.timezone('Europe/Madrid')
        self.persistence = Persistence()
        
    def start(self):
        """Inicia el scheduler usando la job_queue de Telegram."""
        if not self.chat_id:
            logger.warning("No hay CHAT_ID configurado. El bot no sabrá a qué grupo enviar los avisos automáticos.")
            return

        jq = self.app.job_queue
        
        # Tarea 1: Planificación diaria a las 04:00 AM
        from datetime import time
        jq.run_daily(self.plan_daily_matches_job, time=time(hour=4, minute=0, tzinfo=self.tz))
        
        # Tarea 2: Chivato de Bajas a las 08:30 AM
        jq.run_daily(self._check_player_status_job, time=time(hour=8, minute=30, tzinfo=self.tz))

        # Tarea 3: Previa diaria a las 09:00 AM
        jq.run_daily(self._daily_previa_job, time=time(hour=9, minute=0, tzinfo=self.tz))

        # Tarea 4: Jugadores On Fire a las 23:30 PM
        jq.run_daily(self._daily_on_fire_job, time=time(hour=23, minute=30, tzinfo=self.tz))
        
        # Tarea 5: Comprobador de partidos finalizados (cada 10 min)
        jq.run_repeating(self._check_finished_matches_job, interval=timedelta(minutes=10))
        
        logger.info("Scheduler de alarmas integrado en Telegram iniciado.")
        
        # Ejecutar inmediatamente por si encendemos el bot tarde
        jq.run_once(self.plan_daily_matches_job, when=1)

    async def plan_daily_matches_job(self, context):
        """Wrapper del trabajo diario dictado por python-telegram-bot"""
        await self._plan_daily_matches()

    async def _plan_daily_matches(self):
        """Busca y programa notificaciones para los partidos de la jornada actual agrupados por hora."""
        if not self.chat_id:
            return

        logger.info("Planificando alarmas para los partidos de hoy (agrupados por hora)...")
        
        # 1. LIMPIAR TRABAJOS PREVIOS para evitar duplicados
        job_names_to_clear = ["aviso_30min_jornada", "inicio_jornada", "end_of_day_points_tracker"]
        current_jobs = self.app.job_queue.jobs()
        for job in current_jobs:
            if job.name in job_names_to_clear or (job.name and job.name.startswith("alineacion_")):
                job.schedule_removal()
                logger.info(f"Trabajo previo {job.name} eliminado.")
        
        # 2. Obtener datos de Biwenger
        comp_data = self.api.get_rounds()
        if not comp_data:
            logger.error("No se han podido obtener los datos de la competición.")
            return

        # GUARDAR PUNTOS MATUTINOS para el On Fire
        players_data = comp_data.get('players', {})
        morning_points = {p_id: p_data.get('points', 0) for p_id, p_data in players_data.items()}
        self.persistence.save_morning_points(morning_points)
        
        active_events = comp_data.get('activeEvents', [])
        now = datetime.now(self.tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        matches_today = 0
        last_match_time = None
        first_match_of_round = None
        
        # Agrupamos los partidos por su hora de inicio (timestamp)
        matches_by_time = {} # {timestamp: [games]}
        processed_round_ids = set()

        for round_event in active_events:
            if round_event.get('type') != 'round':
                continue
            
            r_id = round_event.get('id')
            if r_id in processed_round_ids: continue
            processed_round_ids.add(r_id)
            
            games = round_event.get('games', [])
            for game in games:
                match_date_utc = datetime.fromtimestamp(game['date'], tz=pytz.UTC)
                match_date_local = match_date_utc.astimezone(self.tz)
                
                # Comprobar si el partido cae en el día de hoy
                if today_start <= match_date_local < today_end:
                    ts = int(game['date'])
                    if ts not in matches_by_time:
                        matches_by_time[ts] = []
                    matches_by_time[ts].append(game)
                    matches_today += 1
                    
                    # Guardar el último evento de hoy
                    if not last_match_time or match_date_local > last_match_time:
                        last_match_time = match_date_local
            
            # Identificar si es el inicio de la jornada total (el primer partido de toda la ronda)
            if games:
                sorted_games_round = sorted(games, key=lambda x: x['date'])
                first_game_total = sorted_games_round[0]
                first_match_utc = datetime.fromtimestamp(first_game_total['date'], tz=pytz.UTC)
                first_match_local = first_match_utc.astimezone(self.tz)
                
                # Si el primer partido de la ronda es hoy, programamos avisos de inicio de jornada
                if today_start <= first_match_local < today_end and first_match_local > now:
                    first_match_of_round = first_match_local
                    
                    # Alarma 30 min antes (Aviso de cierre de mercado)
                    warning_time = first_match_local - timedelta(minutes=30)
                    if warning_time > now:
                        self.app.job_queue.run_once(
                            self._notify_round_warning_30min_job,
                            when=warning_time,
                            name="aviso_30min_jornada"
                        )
                        logger.info(f"Alarma de 30 min para inicio de jornada programada a las {warning_time.strftime('%H:%M')}")

        # 3. Programar las alarmas agrupadas
        for ts, games in matches_by_time.items():
            match_date_local = datetime.fromtimestamp(ts, tz=pytz.UTC).astimezone(self.tz)
            alarm_time = match_date_local - timedelta(minutes=5)
            
            if alarm_time > now:
                is_round_start = (first_match_of_round and match_date_local == first_match_of_round)
                
                self.app.job_queue.run_once(
                    self._notify_batch_lineups_job,
                    when=alarm_time,
                    data={
                        'games': games,
                        'time': match_date_local.strftime('%H:%M'),
                        'is_round_start': is_round_start
                    },
                    name=f"alineacion_batch_{ts}"
                )
                logger.info(f"Alarma agrupada programada para las {alarm_time.strftime('%H:%M')} ({len(games)} partidos)")

        # 4. Programar cierre de jornada si hubo partidos hoy
        if matches_today > 0 and last_match_time:
            notify_time = last_match_time + timedelta(hours=2)
            if now < notify_time:
                self.app.job_queue.run_once(
                    self._track_live_points_job,
                    when=notify_time,
                    name="end_of_day_points_tracker"
                )
                logger.info(f"Seguimiento de puntos programado para las {notify_time.strftime('%H:%M')}")
        
        logger.info(f"Planificación completada. {matches_today} partidos organizados en {len(matches_by_time)} bloques horarios.")

    async def _notify_batch_lineups_job(self, context):
        """Notifica múltiples alineaciones en un solo mensaje."""
        data = context.job.data
        games = data['games']
        is_start = data.get('is_round_start', False)
        
        if is_start:
            msg = "🚀 *¡COMIENZA LA JORNADA!* 🚀\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"
            msg += "¡Alineaciones Guardadas! El mercado se ha cerrado. Mucha suerte a todos. 🍀🏆\n\n"
            msg += "⚽ *ALINEACIONES CONFIRMADAS:*"
        else:
            msg = "⚽ *¡ALINEACIONES CONFIRMADAS!*"
            
        msg += "\n━━━━━━━━━━━━━━━━━━━\n"
        
        for game in games:
            home = game.get('home', {}).get('name', 'Local')
            away = game.get('away', {}).get('name', 'Visitante')
            msg += f"⚔️ *{home}* vs *{away}*\n"
        
        msg += f"\n🕒 Los partidos empiezan a las {data['time']}\n"
        msg += "⏳ *¡Menos de 5 minutos para el pitido inicial!* 🏃‍♂️"
        
        await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')

    async def _notify_round_warning_30min_job(self, context):
        mensaje = (
            "⏳ *¡ÚLTIMO AVISO! (30 MIN)*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Quedan exactamente 30 minutos para que empiece la jornada.\n\n"
            "🚨 *¡Asegúrate de que tu alineación esté guardada!* A partir del inicio del primer partido ya no podrás hacer cambios. 🛑"
        )
        await self.app.bot.send_message(chat_id=self.chat_id, text=mensaje, parse_mode='Markdown')

    async def _track_live_points_job(self, context):
        """Notifica los puntos al finalizar la jornada del día."""
        logger.info("Notificando puntos de final de jornada...")
        data = self.api.get_round_standings()
        if not data or 'league' not in data:
            return

        standings = data['league'].get('standings', [])
        if not standings:
            return

        # Ordenar por puntos (actualmente total acumulado)
        standings.sort(key=lambda x: x.get('points', 0), reverse=True)

        txt = "📊 *Clasificación al Cierre de los Partidos*\n\n"
        records = self.persistence.load_records()
        max_changed = False

        for i, user in enumerate(standings[:10], 1):
            pts = user['points']
            txt += f"{i}. *{user['name']}*: {pts} pts\n"
            
            # Verificar récord de puntuación máxima
            if pts > records["max_round_score"]["points"]:
                records["max_round_score"] = {
                    "points": pts,
                    "user": user['name'],
                    "round": "Actual" # Podríamos intentar sacar el nombre de la jornada de 'data'
                }
                max_changed = True
        
        if max_changed:
            self.persistence.save_records(records)
            txt += "\n✨ *¡NUEVO RÉCORD DE LA LIGA!* ✨"
        
        txt += "\n_Actualizado automáticamente_ 🔄"
        await self.app.bot.send_message(chat_id=self.chat_id, text=txt, parse_mode='Markdown')


    async def _check_player_status_job(self, context):
        """Monitoriza cambios en el estado de los jugadores (lesiones, dudas, etc.)"""
        logger.info("Ejecutando chivato de bajas...")
        new_players = self.api.get_all_players()
        if not new_players: return

        old_states = self.persistence.load_player_states()
        changes = []

        # Solo monitorizamos jugadores con cierto valor o que estaban en el estado anterior
        # Para no saturar, nos centramos en cambios a estados "no OK"
        for p_id, p_data in new_players.items():
            p_name = p_data.get('name')
            new_status = p_data.get('status')
            
            if p_id in old_states:
                old_status = old_states[p_id].get('status')
                if new_status != old_status:
                    # Si antes estaba OK y ahora no, o si el estado ha cambiado significativamente
                    emojis = {"injured": "🚑", "warned": "⚠️", "suspended": "🟥", "doubt": "❓", "ok": "✅"}
                    old_icon = emojis.get(old_status, "⚪")
                    new_icon = emojis.get(new_status, "⚪")
                    
                    # Filtro: Solo avisar si pasa a algo preocupante o si vuelve a estar OK
                    if new_status in ["injured", "suspended", "doubt"] or (old_status != "ok" and new_status == "ok"):
                        changes.append(f"• *{p_name}*: {old_icon} → {new_icon}")

            # Guardar siempre el estado actual
            old_states[p_id] = {"name": p_name, "status": new_status}

        self.persistence.save_player_states(old_states)

        if changes:
            # Separar en dos listas: Bajas y Altas
            bajas = [c for c in changes if "✅" not in c.split("→")[1]]
            altas = [c for c in changes if "✅" in c.split("→")[1]]
            
            msg = "📢 *EL CHIVATO DE BAJAS*\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"
            
            if bajas:
                msg += "🚑 *Nuevas Bajas / Dudas:*\n"
                msg += "\n".join(bajas[:10]) + "\n\n"
            
            if altas:
                msg += "✅ *¡Vuelven al verde!*\n"
                msg += "\n".join(altas[:10]) + "\n\n"
            
            msg += "━━━━━━━━━━━━━━━━━━━\n"
            msg += "¡Revisad vuestras alineaciones! 🧐⚽️"
            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')

    async def _daily_previa_job(self, context):
        """Informa de los partidos que se juegan hoy."""
        logger.info("Enviando previa diaria...")
        comp_data = self.api.get_rounds()
        if not comp_data: return

        active_events = comp_data.get('activeEvents', [])
        now = datetime.now(self.tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        matches = []
        for event in active_events:
            if event.get('type') == 'round':
                for game in event.get('games', []):
                    g_time = datetime.fromtimestamp(game['date'], tz=pytz.UTC).astimezone(self.tz)
                    if today_start <= g_time < today_end:
                        matches.append(f"🕒 *{g_time.strftime('%H:%M')}*: {game['home']['name']} vs {game['away']['name']}")

        if matches:
            msg = "🗓️ *PREVIA DE HOY*\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n"
            msg += "Estos son los partidos que se juegan hoy:\n\n"
            msg += "\n".join(matches)
            msg += "\n━━━━━━━━━━━━━━━━━━━\n"
            msg += "¡Que no se os olvide el once! ⚽️"
            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')

    async def _daily_on_fire_job(self, context):
        """Informa de los mejores jugadores reales del día comparando con los puntos matutinos."""
        logger.info("Enviando informe On Fire...")
        comp_data = self.api.get_rounds()
        if not comp_data: return
        
        current_players = comp_data.get('players', {})
        morning_points = self.persistence.load_morning_points()
        
        if not morning_points:
            logger.warning("No hay puntos matutinos para comparar el On Fire.")
            return

        players = []
        for p_id, p_data in current_players.items():
            current_pts = p_data.get('points', 0)
            morning_pts = morning_points.get(p_id, current_pts)
            diff = current_pts - morning_pts
            if diff > 0:
                players.append((p_data.get('name', 'Desconocido'), diff))

        if players:
            # Ordenar por puntos y coger top 5
            players.sort(key=lambda x: x[1], reverse=True)
            top_players = players[:5]
            
            msg = "🔥 *JUGADORES ON FIRE DE HOY* 🔥\n\nLos cracks que más han sumado hoy en La Liga:\n\n"
            for i, p in enumerate(top_players, 1):
                msg += f"{i}. *{p[0]}*: {p[1]} pts\n"
            
            msg += "\n¡Vaya jugones! 🔝"
            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')

    async def _check_finished_matches_job(self, context):
        """Monitoriza si algún partido ha terminado de forma reciente para notificar puntos usando diff."""
        comp_data = self.api.get_rounds()
        if not comp_data: return
        
        active_events = comp_data.get('activeEvents', [])
        current_players = comp_data.get('players', {})
        
        records = self.persistence.load_records()
        notified = records.get("notified_matches", [])
        changed_notices = False
        
        # Cargar los puntos del último chequeo
        last_points = self.persistence.load_player_points()
        points_changed = False

        for event in active_events:
            if event.get('type') != 'round': continue
            
            for match in event.get('games', []):
                m_id = str(match.get('id', ''))
                status = str(match.get('status', '')).lower()
                
                # Si el partido terminó y no lo hemos avisado aún
                if status in ['finished', 'played', 'closed', 'postponed_closed'] and m_id not in notified:
                    home_id = match.get('home', {}).get('id')
                    away_id = match.get('away', {}).get('id')
                    home_name = match.get('home', {}).get('name', 'Local')
                    away_name = match.get('away', {}).get('name', 'Visitante')
                    
                    match_players = []
                    for p_id, p_data in current_players.items():
                        if p_data.get('teamID') in [home_id, away_id]:
                            fitness = p_data.get('fitness', [])
                            # Usamos fitness[0] como fuente más fiable del partido actual si está disponible
                            if fitness and fitness[0] is not None:
                                try:
                                    score = int(fitness[0])
                                    if score != 0: # Solo mostramos jugadores que han puntuado
                                        match_players.append({
                                            'name': p_data.get('name', 'Desconocido'),
                                            'score': score,
                                            'teamID': p_data.get('teamID')
                                        })
                                except (ValueError, TypeError):
                                    continue
                    
                    if match_players:
                        # Ordenar por puntuación descendente
                        match_players.sort(key=lambda x: x['score'], reverse=True)
                        
                        msg = f"🏁 *FINAL: {home_name} {match.get('home', {}).get('score')} - {match.get('away', {}).get('score')} {away_name}*\n"
                        msg += "━━━━━━━━━━━━━━━━━━━\n"
                        msg += "📊 *Puntuaciones del partido:*\n\n"
                        
                        # Agrupar por equipos
                        home_p = [p for p in match_players if p['teamID'] == home_id]
                        away_p = [p for p in match_players if p['teamID'] == away_id]
                        
                        if home_p:
                            msg += f"🏠 *{home_name.upper()}*\n"
                            for p in home_p:
                                icon = "🌟" if p['score'] >= 10 else "⭐" if p['score'] >= 6 else "▫️" if p['score'] >= 0 else "🔻"
                                msg += f"{icon} *{p['name']}*: {p['score']} pts\n"
                        
                        if away_p:
                            msg += f"\n🚀 *{away_name.upper()}*\n"
                            for p in away_p:
                                icon = "🌟" if p['score'] >= 10 else "⭐" if p['score'] >= 6 else "▫️" if p['score'] >= 0 else "🔻"
                                msg += f"{icon} *{p['name']}*: {p['score']} pts\n"
                            
                        msg += "\n━━━━━━━━━━━━━━━━━━━\n"
                        msg += "_Los puntos de los cronistas pueden ser provisionales_ ⚽"
                        
                        try:
                            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')
                            notified.append(m_id)
                            changed_notices = True
                            logger.info(f"Notificados puntos del partido {home_name} vs {away_name}")
                        except Exception as e:
                            logger.error(f"Error enviando notificación del partido: {e}")
                    else:
                        # Si han pasado más de 24h desde el inicio del partido y no hemos visto cambios de puntos,
                        # asumimos que nos lo perdimos mientras el bot estaba apagado y lo silenciamos.
                        try:
                            match_date = datetime.fromtimestamp(match.get('date', 0), tz=pytz.UTC)
                            if (datetime.now(pytz.UTC) - match_date).total_seconds() > 86400:
                                notified.append(m_id)
                                changed_notices = True
                                logger.info(f"El partido {home_name} vs {away_name} terminó hace mucho. Abortando monitorización de sus puntos.")
                        except Exception:
                            pass

        if changed_notices:
            records["notified_matches"] = notified
            self.persistence.save_records(records)
            
        # Actualizamos last_points en cada chequeo para mantener la consistencia
        if current_players:
            new_last_points = {p_id: p_data.get('points', 0) for p_id, p_data in current_players.items()}
            self.persistence.save_player_points(new_last_points)
