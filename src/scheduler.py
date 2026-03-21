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
        """Busca y programa notificaciones para los partidos de la jornada actual."""
        if not self.chat_id:
            return

        logger.info("Planificando alarmas para los partidos de hoy...")
        
        # Recuperamos la información general (que incluye jornadas/eventos en activeEvents)
        comp_data = self.api.get_rounds()
        if not comp_data:
            logger.error("No se han podido obtener los datos de la competición.")
            return
            
        # GUARDAR PUNTOS MATUTINOS para el On Fire
        players_data = comp_data.get('players', {})
        morning_points = {p_id: p_data.get('points', 0) for p_id, p_data in players_data.items()}
        self.persistence.save_morning_points(morning_points)
        
        active_events = comp_data.get('activeEvents', [])
        
        # Obtenemos el inicio del día local y final
        now = datetime.now(self.tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        matches_today = 0
        last_event_time = None
        first_event_today = None
        
        # Recorremos los eventos activos (normalmente solo hay uno de tipo 'round')
        for round_event in active_events:
            if round_event.get('type') != 'round':
                continue
                
            games = round_event.get('games', [])
            # El primer partido de la jornada total
            first_game_total = None
            if games:
                # Los juegos suelen venir ordenados por fecha, pero por si acaso:
                sorted_games = sorted(games, key=lambda x: x['date'])
                first_game_total = sorted_games[0]

                # Notificación de inicio de jornada
                first_match_utc = datetime.fromtimestamp(first_game_total['date'], tz=pytz.UTC)
                first_match_local = first_match_utc.astimezone(self.tz)
                if today_start <= first_match_local < today_end and first_match_local > now:
                     # Alarma 30 min antes
                     warning_time = first_match_local - timedelta(minutes=30)
                     if warning_time > now:
                         self.app.job_queue.run_once(
                                self._notify_round_warning_30min_job,
                                when=warning_time,
                                name="aviso_30min_jornada"
                            )
                         logger.info(f"Alarma de 30 min para inicio de jornada programada a las {warning_time.strftime('%H:%M')}")

                     # Alarma de inicio (5 min antes para que de tiempo a leer antes del piteo)
                     start_notify_time = first_match_local - timedelta(minutes=5)
                     if start_notify_time > now:
                         self.app.job_queue.run_once(
                                self._notify_round_start_job,
                                when=start_notify_time,
                                data={'first_match': f"{first_game_total['home']['name']} vs {sorted_games[0]['away']['name']}"},
                                name="inicio_jornada"
                            )
                         logger.info(f"Alarma de inicio de jornada programada a las {start_notify_time.strftime('%H:%M')}")

            for game in games:
                match_date_utc = datetime.fromtimestamp(game['date'], tz=pytz.UTC)
                match_date_local = match_date_utc.astimezone(self.tz)
                
                # Comprobar si el partido cae en el día de hoy
                if today_start <= match_date_local < today_end:
                    home_team = game.get('home', {}).get('name', 'Local')
                    away_team = game.get('away', {}).get('name', 'Visitante')
                    
                    # Alarma de alineaciones 5 min antes
                    alarm_time = match_date_local - timedelta(minutes=5)
                    
                    if alarm_time > now:
                        self.app.job_queue.run_once(
                            self._notify_lineups_job,
                            when=alarm_time,
                            data={
                                'match_id': game.get('id'),
                                'home': home_team,
                                'away': away_team,
                                'time': match_date_local.strftime('%H:%M')
                            },
                            name=f"alineacion_{game.get('id')}"
                        )
                        matches_today += 1
                        logger.info(f"Alarma programada a las {alarm_time.strftime('%H:%M')} para {home_team} vs {away_team}")
                    
                    # Guardar el primer evento de hoy para programar el tracker de puntos
                    if not first_event_today or match_date_local < first_event_today:
                        first_event_today = match_date_local
                    
                    # Guardar el último evento de hoy
                    if not last_event_time or match_date_local > last_event_time:
                        last_event_time = match_date_local

        # Notificar la clasificación solo al final de los partidos de hoy
        if matches_today > 0:
            notify_time = last_event_time + timedelta(hours=2) # 2 horas después del inicio del último partido
            if now < notify_time:
                self.app.job_queue.run_once(
                    self._track_live_points_job,
                    when=notify_time,
                    name="end_of_day_points_tracker"
                )
                logger.info(f"Seguimiento de puntos programado para el final de la jornada a las {notify_time.strftime('%H:%M')}")
        
        logger.info(f"Se han programado {matches_today} alarmas de alineaciones para hoy.")

    async def _notify_round_warning_30min_job(self, context):
        mensaje = (
            "⏳ *¡ÚLTIMO AVISO! (30 MIN)*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Quedan exactamente 30 minutos para que empiece la jornada.\n\n"
            "🚨 *¡Asegúrate de que tu alineación esté guardada!* A partir del inicio del primer partido ya no podrás hacer cambios. 🛑"
        )
        await self.app.bot.send_message(chat_id=self.chat_id, text=mensaje, parse_mode='Markdown')

    async def _notify_round_start_job(self, context):
        match_info = context.job.data.get('first_match', 'el primer partido')
        mensaje = (
            "🚀 *¡COMIENZA LA JORNADA!* 🚀\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"El primer partido (*{match_info}*) está a punto de empezar.\n\n"
            "¡Alineaciones Guardadas! Mucha suerte a todos en Biwenger. 🍀🏆"
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

    async def _notify_lineups_job(self, context):
        data = context.job.data
        mensaje = (
            f"⚽ *¡ALINEACIONES CONFIRMADAS!*\n\n"
            f"⚔️ {data['home']} vs {data['away']}\n"
            f"🕒 El partido empieza a las {data['time']}\n\n"
            f"⏳ *¡Tienes menos de 5 minutos para hacer cambios en Biwenger!*"
        )
        await self.app.bot.send_message(chat_id=self.chat_id, text=mensaje, parse_mode='Markdown')

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
                    
                    scored_players = []
                    played_teams_players = []
                    
                    for p_id, p_data in current_players.items():
                        if p_data.get('teamID') in [home_id, away_id]:
                            played_teams_players.append(p_id)
                            current_pts = p_data.get('points', 0)
                            old_pts = last_points.get(p_id, current_pts)
                            diff = current_pts - old_pts
                            if diff != 0:
                                scored_players.append((p_data.get('name', 'Desconocido'), diff))
                    
                    # Si detectamos que han cambiado los puntos para los jugadores de este partido
                    if scored_players:
                        scored_players.sort(key=lambda x: x[1], reverse=True)
                        
                        msg = f"🏁 *FINAL: {home_name} vs {away_name}*\n"
                        msg += "━━━━━━━━━━━━━━━━━━━\n"
                        msg += "📊 *Puntuaciones del partido:*\n\n"
                        
                        for p in scored_players:
                            icon = "🌟" if p[1] >= 10 else "⭐" if p[1] >= 6 else "▫️" if p[1] >= 0 else "🔻"
                            msg += f"{icon} *{p[0]}*: {p[1]} pts\n"
                            
                        msg += "━━━━━━━━━━━━━━━━━━━\n"
                        msg += "_Los puntos de los cronistas pueden ser provisionales_ ⚽"
                        
                        try:
                            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')
                            notified.append(m_id)
                            changed_notices = True
                            logger.info(f"Notificados puntos del partido {home_name} vs {away_name}")
                            
                            # Actualizamos last_points solo para estos jugadores para no sobreescribir otros
                            for p_id in played_teams_players:
                                last_points[p_id] = current_players.get(p_id, {}).get('points', 0)
                            points_changed = True
                            
                        except Exception as e:
                            logger.error(f"Error enviando notificación del partido: {e}")
                    else:
                        # Si han pasado más de 24h desde el inicio del partido y no hemos visto cambios de puntos,
                        # asumimos que nos lo perdimos mientras el bot estaba apagado y lo silenciamos.
                        try:
                            import pytz
                            from datetime import datetime
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
            
        if points_changed:
            self.persistence.save_player_points(last_points)
        
        # Inicializar todos los jugadores en el primer run si no existen guardados
        if not last_points and current_players:
            for p_id, p_data in current_players.items():
                last_points[p_id] = p_data.get('points', 0)
            self.persistence.save_player_points(last_points)
