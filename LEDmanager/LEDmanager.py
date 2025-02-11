from MyMQTT import MyMQTT
import json
import cherrypy
import time

class LightManager: 
    def __init__(self, clientID, broker, port):
        # Initialize MQTT client and internal data structures
        self.broker = broker
        self.port = port
        self.rooms = {}  # Store room configurations internally
        self.clientID = clientID
        self.client = MyMQTT(clientID, broker, port, self)  # Using MyMQTT

        # Define color mappings (in RGB format)
        self.colors = {
            "green": (0, 255, 0),
            "yellow": (255, 255, 0),
            "orange": (255, 165, 0),
            "red": (255, 0, 0),
            "dark purple": (75, 0, 130)
        }

        # Thresholds for different pollutants to determine air quality
        self.eaqi_thresholds = {
            "PM2.5": [10, 20, 25, 50],
            "PM10": [20, 40, 50, 100],
            "O3": [60, 120, 180, 240],
            "NO2": [40, 90, 120, 230],
            "SO2": [100, 200, 350, 500]
        }

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

                # Update pollutant values and determine LED color
                for entry in data['e']:
                    pollutant = entry['n']
                    if pollutant in room["latest_values"]:
                        room["latest_values"][pollutant] = entry['v']
                        room["current_color"] = self.determine_led_color(room["latest_values"])
                        self.publish(room_id, room["current_color"])
        except Exception as e:
            print(f"Error processing message: {e}")

    def add_room(self, room_id):
        # Initialize data for a new room
        self.rooms[room_id] = {
            "latest_values": {pollutant: 0 for pollutant in ["PM2.5", "PM10", "O3", "NO2", "SO2"]},
            "current_color": "green"
        }
        print(f"Added room {room_id}")

    def startSim(self):
        # Start the MQTT client and subscribe to topics
        self.client.start()
        self.client.mySubscribe("+/+/+/+/pollutants")  # Subscribe to all pollutant topics
        print("Subscribed to all pollutant topics using wildcard")

    def stopSim(self):
        # Stop the MQTT client and unsubscribe from topics
        self.client.unsubscribe()
        self.client.stop()
        print("Unsubscribed from all pollutant topics")

    def determine_led_color(self, latest_values):
        # Determine the worst pollutant score to set LED color
        worst_score = 0
        for pollutant, thresholds in self.eaqi_thresholds.items():
            value = latest_values.get(pollutant, 0)
            for index, threshold in enumerate(thresholds):
                if value > threshold:
                    worst_score = max(worst_score, index + 1)
        colors_list = list(self.colors.keys())
        return colors_list[worst_score]  # Return the corresponding color

    def publish(self, room_id, color):
        # Publish the RGB color to the corresponding LED topic
        rgb_value = self.colors[color]
        topic_publish = f"{room_id}/LED"  # Dynamic topic based on room ID
        message = {
            'bn': f"{self.clientID}/{room_id}/LED",
            'bt': time.time(),
            'e': [
                {'n': 'status', 'u': 'rgb', 'v': rgb_value}
            ]
        }
        self.client.myPublish(topic_publish, json.dumps(message))
        print(f"LED color set to {rgb_value} for room {room_id} at {topic_publish}")

if __name__ == "__main__":
    # Load MQTT broker configuration from JSON
    with open("broker.json", "r") as file:
        broker_config = json.load(file)

    broker = broker_config["ip"]
    port = broker_config["port"]

    # Create LightManager instance
    light_manager = LightManager("light_manager", broker, port)

    # Start the MQTT simulation with CherryPy
    cherrypy.engine.subscribe('start', light_manager.startSim)
    cherrypy.engine.subscribe('stop', light_manager.stopSim)

    cherrypy.quickstart(light_manager, "/", {"global": {"server.socket_host": "0.0.0.0", "server.socket_port": 8080}})
