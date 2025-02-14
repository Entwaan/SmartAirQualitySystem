import telepot
from telepot.loop import MessageLoop
import requests
import json
import time

# URLs for services
CATALOG_URL = "http://localhost:8080"
RASPBERRY_URL = "http://localhost:8082"
TIME_SERIES_URL = "http://localhost:8081"

# Required password
PASSWORD = "Antonio?"

class AirQualityBot:
    def __init__(self, token):
        self.bot = telepot.Bot(token)
        self.verified_users = {}
        self.pending_requests = {}
        self.start_bot()

    def start_bot(self):
        MessageLoop(self.bot, self.on_chat_message).run_as_thread()
        print("Bot is running...")

    def on_chat_message(self, msg):
        chat_id = str(msg['chat']['id'])
        text = msg.get('text', '').strip()
        user_name = msg['from'].get('first_name', 'User')

        # Step 1: Authentication
        if chat_id not in self.verified_users:
            if text == PASSWORD:
                self.verified_users[chat_id] = []  # ✅ Marquer l'utilisateur comme vérifié
                self.bot.sendMessage(chat_id, "✅ Correct password! Verifying your account...")
                self.verify_or_register_user(chat_id, user_name)
            else:
                self.bot.sendMessage(chat_id, "🔒 Enter the password to access the bot:")
            return

        # Step 2: Handle pending user requests
        if chat_id in self.pending_requests:
            request_type = self.pending_requests.pop(chat_id)
            
            if request_type == "register":
                self.register_user(chat_id, user_name, text)
                return

            elif request_type == "status_room":
                if text in self.verified_users[chat_id]:
                    self.fetch_room_status(chat_id, text)
                else:
                    self.bot.sendMessage(chat_id, "⚠️ Room not found. Please enter a valid room number.")
                    self.pending_requests[chat_id] = "status_room"  # Re-demander la saisie
                return

            elif request_type == "control_room":
                if text in self.verified_users[chat_id]:
                    self.pending_requests[chat_id] = ("control_action", text)
                    self.bot.sendMessage(chat_id, "🔧 Choose an action: `open_window`, `close_window`, `activate_ventilation`, `deactivate_ventilation`")
                else:
                    self.bot.sendMessage(chat_id, "⚠️ Room not found. Please enter a valid room number.")
                    self.pending_requests[chat_id] = "control_room"  # Re-demander la saisie
                return

            elif isinstance(request_type, tuple) and request_type[0] == "control_action":
                room = request_type[1]
                self.send_control_command(chat_id, room, text)
                return

        # Step 3: General Commands
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
                self.verified_users[chat_id] = user_info["rooms"]
                self.bot.sendMessage(chat_id, f"✅ You are registered! Rooms: {', '.join(user_info['rooms'])}\n\nℹ️ Choose an action:\n- 🔍 Check room status: /status\n- 🔧 Control actuators: /control")
            else:
                self.bot.sendMessage(chat_id, "📌 Enter the room numbers you want to register (e.g., '101 102'):")
                self.pending_requests[chat_id] = "register"
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error verifying catalog: {e}")

    def register_user(self, chat_id, user_name, room_ids):
        try:
            rooms = room_ids.split()
            payload = {"username": user_name, "telegramChatID": chat_id, "rooms": rooms}
            response = requests.post(f"{CATALOG_URL}/users", json=payload)

            if response.status_code == 200:
                self.verified_users[chat_id] = rooms  # ✅ Ajout des chambres à la mémoire
                self.bot.sendMessage(chat_id, f"✅ Registration successful! Registered rooms: {', '.join(rooms)}\n\nℹ️ Choose an action:\n- 🔍 Check room status: /status\n- 🔧 Control actuators: /control")
            else:
                self.bot.sendMessage(chat_id, f"❌ Registration error: {response.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Registration error: {e}")

    def request_room_status(self, chat_id):
        if chat_id not in self.verified_users:
            self.bot.sendMessage(chat_id, "⚠️ You must register first.")
            return

        self.bot.sendMessage(chat_id, f"📌 Your rooms: {', '.join(self.verified_users[chat_id])}. Enter a room number to check:")
        self.pending_requests[chat_id] = "status_room"

    def fetch_room_status(self, chat_id, room):
        try:
            response = requests.get(f"{TIME_SERIES_URL}/aqi", params={"room": room})
            if response.status_code == 200:
                status = response.json()
                self.bot.sendMessage(chat_id, f"📊 Room {room} - Air Quality: {status}")
            else:
                self.bot.sendMessage(chat_id, "⚠️ Room not found. Please enter a valid room number.")
                self.pending_requests[chat_id] = "status_room"  # Re-demander la saisie
        except Exception as e:
            self.bot.sendMessage(chat_id, f"⚠️ Error fetching status: {e}")

    def request_control_action(self, chat_id):
        if chat_id not in self.verified_users:
            self.bot.sendMessage(chat_id, "⚠️ You must register first.")
            return

        self.bot.sendMessage(chat_id, f"📌 Your rooms: {', '.join(self.verified_users[chat_id])}. Enter a room number to control:")
        self.pending_requests[chat_id] = "control_room"

    def send_control_command(self, chat_id, room, action):
        try:
            if action not in ["open_window", "close_window", "activate_ventilation", "deactivate_ventilation"]:
                self.bot.sendMessage(chat_id, "⚠️ Invalid action. Choose from: `open_window`, `close_window`, `activate_ventilation`, `deactivate_ventilation`.")
                return

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
