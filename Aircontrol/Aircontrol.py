from MyMQTT import MyMQTT
import json
import time
import requests

class AirControlManager:
    def __init__(self, clientID, catalog_ip, catalog_port, weatherAdaptor_url):
        self.clientID = clientID
        self.catalog_ip = catalog_ip
        self.catalog_port = catalog_port
        self.weatherAdaptor_url = weatherAdaptor_url

        # Retrieve broker details dynamically from the catalog
        self._get_broker()

        self.rooms = {}
        # Note: Weather data is now fetched via HTTP when needed.
        self.client = MyMQTT(clientID, self.broker, self.port, self)

        self.eaqi_thresholds = {
            "PM2.5": [10, 20, 25, 50],
            "PM10":  [20, 40, 50, 100],
            "O3":    [60, 120, 180, 240],
            "NO2":   [40, 90, 120, 230],
            "SO2":   [100, 200, 350, 500]
        }

    def _get_broker(self):
        """Retrieve broker details from the catalog."""
        try:
            response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/broker")
            response.raise_for_status()
            broker_info = response.json()
            self.broker = broker_info["ip"]
            self.port = broker_info["port"]
            print(f"Broker retrieved: {self.broker}:{self.port}")
        except Exception as e:
            print(f"Error retrieving broker information: {e}")
            self.broker = "localhost"
            self.port = 1883

    def notify(self, topic, msg):
        print(f"Message received on topic {topic}: {msg}")
        try:
            data = json.loads(msg)
            parts = topic.split("/")

            if "pollutants" in topic:
                room_id = "/".join(parts[1:5]) if len(parts) >= 5 else None
                if room_id:
                    if room_id not in self.rooms:
                        self.add_room(room_id)
                    room = self.rooms[room_id]

                    for entry in data['e']:
                        pollutant = entry['n']
                        if pollutant in room["latest_values"]:
                            room["latest_values"][pollutant] = entry['v']

                    self.make_decision(room_id)
            # Weather data is now fetched via HTTP, so we do not handle it here.
        except Exception as e:
            print(f"Error processing message: {e}")

    def add_room(self, room_id):
        self.rooms[room_id] = {
            "latest_values": {pollutant: 0 for pollutant in self.eaqi_thresholds.keys()},
            "window_status": "closed",
            "ventilation_status": "off"
        }
        print(f"Added room {room_id}")

    def startSim(self):
        self.client.start()
        # Subscribe only to pollutant topics. Every topic starts with a leading slash.
        self.client.mySubscribe("/+/+/+/+/pollutants")
        print("Subscribed to pollutant topics")

    def stopSim(self):
        self.client.unsubscribe()
        self.client.stop()
        print("Unsubscribed from all topics")

    def get_weather_data(self):
        """Fetch weather data from the Weather Adaptor via HTTP."""
        try:
            response = requests.get(self.weatherAdaptor_url)
            response.raise_for_status()
            weather_data = response.json()
            return weather_data
        except Exception as e:
            print(f"Error fetching weather data: {e}")
            return {}

    def make_decision(self, room_id):
        room = self.rooms[room_id]
        # Fetch the latest weather data on demand
        weather_data = self.get_weather_data()

        overall_index = max([
            self.determine_eaqi_level(pollutant, value)
            for pollutant, value in room["latest_values"].items()
        ])

        # Extract weather parameters from the retrieved data
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
        topic_publish = f"/{room_id}/window"  # Ensure a leading slash
        message = {
            'bn': f"{self.clientID}/{room_id}/window",
            'bt': time.time(),
            'e': [{'n': 'status', 'v': action}]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        self.rooms[room_id]["window_status"] = action
        print(f"Window {action} for room {room_id}")

    def control_ventilation(self, room_id, action):
        topic_publish = f"/{room_id}/ventilation"  # Ensure a leading slash
        message = {
            'bn': f"{self.clientID}/{room_id}/ventilation",
            'bt': time.time(),
            'e': [{'n': 'status', 'v': action}]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        self.rooms[room_id]["ventilation_status"] = action
        print(f"Ventilation {action} for room {room_id}")

if __name__ == "__main__":
    # Read configuration from the JSON file (including catalog and weather adaptor info)
    with open("config-aircontrol.json", "r") as file:
        config = json.load(file)

    catalog_ip = config["catalog"]["ip"]
    catalog_port = config["catalog"]["port"]
    weatherAdaptor_url = config["weatherAdaptor"]["url"]

    air_control_manager = AirControlManager("air_control_manager", catalog_ip, catalog_port, weatherAdaptor_url)
    air_control_manager.startSim()
