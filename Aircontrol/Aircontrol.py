from MyMQTT import MyMQTT
import json
import time

class AirControlManager:
    def __init__(self, clientID, broker, port):
        self.broker = broker
        self.port = port
        self.clientID = clientID
        self.rooms = {}
        self.weather_data = {}  # Store weather data per building
        self.client = MyMQTT(clientID, broker, port, self)

        self.eaqi_thresholds = {
            "PM2.5": [10, 20, 25, 50],
            "PM10": [20, 40, 50, 100],
            "O3": [60, 120, 180, 240],
            "NO2": [40, 90, 120, 230],
            "SO2": [100, 200, 350, 500]
        }

    def notify(self, topic, msg):
        print(f"Message received on topic {topic}: {msg}")
        try:
            data = json.loads(msg)
            parts = topic.split("/")

            if "pollutants" in topic:
                room_id = "/".join(parts[:4]) if len(parts) >= 4 else None
                if room_id:
                    if room_id not in self.rooms:
                        self.add_room(room_id)
                    room = self.rooms[room_id]

                    for entry in data['e']:
                        pollutant = entry['n']
                        if pollutant in room["latest_values"]:
                            room["latest_values"][pollutant] = entry['v']

                    self.make_decision(room_id)

            elif "weather" in topic:
                building_id = "/".join(parts[:3]) if len(parts) >= 3 else None
                if building_id:
                    self.weather_data[building_id] = data["current_weather"]
                    print(f"Weather data updated for {building_id}")

        except Exception as e:
            print(f"Error processing message: {e}")

    def add_room(self, room_id):
        self.rooms[room_id] = {
            "latest_values": {pollutant: 0 for pollutant in ["PM2.5", "PM10", "O3", "NO2", "SO2"]},
            "window_status": "closed",
            "ventilation_status": "off"
        }
        print(f"Added room {room_id}")

    def startSim(self):
        self.client.start()
        self.client.mySubscribe("+/+/+/+/pollutants")  # Subscribe to pollutant topics
        self.client.mySubscribe("+/+/weather")        # Subscribe to weather data topics
        print("Subscribed to pollutant and weather topics")

    def stopSim(self):
        self.client.unsubscribe()
        self.client.stop()
        print("Unsubscribed from all topics")

    def make_decision(self, room_id):
        room = self.rooms[room_id]
        building_id = "/".join(room_id.split("/")[:3])
        weather_data = self.weather_data.get(building_id, {})

        overall_index = max([
            self.determine_eaqi_level(pollutant, value)
            for pollutant, value in room["latest_values"].items()
        ])

        wind_speed = weather_data.get("wind_speed_10m", 0)
        precipitation = weather_data.get("precipitation", 0)
        temperature = weather_data.get("temperature_2m", 0)
        wind_direction = weather_data.get("wind_direction_10m", 0)

        # Advanced Decision Logic
        if overall_index > 3:
            self.control_window(room_id, "close")
            self.control_ventilation(room_id, "on")
        elif precipitation > 0 or temperature > 30:
            self.control_window(room_id, "close")
            if wind_speed > 15:
                self.control_ventilation(room_id, "boost")  # Boost mode for high wind
            else:
                self.control_ventilation(room_id, "on")
        elif wind_speed > 10 and overall_index <= 3:
            if 90 <= wind_direction <= 270:  # Favorable wind direction
                self.control_window(room_id, "open")
                self.control_ventilation(room_id, "off")
            else:
                self.control_window(room_id, "close")
                self.control_ventilation(room_id, "on")
        else:
            if overall_index <= 2:
                self.control_window(room_id, "slightly_open")  # Partial opening for moderate AQI
            else:
                self.control_window(room_id, "close")
            self.control_ventilation(room_id, "on")

    def determine_eaqi_level(self, pollutant, value):
        thresholds = self.eaqi_thresholds.get(pollutant, [])
        for index, threshold in enumerate(thresholds):
            if value <= threshold:
                return index + 1
        return 5  # Very Poor Air Quality

    def control_window(self, room_id, action):
        topic_publish = f"{room_id}/window"
        message = {
            'bn': f"{self.clientID}/{room_id}/window",
            'bt': time.time(),
            'e': [
                {'n': 'status', 'v': action}
            ]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        self.rooms[room_id]["window_status"] = action
        print(f"Window {action} for room {room_id}")

    def control_ventilation(self, room_id, action):
        topic_publish = f"{room_id}/ventilation"
        message = {
            'bn': f"{self.clientID}/{room_id}/ventilation",
            'bt': time.time(),
            'e': [
                {'n': 'status', 'v': action}
            ]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        self.rooms[room_id]["ventilation_status"] = action
        print(f"Ventilation {action} for room {room_id}")

if __name__ == "__main__":
    with open("broker.json", "r") as file:
        broker_config = json.load(file)

    broker = broker_config["ip"]
    port = broker_config["port"]

    air_control_manager = AirControlManager("air_control_manager", broker, port)

    air_control_manager.startSim()
