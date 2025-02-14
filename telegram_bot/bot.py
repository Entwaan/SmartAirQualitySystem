import telepot
from telepot.loop import MessageLoop
import requests
import json
import time

# URLs for Catalog Service, Raspberry Pi, and Time Series Adaptor
CATALOG_URL = "http://localhost:8080"
RASPBERRY_URL = "http://localhost:8082"
TIME_SERIES_URL = "http://localhost:8081"

# Required password for authentication
PASSWORD = "Antonio?"

class AirQualityBot:
    def __init__(self, token):
        self.bot = telepot.Bot(token)
        self.verified_users = set()
        self.start_bot()

    def start_bot(self):
        MessageLoop(self.bot, self.on_chat_message).run_as_thread()
        print("Bot is running...")

    def on_chat_message(self, msg):
        chat_id = str(msg['chat']['id'])
        text = msg.get('text', '').strip()
        user_name = msg['from'].get('first_name', 'User')

        if chat_id not in self.verified_users:
            if text == PASSWORD:
                self.verified_users.add(chat_id)
                self.bot.sendMessage(chat_id, "✅ Correct password! Verifying your account in the catalog...")
                self.verify_or_register_user(chat_id, user_name)
            else:
                self.bot.sendMessage(chat_id, "🔒 Enter the password to access the bot:")
            return

        if text == "/status":
            self.request_room_status(chat_id)
        elif text == "/control":
            self.request_control_action(chat_id)
        else:
            self.bot.sendMessage(chat_id, "⚠️ Unknown command. Use /status or /control.")

    def verify_or_register_user(self, chat_id, user_name):
        try:
            response = requests.get(f"{CATALOG_URL}/users/{chat_id}")
            if response.status_code == 200:
                user_info = response.json()
                self.bot.sendMessage(chat_id, f"✅ You are registered! Associated rooms: {', '.join(user_info['rooms'])}")
            else:
                self.request_room_registration(chat_id, user_name)
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error verifying catalog: {e}")

    def request_room_registration(self, chat_id, user_name):
        self.bot.sendMessage(chat_id, "📌 Enter your room numbers (e.g., '101 102') to register:")
        self.bot_listener = ("register", chat_id, user_name)

    def register_user(self, chat_id, user_name, room_ids):
        try:
            rooms = room_ids.split()
            payload = {"username": user_name, "telegramChatID": chat_id, "rooms": rooms}
            response = requests.post(f"{CATALOG_URL}/users", json=payload)
            if response.status_code == 200:
                self.bot.sendMessage(chat_id, f"✅ Registration successful! Registered rooms: {', '.join(rooms)}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Registration error: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Registration error: {e}")

    def request_room_status(self, chat_id):
        try:
            response = requests.get(f"{CATALOG_URL}/users/{chat_id}")
            if response.status_code == 200:
                user_info = response.json()
                self.bot.sendMessage(chat_id, f"📌 You can check the status of rooms: {', '.join(user_info['rooms'])}. Enter a room number:")
                self.bot_listener = ("status", chat_id)
            else:
                self.bot.sendMessage(chat_id, "⚠️ You must register first. Use /register.")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error fetching status: {e}")

    def fetch_room_status(self, chat_id, room):
        try:
            response = requests.get(f"{TIME_SERIES_URL}/aqi", params={"room": room})
            if response.status_code == 200:
                status = response.json()
                self.bot.sendMessage(chat_id, f"📊 Room {room} - Air Quality: {status}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Error fetching status: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error fetching status: {e}")

    def request_control_action(self, chat_id):
        try:
            response = requests.get(f"{CATALOG_URL}/users/{chat_id}")
            if response.status_code == 200:
                user_info = response.json()
                self.bot.sendMessage(chat_id, f"📌 You can control rooms: {', '.join(user_info['rooms'])}. Enter: '<room> <action>' (e.g., '101 open_window')")
                self.bot_listener = ("control", chat_id)
            else:
                self.bot.sendMessage(chat_id, "⚠️ You must register first. Use /register.")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error fetching control access: {e}")

    def send_control_command(self, chat_id, room_action):
        try:
            room, action = room_action.split()
            actuator = "windows" if "window" in action else "ventilation"
            state = "Open" if action == "open_window" else "Closed" if action == "close_window" else "On" if action == "activate_ventilation" else "Off"
            response = requests.put(f"{RASPBERRY_URL}/{actuator}", params={"state": state})
            if response.status_code == 200:
                self.bot.sendMessage(chat_id, f"✅ Action '{action}' executed in room {room}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Error executing action: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error executing action: {e}")

# Initialize the bot with your Telegram Bot Token
bot_instance = AirQualityBot("7847206958:AAGvH3qIjyyLmkfG4o0HjrDpNsh6WAi0LfM")

# Keep the bot running
while True:
    time.sleep(10)
