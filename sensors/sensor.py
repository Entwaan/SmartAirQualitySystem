import json
import requests
import time
import threading
import numpy as np
import cherrypy
from MyMQTT import *


class SensorSimulator:
    def __init__(self, mode='moderate'):
        self.mode = mode
        self.computed_aqi_json = None

    def simulate_pm25(self):
        if self.mode == 'good':
            return np.random.uniform(0, 12)
        elif self.mode == 'bad':
            return np.random.uniform(35.5, 55.4)
        else:
            return np.random.uniform(12.1, 35.4)
        
    def simulate_pm10(self):
        if self.mode == 'good':
            return np.random.uniform(0, 22)
        elif self.mode == 'bad':
            return np.random.uniform(55.5, 105.4)
        else:
            return np.random.uniform(25.1, 50.4)

    def simulate_o3(self):
        if self.mode == 'good':
            return np.random.uniform(0, 54)
        elif self.mode == 'bad':
            return np.random.uniform(125, 164)
        else:
            return np.random.uniform(55, 124)

    def simulate_no2(self):
        if self.mode == 'good':
            return np.random.uniform(0, 53)
        elif self.mode == 'bad':
            return np.random.uniform(101, 360)
        else:
            return np.random.uniform(54, 100)

    def simulate_so2(self):
        if self.mode == 'good':
            return np.random.uniform(0, 35)
        elif self.mode == 'bad':
            return np.random.uniform(186, 304)
        else:
            return np.random.uniform(36, 185)

class SensorsConnector:
    def __init__(self, config):
        self.config = config
        self.simulator = SensorSimulator()

        # Flag to stop the other threads
        self.thread_stop = threading.Event()
        
        self._get_broker()
        self.mqtt_client = MyMQTT(self.config['mqttInfos']['clientId'], self.brokerIp, self.brokerPort, self)
        self.mqtt_client.start()
        self.mqtt_client.mySubscribe(self.config['endpoints']['mqtt']['topics'][0])
        self._post_device()

    def notify(self, topic, msg):
        print(f"Received message on topic {topic}")
        self.simulator.computed_aqi_json = json.loads(json.loads(msg))


    def _get_broker(self):
        self.catalog_ip = self.config["catalog"]["ip"]
        self.catalog_port = self.config["catalog"]["port"]
        response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/broker")
        broker_info = response.json()
        self.brokerIp = broker_info["ip"]
        self.brokerPort = broker_info["port"]

    def _post_device(self):
        # Register device at the catalog
        body = {
            "ip": self.config["ip"],
            "port": self.config["port"],
            "endpoints": self.config["endpoints"],
            "availableResources": self.config["availableResources"],
            "roomID": self.config["roomID"],
        }
        response = requests.post(f"http://{self.catalog_ip}:{self.catalog_port}/devices", json=body)
        self.device_id = response.json()["deviceID"]
        

    def _put_device(self):
        # Update device at the catalog
        body = {
            "ip": self.config["ip"],
            "port": self.config["port"],
            "endpoints": self.config["endpoints"],
            "availableResources": self.config["availableResources"],
            "roomID": self.config["roomID"],
        }
        response = requests.put(f"http://{self.catalog_ip}:{self.catalog_port}/devices/{self.device_id}", json=body)

    def publish_sensor_data(self):
        while not self.thread_stop.is_set():
            sensor_data = {
                'bn': self.config['mqttInfos']['basename'] + "/pollutants",
                'bt': time.time(),
                'e': [
                    {'n': 'PM2.5', 'u': 'ug/m3', 'v': self.simulator.simulate_pm25()},
                    {'n': 'O3', 'u': 'ug/m3', 'v': self.simulator.simulate_o3()},
                    {'n': 'NO2', 'u': 'ug/m3', 'v': self.simulator.simulate_no2()},
                    {'n': 'SO2', 'u': 'ug/m3', 'v': self.simulator.simulate_so2()},
                    {'n': 'PM10', 'u': 'ug/m3', 'v': self.simulator.simulate_pm10()}
                ]
            }
            self.mqtt_client.myPublish(self.config['endpoints']['mqtt']['topics'][1], json.dumps(sensor_data))
            print("Published sensor data")
            self._put_device()
            time.sleep(60)

class AQIRestService:
    exposed = True
    def __init__(self, simulator):
        self.simulator = simulator

    def GET(self, *uri, **params):
        if len(uri) == 0 or uri[0] != "aqi":
            raise cherrypy.HTTPError(404, "Endpoint not found")
        return json.dumps(self.simulator.computed_aqi_json).encode('utf-8')
    
    def POST(self, *uri, **params):
        if uri and uri[0] == "mode":
            body = cherrypy.request.body.read()
            data = json.loads(body)
            mode = data.get("mode")
            
            if mode in ["good", "moderate", "bad"]:
                self.simulator.mode = mode
                return json.dumps({"status": "Mode updated"}).encode('utf-8')
            else:
                raise cherrypy.HTTPError(400, "Invalid mode")
        
        raise cherrypy.HTTPError(404, "Endpoint not found")

if __name__ == '__main__':
    config = json.load(open("config-sensor.json"))

    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }

    connector = SensorsConnector(config)
    service = AQIRestService(connector.simulator)

    # Start the thread to publish the sensor data
    t1 = threading.Thread(target=connector.publish_sensor_data)
    t1.start()

    # To stop the thread when CherryPy stops
    def shutdown():
        print("Stopping mqtt and CLI threads...")
        connector.thread_stop.set()
        connector.mqtt_client.stop()

    cherrypy.engine.subscribe('stop', shutdown)

    cherrypy.tree.mount(service, '/', conf)
    cherrypy.config.update({
        'server.socket_port': 8080,
        'server.socket_host': '0.0.0.0',
        "tools.response_headers.on": True,
        "tools.response_headers.headers": [("Content-Type", "application/json")]
    })
    cherrypy.engine.start()
    cherrypy.engine.block()