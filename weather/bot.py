import telepot
from telepot.loop import MessageLoop
import requests
import json
import time


CATALOG_URL = "http://localhost:8080"
RASPBERRY_URL = "http://localhost:8082"
TIME_SERIES_URL = "http://localhost:8081"

class AirQualityBot:
    def __init__(self, token):
        self.bot = telepot.Bot(token)
        self.user_data = {} 
        self.start_bot()

    def start_bot(self):
        MessageLoop(self.bot, self.on_chat_message).run_as_thread()
        print("Bot is running...")

    def on_chat_message(self, msg):
        chat_id = msg['chat']['id']
        text = msg.get('text', '').strip()
        user_name = msg['from'].get('first_name', 'User')

        if text == "/start":
            self.handle_start(chat_id, user_name)
        elif text == "/register":
            self.request_room_registration(chat_id, user_name)
        elif text == "/status":
            self.request_room_status(chat_id)
        elif text == "/control":
            self.request_control_action(chat_id)
        else:
            self.handle_text_input(chat_id, text)

    def handle_start(self, chat_id, user_name):
        """ Accueil de l'utilisateur et vérification de son enregistrement """
        user_info = self.get_user_info(chat_id)
        if user_info:
            rooms = ', '.join(user_info["rooms"])
            self.bot.sendMessage(chat_id, f"Hello {user_name}, welcome back!\nYour rooms: {rooms}\nUse /status or /control.")
        else:
            self.bot.sendMessage(chat_id, "Hello! You are not registered yet.\nUse /register to add your rooms.")

    def request_room_registration(self, chat_id, user_name):
        """ Demande à l'utilisateur d'entrer ses rooms """
        self.bot.sendMessage(chat_id, "Enter your room numbers (e.g., '101 102'):")
        self.user_data[chat_id] = {"name": user_name, "rooms": []}
        self.bot_listener = ("register", chat_id)

    def register_user(self, chat_id, room_ids):
        """ Enregistre les salles et les envoie au catalogue """
        try:
            rooms = room_ids.split()
            payload = {"username": self.user_data[chat_id]["name"], "telegramChatID": chat_id, "rooms": rooms}
            response = requests.post(f"{CATALOG_URL}/users", json=payload)
            
            if response.status_code == 200:
                self.user_data[chat_id]["rooms"] = rooms
                self.bot.sendMessage(chat_id, f"✅ Registered! Rooms: {', '.join(rooms)}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Registration failed: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error registering: {e}")

    def request_room_status(self, chat_id):
        """ Demande à l'utilisateur de sélectionner une salle avant de récupérer son état """
        user_info = self.get_user_info(chat_id)
        if user_info:
            self.bot.sendMessage(chat_id, "Enter the room number to check status:")
            self.bot_listener = ("status", chat_id)
        else:
            self.bot.sendMessage(chat_id, "You need to register first. Use /register.")

    def fetch_room_status(self, chat_id, room):
        """ Récupère et affiche l'état de la salle """
        try:
            response = requests.get(f"{TIME_SERIES_URL}/aqi", params={"room": room})
            if response.status_code == 200:
                status = response.json()
                self.bot.sendMessage(chat_id, f"📊 Room {room} Air Quality: {status}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Error fetching status: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error: {e}")

    def request_control_action(self, chat_id):
        """ Demande à l'utilisateur une action sur les actuateurs """
        user_info = self.get_user_info(chat_id)
        if user_info:
            self.bot.sendMessage(chat_id, "Enter: '<room> <action>' (e.g., '101 open_window')")
            self.bot_listener = ("control", chat_id)
        else:
            self.bot.sendMessage(chat_id, "You need to register first. Use /register.")

    def send_control_command(self, chat_id, room_action):
        """ Envoie une commande à un actuateur """
        try:
            room, action = room_action.split()
            if action not in ["open_window", "close_window", "activate_ventilation", "stop_ventilation"]:
                self.bot.sendMessage(chat_id, "Invalid action. Use: open_window, close_window, activate_ventilation, stop_ventilation.")
                return

            actuator = "windows" if "window" in action else "ventilation"
            state = "Open" if action == "open_window" else "Closed" if action == "close_window" else "On" if action == "activate_ventilation" else "Off"
            
            response = requests.put(f"{RASPBERRY_URL}/{actuator}", params={"state": state})
            if response.status_code == 200:
                self.bot.sendMessage(chat_id, f"✅ {action} executed in room {room}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Error executing {action}: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error: {e}")

    def handle_text_input(self, chat_id, text):
        """ Gère les réponses utilisateurs en fonction du contexte """
        if hasattr(self, "bot_listener") and self.bot_listener[1] == chat_id:
            command = self.bot_listener[0]

            if command == "register":
                self.register_user(chat_id, text)
            elif command == "status":
                self.fetch_room_status(chat_id, text)
            elif command == "control":
                self.send_control_command(chat_id, text)

            del self.bot_listener

    def get_user_info(self, chat_id):
        """ Vérifie si l'utilisateur est enregistré et retourne ses informations """
        try:
            response = requests.get(f"{CATALOG_URL}/users/{chat_id}")
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

bot_instance = AirQualityBot("7847206958:AAGvH3qIjyyLmkfG4o0HjrDpNsh6WAi0LfM")

while True:
    time.sleep(10)
