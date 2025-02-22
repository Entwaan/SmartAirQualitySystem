import os
import time
import json
import requests
import telepot
from telepot.loop import MessageLoop
import matplotlib.pyplot as plt
from io import BytesIO
import datetime

################################################################################
# Load configuration from bot_config.json 

with open("bot_config.json", "r") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN")
CATALOG_URL = config.get("CATALOG_URL")
BOT_PASSWORD = config.get("BOT_PASSWORD")
TIME_SERIES_DB_URL = config.get("TIME_SERIES_DB_URL")
ACTUATORS_URL = config.get("ACTUATORS_URL")

################################################################################
# Helpers 

def compose_room_label(building, floor, number):
    """ 'A', 1, 1 => 'A101' """
    floor_str = str(floor)
    number_str = f"{number:02d}"
    return f"{building}{floor_str}{number_str}"

def parse_room_label(label):
  
    if len(label) < 4:
        raise ValueError("Room label must be >= 4 chars, e.g. 'A101'.")
    building = label[0]           # 'A'
    floor_part = label[1]         # '1'
    number_part = label[2:]       # '01'
    floor = int(floor_part)
    number = int(number_part)
    return building, floor, number

def parse_opening_hours(hour_string):

    if '-' not in hour_string:
        raise ValueError("Hours must be 'HH:MM-HH:MM'.")
    start_str, end_str = hour_string.split('-', 1)

    def to_hour(hhmm):
        return int(hhmm.strip().split(':')[0])  # just parse hour
    start_h = to_hour(start_str)
    end_h = to_hour(end_str)
    return start_h, end_h


def plot_aqi_data(aqi_data):
  
    timestamps = []
    values = []

    for row in aqi_data:
        if "timestamp" in row and "value" in row:
            ts_str = row["timestamp"] 
            try:
                dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                timestamps.append(dt)
                values.append(row["value"])
            except ValueError as e:
                print(f"[WARN] Could not parse timestamp '{ts_str}': {e}")

    if not timestamps or not values:
        return None  # => "❌ Could not generate AQI plot."

    # Now do the same plotting as before
    plt.figure(figsize=(10,4))
    plt.plot(timestamps, values, marker='o', linestyle='-')
    plt.xlabel("Time")
    plt.ylabel("AQI")
    plt.title("AQI over the last 24 hours")
    plt.grid(True)
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf

################################################################################
# Main Bot Class


class AirQualityBot:
    def __init__(self, telegram_token):
        self.bot = telepot.Bot(telegram_token)
        self.user_data = {}
        self.room_map = {}         # "A101" -> room-uuid
        self.inverse_room_map = {} # room-uuid -> "A101"

        # Start receiving messages
        MessageLoop(self.bot, self.on_chat_message).run_as_thread()
        print("🤖 Bot is running...")

        # Populate room map from Catalog
        self.update_room_map()

    def update_room_map(self):
        self.room_map.clear()
        self.inverse_room_map.clear()
        try:
            resp = requests.get(f"{CATALOG_URL}/rooms", timeout=5)
            if resp.status_code == 200:
                rooms_list = resp.json()
                for r in rooms_list:
                    building = r["buildingName"]
                    floor = r["floor"]
                    number = r["number"]
                    room_id = r["roomID"]
                    label = compose_room_label(building, floor, number)
                    self.room_map[label] = room_id
                    self.inverse_room_map[room_id] = label
            else:
                print(f"[WARN] Could not retrieve rooms => {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[ERROR] update_room_map => {e}")

    def on_chat_message(self, msg):
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "").strip()

        # Initialize user data if needed
        if chat_id not in self.user_data:
            self.user_data[chat_id] = {
                "verified": False,
                "rooms": [],
                "user_id": None,
                "pending_action": None
            }

        # 1) Password check
        if not self.user_data[chat_id]["verified"]:
            self.handle_password(chat_id, text)
            return

        # 2) Check if there's a pending action
        if self.user_data[chat_id]["pending_action"]:
            action = self.user_data[chat_id]["pending_action"]
            self.user_data[chat_id]["pending_action"] = None
            self.handle_pending_action(chat_id, text, action)
            return

        # 3) Interpret commands
        if text == "/status":
            self.start_status_flow(chat_id)
        elif text == "/control":
            self.start_control_flow(chat_id)
        elif text == "/add_room":
            self.start_add_room_flow(chat_id)
        elif text == "/update_list":
            self.start_update_list_flow(chat_id)
        else:
            self.show_main_menu(chat_id)

    def handle_password(self, chat_id, text):
        if text == BOT_PASSWORD:
            self.user_data[chat_id]["verified"] = True
            self.bot.sendMessage(chat_id, "✅ Correct password! Checking your account in the Catalog...")
            self.verify_or_register_user(chat_id)
        else:
            self.bot.sendMessage(chat_id, "🔐 Please enter the bot password to continue:")

    def verify_or_register_user(self, chat_id):
        try:
            resp = requests.get(f"{CATALOG_URL}/users/{chat_id}", timeout=5)
            if resp.status_code == 200:
                user_info = resp.json()
                self.user_data[chat_id]["user_id"] = user_info["userID"]
                self.user_data[chat_id]["rooms"] = user_info["rooms"]

                label_list = [self.inverse_room_map.get(rid, rid) for rid in user_info["rooms"]]
                rooms_str = ", ".join(label_list) if label_list else "None"
                self.bot.sendMessage(
                    chat_id,
                    f"👤 You are already registered.\nYour subscribed rooms: {rooms_str}\n\n"
                    "Use /status, /control, /add_room, or /update_list."
                )
            else:
                self.bot.sendMessage(
                    chat_id,
                    "📋 No entry found in the Catalog. Please type the rooms you want to subscribe to (e.g., 'A101 B205'):"
                )
                self.user_data[chat_id]["pending_action"] = "register_user"
        except Exception as e:
            self.bot.sendMessage(chat_id, f"❌ Error checking user: {e}")

    def handle_pending_action(self, chat_id, text, action):
        if action == "register_user":
            self.register_user(chat_id, text)
        elif action == "status_room":
            self.handle_status_room(chat_id, text)
        elif action == "control_room":
            self.handle_control_room_choice(chat_id, text)
        elif isinstance(action, dict) and action.get("name") == "control_action":
            self.handle_control_action(chat_id, text, action["roomID"])
        elif action == "add_room_step":
            self.handle_add_room(chat_id, text)
        elif action == "update_list_step":
            self.handle_update_list(chat_id, text)
        else:
            self.show_main_menu(chat_id)

    # -----------------------------------------------------------------
    # Registration Flow

    def register_user(self, chat_id, rooms_text):
        labels = rooms_text.split()
        if not labels:
            self.bot.sendMessage(chat_id, "🚫 Empty list. Try again (e.g., 'A101 B205').")
            self.user_data[chat_id]["pending_action"] = "register_user"
            return

        room_ids = []
        missing = []
        for lab in labels:
            if lab in self.room_map:
                room_ids.append(self.room_map[lab])
            else:
                missing.append(lab)

        if missing:
            missing_str = ", ".join(missing)
            self.bot.sendMessage(chat_id, f"🚫 The following rooms do not exist: {missing_str}. Try again.")
            self.user_data[chat_id]["pending_action"] = "register_user"
            return

        payload = {
            "userID": chat_id,
            "username": f"Telegram_{chat_id}",
            "telegramChatID": chat_id,
            "rooms": room_ids
        }
        try:
            r = requests.post(f"{CATALOG_URL}/users", json=payload, timeout=5)
            if r.status_code in [200, 201]:
                user_info = r.json()
                self.user_data[chat_id]["user_id"] = user_info.get("userID", chat_id)
                self.user_data[chat_id]["rooms"] = room_ids
                labels_str = ", ".join([self.inverse_room_map.get(rid, rid) for rid in room_ids])
                self.bot.sendMessage(
                    chat_id,
                    f"✅ Registration successful!\nYou are subscribed to rooms: {labels_str}\n\n"
                    "Use /status, /control, /add_room, or /update_list."
                )
            else:
                self.bot.sendMessage(chat_id, f"❌ Error during registration: {r.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"❌ Registration error: {e}")

    # -----------------------------------------------------------------
    # /STATUS

    def start_status_flow(self, chat_id):
        user_rooms = self.user_data[chat_id]["rooms"]
        if not user_rooms:
            self.bot.sendMessage(chat_id, "🚫 You have no rooms. Use /update_list or /add_room.")
            return
        labels = [self.inverse_room_map.get(rid, rid) for rid in user_rooms]
        self.bot.sendMessage(chat_id, f"📊 Type one of your rooms to check the status: {', '.join(labels)}")
        self.user_data[chat_id]["pending_action"] = "status_room"

    def handle_status_room(self, chat_id, label):
        if label not in self.room_map:
            self.bot.sendMessage(chat_id, f"🚫 Room '{label}' not found in the Catalog.")
            self.user_data[chat_id]["pending_action"] = "status_room"
            return

        room_id = self.room_map[label]
        if room_id not in self.user_data[chat_id]["rooms"]:
            self.bot.sendMessage(chat_id, f"🚫 You are not subscribed to '{label}'.")
            self.user_data[chat_id]["pending_action"] = "status_room"
            return

        # 1) Attempt direct device data from Catalog (optional)
        try:
            r = requests.get(f"{CATALOG_URL}/rooms/{room_id}", timeout=5)
            if r.status_code != 200:
                self.bot.sendMessage(chat_id, f"❌ Error retrieving room data: {r.text}")
            else:
                room_data = r.json()
                device_ids = room_data.get("devices", [])
                if device_ids:
                    sensor_reports = []
                    for d_id in device_ids:
                        dresp = requests.get(f"{CATALOG_URL}/devices/{d_id}", timeout=5)
                        if dresp.status_code == 200:
                            dev_info = dresp.json()
                            resources = dev_info.get("availableResources", [])
                            # Skip actuators
                            if any(res.lower() in ["window", "ventilation"] for res in resources):
                                continue
                            rest_ip = dev_info["endpoints"]["rest"]["restIP"]
                            try:
                                aqi_resp = requests.get(f"{rest_ip}/aqi", timeout=5)
                                if aqi_resp.status_code == 200:
                                    data = aqi_resp.json()
                                    sensor_reports.append(f"Device {d_id} => {json.dumps(data)}")
                                else:
                                    sensor_reports.append(f"Device {d_id} => /aqi error {aqi_resp.status_code}")
                            except Exception as se:
                                sensor_reports.append(f"Device {d_id} => REST error: {se}")
                        else:
                            sensor_reports.append(f"Device {d_id} not found in the Catalog")
                    direct_data = "\n".join(sensor_reports) if sensor_reports else "No direct sensor data found."
                else:
                    direct_data = "No devices found in room."
                self.bot.sendMessage(chat_id, f"📊 Direct device data for room {label}:\n{direct_data}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"❌ Error reading direct device status: {e}")

        # 2) Time Series DB data
      
        building, floor, number = parse_room_label(label)

        latest_aqi = self._fetch_latest_from_tsdb("aqi", building, floor, number)
        latest_windows = self._fetch_latest_from_tsdb("windows", building, floor, number)
        latest_ventilation = self._fetch_latest_from_tsdb("ventilation", building, floor, number)
        aqi_24h = self._fetch_range_from_tsdb("aqi", building, floor, number, "1d")

        # Build the textual report
        concentration_info = f"Current AQI: {latest_aqi}" if latest_aqi is not None else "No recent AQI data"
        windows_info = f"Windows state: {latest_windows}" if latest_windows is not None else "No recent windows data"
        ventilation_info = f"Ventilation state: {latest_ventilation}" if latest_ventilation is not None else "No recent ventilation data"

        if aqi_24h:
            range_info = f"24h data: {len(aqi_24h)} records"
        else:
            range_info = "No 24h AQI data"

        ts_message = (
            f"--- Time Series DB Status for room {label} ---\n"
            f"{concentration_info}\n"
            f"{windows_info}\n"
            f"{ventilation_info}\n"
            f"{range_info}"
        )
        self.bot.sendMessage(chat_id, ts_message)

        # Attempt to plot the 24h AQI data
        if aqi_24h:
            buf = plot_aqi_data(aqi_24h)
            if buf:
                self.bot.sendPhoto(chat_id, photo=buf, caption="AQI trend over the last 24h 📈")
            else:
                self.bot.sendMessage(chat_id, "❌ Could not generate AQI plot.")

    def _fetch_latest_from_tsdb(self, measure_type, building, floor, number):

        try:
            url = f"{TIME_SERIES_DB_URL}/{measure_type}?building={building}&floor={floor}&room={number}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    last_row = data[-1]
                    return last_row.get("value")
                else:
                    return None
            else:
                print(f"[WARN] Could not fetch latest {measure_type}, status={resp.status_code}")
                return None
        except Exception as e:
            print(f"[ERROR] _fetch_latest_from_tsdb({measure_type}, {building},{floor},{number}) => {e}")
            return None

    def _fetch_range_from_tsdb(self, measure_type, building, floor, number, range_str):
    
        try:
            url = (
                f"{TIME_SERIES_DB_URL}/{measure_type}"
                f"?building={building}&floor={floor}&room={number}&range={range_str}"
            )
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[WARN] Could not fetch {measure_type} range, status={resp.status_code}")
                return []
        except Exception as e:
            print(f"[ERROR] _fetch_range_from_tsdb({measure_type}, {building},{floor},{number},{range_str}) => {e}")
            return []

    # -----------------------------------------------------------------
    # /CONTROL

    def start_control_flow(self, chat_id):
        user_rooms = self.user_data[chat_id]["rooms"]
        if not user_rooms:
            self.bot.sendMessage(chat_id, "🚫 You have no rooms. Use /update_list or /add_room.")
            return
        labels = [self.inverse_room_map.get(rid, rid) for rid in user_rooms]
        self.bot.sendMessage(chat_id, f"🎮 Type one of your rooms or ALL: {', '.join(labels)}")
        self.user_data[chat_id]["pending_action"] = "control_room"

    def handle_control_room_choice(self, chat_id, user_input):
        if user_input.upper() == "ALL":
            self.bot.sendMessage(chat_id, "🎮 Choose an action: open_window, close_window, activate_ventilation, stop_ventilation")
            self.user_data[chat_id]["pending_action"] = {"name": "control_action", "roomID": "ALL"}
            return

        if user_input not in self.room_map:
            self.bot.sendMessage(chat_id, f"🚫 Room '{user_input}' not found. Try again.")
            self.user_data[chat_id]["pending_action"] = "control_room"
            return

        room_id = self.room_map[user_input]
        if room_id not in self.user_data[chat_id]["rooms"]:
            self.bot.sendMessage(chat_id, f"🚫 You are not subscribed to '{user_input}'.")
            self.user_data[chat_id]["pending_action"] = "control_room"
            return

        self.bot.sendMessage(chat_id, "🎮 Choose an action: open_window, close_window, activate_ventilation, stop_ventilation")
        self.user_data[chat_id]["pending_action"] = {"name": "control_action", "roomID": room_id}

    def handle_control_action(self, chat_id, action, room_id):
        valid_actions = ["open_window", "close_window", "activate_ventilation", "stop_ventilation"]
        if action not in valid_actions:
            self.bot.sendMessage(chat_id, f"🚫 Invalid action. Valid actions: {', '.join(valid_actions)}.")
            return

        if room_id == "ALL":
            for rid in self.user_data[chat_id]["rooms"]:
                self.perform_actuator_call(rid, action)
            self.bot.sendMessage(chat_id, f"🎮 Action '{action}' applied to ALL your rooms.")
        else:
            self.perform_actuator_call(room_id, action)
            label = self.inverse_room_map.get(room_id, room_id)
            self.bot.sendMessage(chat_id, f"🎮 Action '{action}' executed in room {label}.")

    def perform_actuator_call(self, room_id, action):
        if action == "open_window":
            endpoint = "/windows?state=Open"
        elif action == "close_window":
            endpoint = "/windows?state=Closed"
        elif action == "activate_ventilation":
            endpoint = "/ventilation?state=On"
        else:  # stop_ventilation
            endpoint = "/ventilation?state=Off"

        if ACTUATORS_URL:
            url = ACTUATORS_URL + endpoint
            try:
                r = requests.put(url, timeout=5)
                if r.status_code not in [200, 201]:
                    print(f"[WARN] Actuator call returned {r.status_code} => {r.text}")
            except Exception as e:
                print(f"[ERROR] Actuator call failed => {e}")

    # -----------------------------------------------------------------
    # /ADD_ROOM

    def start_add_room_flow(self, chat_id):
        self.bot.sendMessage(chat_id, "🏠 Enter a new room in format 'A101 08:00-18:00':")
        self.user_data[chat_id]["pending_action"] = "add_room_step"

    def handle_add_room(self, chat_id, text):
        parts = text.split()
        if len(parts) != 2:
            self.bot.sendMessage(chat_id, "🚫 Invalid format. Example: 'A101 08:00-18:00'.")
            self.user_data[chat_id]["pending_action"] = "add_room_step"
            return

        room_label, hours_str = parts
        try:
            building, floor, number = parse_room_label(room_label)
        except Exception as e:
            self.bot.sendMessage(chat_id, f"🚫 Error parsing '{room_label}': {e}")
            self.user_data[chat_id]["pending_action"] = "add_room_step"
            return

        try:
            start_h, end_h = parse_opening_hours(hours_str)
        except Exception as e:
            self.bot.sendMessage(chat_id, f"🚫 Error parsing hours '{hours_str}': {e}")
            self.user_data[chat_id]["pending_action"] = "add_room_step"
            return

        payload = {
            "buildingName": building,
            "floor": floor,
            "number": number,
            "openingHours": {
                "start": start_h,
                "end": end_h
            },
            "coordinates": {
                "lat": 45.07,
                "lon": 7.67
            }
        }
        try:
            r = requests.post(f"{CATALOG_URL}/rooms", json=payload, timeout=5)
            if r.status_code in [200, 201]:
                self.update_room_map()
                self.bot.sendMessage(chat_id, f"🏠 Room {room_label} created ({start_h}:00 to {end_h}:00).")
            else:
                self.bot.sendMessage(chat_id, f"❌ Error creating room: {r.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"❌ Exception creating room: {e}")

    # -----------------------------------------------------------------
    # /UPDATE_LIST

    def start_update_list_flow(self, chat_id):
        self.bot.sendMessage(chat_id, "📋 Type the new list of rooms (e.g., 'A101 B305'):")
        self.user_data[chat_id]["pending_action"] = "update_list_step"

    def handle_update_list(self, chat_id, rooms_text):
        labels = rooms_text.split()
        if not labels:
            self.bot.sendMessage(chat_id, "🚫 No rooms specified. Try again.")
            self.user_data[chat_id]["pending_action"] = "update_list_step"
            return

        room_ids = []
        missing = []
        for lab in labels:
            if lab in self.room_map:
                room_ids.append(self.room_map[lab])
            else:
                missing.append(lab)
        if missing:
            missing_str = ", ".join(missing)
            self.bot.sendMessage(chat_id, f"🚫 Unknown rooms: {missing_str}. Try again.")
            self.user_data[chat_id]["pending_action"] = "update_list_step"
            return

        user_id = self.user_data[chat_id]["user_id"]
        payload = {
            "userID": user_id,
            "username": f"Telegram_{chat_id}",
            "telegramChatID": chat_id,
            "rooms": room_ids
        }
        try:
            r = requests.put(f"{CATALOG_URL}/users/{user_id}", json=payload, timeout=5)
            if r.status_code == 200:
                self.user_data[chat_id]["rooms"] = room_ids
                self.update_room_map()
                updated_labels = [self.inverse_room_map.get(rid, rid) for rid in room_ids]
                self.bot.sendMessage(chat_id, f"✅ Your rooms are updated: {', '.join(updated_labels)}")
            else:
                self.bot.sendMessage(chat_id, f"❌ Error updating rooms: {r.text}")
        except Exception as e:
            self.bot.sendMessage(chat_id, f"❌ Exception updating rooms: {e}")

    # -----------------------------------------------------------------
    # Show Menu

    def show_main_menu(self, chat_id):
        self.bot.sendMessage(
            chat_id,
            "📋 Available commands:\n"
            "/status - Show sensor status\n"
            "/control - Control windows or ventilation\n"
            "/add_room - Add a new room\n"
            "/update_list - Update your subscribed rooms"
        )

################################################################################
# Launch


if __name__ == "__main__":
    bot_instance = AirQualityBot(TELEGRAM_TOKEN)
    while True:
        time.sleep(10)
