import json
import os
import logging

logger = logging.getLogger(__name__)

class Persistence:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        self.players_file = os.path.join(self.data_dir, "player_states.json")
        self.records_file = os.path.join(self.data_dir, "records.json")
        self.points_file = os.path.join(self.data_dir, "player_points.json")
        self.morning_file = os.path.join(self.data_dir, "morning_points.json")

    def load_player_states(self):
        """Carga el último estado conocido de los jugadores."""
        if os.path.exists(self.players_file):
            try:
                with open(self.players_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando estados de jugadores: {e}")
        return {}

    def save_player_states(self, states):
        """Guarda el estado actual de los jugadores."""
        try:
            with open(self.players_file, 'w', encoding='utf-8') as f:
                json.dump(states, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando estados de jugadores: {e}")

    def load_player_points(self):
        """Carga los puntos de los jugadores guardados tras el último partido."""
        if os.path.exists(self.points_file):
            try:
                with open(self.points_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando puntos de jugadores: {e}")
        return {}

    def save_player_points(self, points_dict):
        """Guarda el estado actual de puntos totales de cada jugador."""
        try:
            with open(self.points_file, 'w', encoding='utf-8') as f:
                json.dump(points_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando puntos de jugadores: {e}")

    def load_morning_points(self):
        """Carga los puntos guardados de madrugada para detectar el top 5 On Fire."""
        if os.path.exists(self.morning_file):
            try:
                with open(self.morning_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando puntos matutinos: {e}")
        return {}

    def save_morning_points(self, points_dict):
        """Guarda los puntos a primera hora del día."""
        try:
            with open(self.morning_file, 'w', encoding='utf-8') as f:
                json.dump(points_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando puntos matutinos: {e}")

    def load_records(self):
        """Carga los récords de la liga."""
        records = {
            "max_round_score": {"points": 0, "user": "", "round": ""},
            "leader_streak": {"user": "", "weeks": 0},
            "notified_matches": []
        }
        if os.path.exists(self.records_file):
            try:
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    records.update(loaded)
            except Exception as e:
                logger.error(f"Error cargando récords: {e}")
        return records

    def save_records(self, records):
        """Guarda los récords de la liga."""
        try:
            with open(self.records_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando récords: {e}")
