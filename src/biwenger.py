import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class BiwengerAPI:
    def __init__(self):
        self.token = os.getenv("BIWENGER_TOKEN")
        self.league_id = os.getenv("BIWENGER_LEAGUE_ID")
        self.base_url = "https://biwenger.as.com/api/v2"
        self.user_id = self._fetch_user_id()

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "X-League": self.league_id,
            "X-User": self.user_id,
            "X-Version": "",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Referer": "https://biwenger.as.com/"
        }

    def _fetch_user_id(self):
        url = f"{self.base_url}/account"
        headers_account = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
        }
        try:
            response = requests.get(url, headers=headers_account)
            response.raise_for_status()
            data = response.json().get('data', {})
            for league in data.get('leagues', []):
                if str(league.get('id')) == str(self.league_id):
                    return str(league.get('user', {}).get('id', ''))
            return ""
        except Exception:
            return ""
    def _get(self, endpoint, params=None):
        """Método base para realizar peticiones GET a la API."""
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == 200:
                return data.get("data")
            else:
                logger.error(f"Error en API Biwenger: {data}")
                return None
        except Exception as e:
            logger.error(f"Excepción conectando a API Biwenger ({endpoint}): {e}")
            logger.error(f"Status Code: {getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'}")
            logger.error(f"Response: {getattr(e.response, 'text', 'N/A') if hasattr(e, 'response') else 'N/A'}")
            return None

    def get_league_info(self):
        """Obtiene información general de la liga."""
        return self._get("league")

    def get_account(self):
        """Obtiene la info de la cuenta sin headers restrictivos."""
        url = f"{self.base_url}/account"
        headers_account = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
        }
        try:
            response = requests.get(url, headers=headers_account)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Error account: {e}")
            return None

    def get_market(self):
        """Obtiene el estado actual del mercado de fichajes."""
        return self._get("market")
        
    def get_rounds(self):
        """Devuelve el listado de las jornadas (rounds) y su estado."""
        params = {"lang": "es", "score": "5"}
        return self._get("competitions/la-liga/data", params=params)

    def get_live_scores(self):
        """Obtiene las puntuaciones en vivo de la jornada actual."""
        params = {"lang": "es"}
        return self._get("competitions/la-liga/live", params=params)

    def get_round_standings(self):
        """Obtiene la clasificación de la jornada actual de la liga."""
        return self._get("rounds/league")

    def get_fixtures(self):
        """Obtiene los partidos de la jornada actual."""
        params = {"competition": "la-liga"}
        return self._get("rounds", params=params)

    def get_all_players(self):
        """Obtiene todos los jugadores de la liga con sus estados."""
        data = self.get_rounds()
        return data.get("players", {}) if data else {}

    def search_player(self, name):
        """Busca un jugador por nombre (búsqueda simple)."""
        players = self.get_all_players()
        name_lower = name.lower()
        for p_id, p_data in players.items():
            if name_lower in p_data.get("name", "").lower() or name_lower in p_data.get("slug", "").lower():
                return p_data
        return None

if __name__ == '__main__':
    import json
    logging.basicConfig(level=logging.INFO)
    api = BiwengerAPI()
    print("Probando conexión a la API...")
    info = api.get_league_info()
    if info:
        print(f"✅ Conectado a la liga: {info.get('name')}")
        print("--- DEBUG JSON LEAGUE ---")
        # Imprimimos de manera bonita las claves para entender qué mandan
        print(json.dumps(list(info.keys()), indent=2))
        if 'standings' in info:
            print("Standings:", len(info['standings']))
        elif 'users' in info:
            print("Users:", len(info['users']))
        else:
            print("Estructura devuelta recortada:")
            print({k: type(v) for k, v in info.items()})
    else:
        print("❌ Error de conexión con la liga")
