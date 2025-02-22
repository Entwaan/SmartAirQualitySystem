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

        self.client = MyMQTT(clientID, self.broker, self.port, self)

        self.eaqi_thresholds = {
            "PM2.5": [10, 20, 25, 50],
            "PM10":  [20, 40, 50, 100],
            "O3":    [60, 120, 180, 240],
            "NO2":   [40, 90, 120, 230],
            "SO2":   [100, 200, 350, 500]
        }

    def _get_broker(self):
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
        try:
            data = json.loads(json.loads(msg))
            print(f"Message received on topic {topic}: {data}", flush=True)
            parts = topic.split("/")

            if "pollutants" in topic:
                room_id = "/".join(parts[1:4]) if len(parts) >= 5 else None
                if room_id:
                    if room_id not in self.rooms:
                        self.add_room(room_id)
                    room = self.rooms[room_id]

                    for entry in data['e']:
                        pollutant = entry['n']
                        if pollutant in room["latest_values"]:
                            room["latest_values"][pollutant] = entry['v']

                    self.make_decision(room_id)
        except Exception as e:
            print(f"Error processing message: {e}")

    def add_room(self, room_id):
        self.rooms[room_id] = {
            "latest_values": {pollutant: 0 for pollutant in self.eaqi_thresholds.keys()},
            "window_status": "Closed",
            "ventilation_status": "Off",
            "windows_actuator_ip": None,
            "ventilation_actuator_ip": None
        }
      
        response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/rooms")
        rooms = response.json()
        building, floor, room_number = room_id.split("/")
        for room in rooms:
            if room["buildingName"] == building and str(room["floor"]) == floor and str(room["number"]) == room_number:
                # iterate through the endpoints of the room to find the actuators ips
                for deviceId in room["devices"]:
                    response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/devices/{deviceId}")
                    device = response.json()
                    # check if the device has the available resources and set the actuators ips
                    if "windows" in device["availableResources"]:
                        self.rooms[room_id]["windows_actuator_ip"] = device["endpoints"]["rest"]["restIP"]
                    if "ventilation" in device["availableResources"]:
                        self.rooms[room_id]["ventilation_actuator_ip"] = device["endpoints"]["rest"]["restIP"]

        print(f"Added room {room_id} : {self.rooms[room_id]}", flush=True)

    def startSim(self):
        self.client.start()
        self.client.mySubscribe("/+/+/+/pollutants")
        print("Subscribed to pollutant topics")

    def stopSim(self):
        self.client.unsubscribe()
        self.client.stop()
        print("Unsubscribed from all topics")

    def get_weather_data(self):
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
        weather_data = self.get_weather_data()

        overall_index = max([
            self.determine_eaqi_level(pollutant, value)
            for pollutant, value in room["latest_values"].items()
        ])
        wind_speed = weather_data["current"].get("wind_speed_10m", 0)
        precipitation = weather_data["current"].get("precipitation", 0)
        temperature = weather_data["current"].get("temperature_2m", 0)
        wind_direction = weather_data["current"].get("wind_direction_10m", 0)

        # Decision Logic
        if overall_index > 3:
            self.control_window(room_id, "Closed")
            self.control_ventilation(room_id, "On")
        elif precipitation > 0 or temperature > 30:
            self.control_window(room_id, "Closed")
            if wind_speed > 15:
                self.control_ventilation(room_id, "Boost") 
            else:
                self.control_ventilation(room_id, "On")
        elif wind_speed > 10 and overall_index <= 3:
            if 90 <= wind_direction <= 270:  
                self.control_window(room_id, "Open")
                self.control_ventilation(room_id, "Off")
            else:
                self.control_window(room_id, "Closed")
                self.control_ventilation(room_id, "On")
        else:
            if overall_index <= 2:
                self.control_window(room_id, "Slightly_Open") 
            else:
                self.control_window(room_id, "Closed")
            self.control_ventilation(room_id, "On")

    def determine_eaqi_level(self, pollutant, value):
        thresholds = self.eaqi_thresholds.get(pollutant, [])
        for index, threshold in enumerate(thresholds):
            if value <= threshold:
                return index + 1
        return 5 

    def control_window(self, room_id, action):
        response = requests.put(f"{self.rooms[room_id]['windows_actuator_ip']}/windows", params={"state": action})
        if response.status_code == 200:
            print(f"Window {action} for room {room_id}", flush=True)
            self.rooms[room_id]["window_status"] = action
        else:
            print(f"Windows state unchanged: the windows are already in state {action} or the room is closed", flush=True)

    def control_ventilation(self, room_id, action):
        response = requests.put(f"{self.rooms[room_id]['ventilation_actuator_ip']}/ventilation", params={"state": action})
        if response.status_code == 200:
            print(f"Ventilation {action} for room {room_id}", flush=True)
            self.rooms[room_id]["ventilation_status"] = action
        else:
            print(f"Ventilation state unchanged: the ventilation is already in state {action}", flush=True)

if __name__ == "__main__":
    with open("config-aircontrol.json", "r") as file:
        config = json.load(file)

    catalog_ip = config["catalog"]["ip"]
    catalog_port = config["catalog"]["port"]
    weatherAdaptor_url = config["weatherAdaptor"]["url"]
    clientId = config["mqttInfos"]["clientId"]

    air_control_manager = AirControlManager(clientId, catalog_ip, catalog_port, weatherAdaptor_url)
    air_control_manager.startSim()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        air_control_manager.stopSim()
        print("Stopping")
