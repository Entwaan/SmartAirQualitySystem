import json
import requests
import cherrypy
import time
from MyMQTT import MyMQTT

class LightManager:
    def __init__(self, clientID, catalog_ip, catalog_port):
        self.clientID = clientID
        self.catalog_ip = catalog_ip
        self.catalog_port = catalog_port

        # Retrieve broker details dynamically from the catalog
        self._get_broker()
        
        # Initialize MQTT client with retrieved broker information
        self.client = MyMQTT(clientID, self.broker, self.port, self)

        self.rooms = {}  # Store room configurations internally

        # Define color mappings (in RGB format)
        # EAQI 1: green, 2: yellow, 3: orange, 4: red, 5: dark purple
        self.colors = {
            1: (0, 255, 0),
            2: (255, 255, 0),
            3: (255, 165, 0),
            4: (255, 0, 0),
            5: (75, 0, 130)
        }

        # Define pollutant thresholds for EAQI calculation.
        # Each pollutant has four thresholds that separate the 5 categories.
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
        except requests.RequestException as e:
            print(f"Error retrieving broker information: {e}")
            self.broker = "localhost"
            self.port = 1883  # Default fallback values

    def notify(self, topic, msg):
        # Handles incoming MQTT messages
        print(f"Message received on topic {topic}: {msg}")
        try:
            data = json.loads(msg)
            parts = topic.split("/")
            room_id = "/".join(parts[:4]) if len(parts) >= 4 else None  # Unique identifier for each room

            if room_id:
                if room_id not in self.rooms:
                    self.add_room(room_id)  # Dynamically add room if not present
                room = self.rooms[room_id]

                # Update pollutant values from the incoming message
                for entry in data['e']:
                    pollutant = entry['n']
                    if pollutant in room["latest_values"]:
                        room["latest_values"][pollutant] = entry['v']
                
                # Compute EAQI value and corresponding LED color
                color, eaqi_value = self.determine_led_color_and_eaqi(room["latest_values"])
                room["current_color"] = color

                # Publish both the LED color and EAQI value
                self.publish_led(room_id, color)
                self.publish_eaqi(room_id, eaqi_value)
        except Exception as e:
            print(f"Error processing message: {e}")

    def add_room(self, room_id):
        # Initialize data for a new room
        self.rooms[room_id] = {
            "latest_values": {pollutant: 0 for pollutant in self.eaqi_thresholds.keys()},
            "current_color": 1  # Default EAQI category 1 (green)
        }
        print(f"Added room {room_id}")

    def startSim(self):
        # Start the MQTT client and subscribe to topics
        self.client.start()
        self.client.mySubscribe("/+/+/+/+/pollutants")  # Subscribe to all pollutant topics
        print("Subscribed to all pollutant topics using wildcard")

    def stopSim(self):
        # Stop the MQTT client and unsubscribe from topics
        self.client.unsubscribe()
        self.client.stop()
        print("Unsubscribed from all pollutant topics")

    def determine_led_color_and_eaqi(self, latest_values):
        """
        Compute the EAQI for each pollutant based on its thresholds.
        The EAQI for a pollutant is defined as:
          - 1 if value <= first threshold
          - 2 if first threshold < value <= second threshold
          - 3 if second threshold < value <= third threshold
          - 4 if third threshold < value <= fourth threshold
          - 5 if value > fourth threshold
        The overall EAQI for the room is the maximum among all pollutant EAQI values.
        The corresponding LED color is then obtained from the color mapping.
        """
        worst_eaqi = 1
        for pollutant, thresholds in self.eaqi_thresholds.items():
            value = latest_values.get(pollutant, 0)
            if value <= thresholds[0]:
                pollutant_eaqi = 1
            elif value <= thresholds[1]:
                pollutant_eaqi = 2
            elif value <= thresholds[2]:
                pollutant_eaqi = 3
            elif value <= thresholds[3]:
                pollutant_eaqi = 4
            else:
                pollutant_eaqi = 5

            worst_eaqi = max(worst_eaqi, pollutant_eaqi)
        
        # Get the corresponding color for the worst EAQI value
        color = self.colors[worst_eaqi]
        return color, worst_eaqi

    def publish_led(self, room_id, color):
        """Publish the LED color message for a room."""
        topic_publish = f"/{room_id}/LED"  # Dynamic topic based on room ID
        message = {
            'bn': f"{self.clientID}/{room_id}/LED",
            'bt': time.time(),
            'e': [{'n': 'status', 'u': 'rgb', 'v': color}]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        print(f"LED color {color} published for room {room_id} at {topic_publish}")

    def publish_eaqi(self, room_id, eaqi_value):
        """Publish the EAQI value for a room on a separate topic."""
        topic_publish = f"/{room_id}/eaqi"  # EAQI topic per room
        message = {
            'bn': f"{self.clientID}/{room_id}/eaqi",
            'bt': time.time(),
            'e': [{'n': 'eaqi', 'u': 'score', 'v': eaqi_value}]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        print(f"EAQI value {eaqi_value} published for room {room_id} at {topic_publish}")

if __name__ == "__main__":
    # Load configuration from file (for catalog info)
    with open("config-lightmanager.json", "r") as file:
        config = json.load(file)

    catalog_ip = config["catalog"]["ip"]
    catalog_port = config["catalog"]["port"]

    # Create the LightManager instance with dynamic broker info from the catalog
    light_manager = LightManager("light_manager", catalog_ip, catalog_port)

    # Start the MQTT simulation with CherryPy
    cherrypy.engine.subscribe('start', light_manager.startSim)
    cherrypy.engine.subscribe('stop', light_manager.stopSim)

    cherrypy.quickstart(light_manager, "/", {
        "global": {
            "server.socket_host": "0.0.0.0",
            "server.socket_port": 8080
        }
    })
