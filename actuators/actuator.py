import json
import requests
import time
import threading
import cherrypy
from MyMQTT import *


class ActuatorsConnector:
    def __init__(self, config):
        self.config = config
        self.windows_state = "Closed"
        self.ventilation_state = "Off"

        # Flag to stop the other threads
        self.thread_stop = threading.Event()
        
        self._get_broker()
        self._get_opening_hours()
        self.mqtt_client = MyMQTT(self.config['mqttInfos']['clientId'], self.brokerIp, self.brokerPort, self)
        self.mqtt_client.start()
        self._post_device()


    def _get_broker(self):
        self.catalog_ip = self.config["catalog"]["ip"]
        self.catalog_port = self.config["catalog"]["port"]
        response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/broker")
        broker_info = response.json()
        self.brokerIp = broker_info["ip"]
        self.brokerPort = broker_info["port"]

    def _get_opening_hours(self):
        response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/rooms/{self.config['roomID']}")
        room_infos = response.json()
        self.starting_hour = room_infos["openingHours"]["start"]
        self.ending_hour = room_infos["openingHours"]["end"]

    def isRoomClosed(self):
        current_hour = time.localtime().tm_hour
        if(current_hour < self.starting_hour or current_hour >= self.ending_hour):
            return True
        return False

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

    def periodically_register_device_and_close_windows(self):
        while not self.thread_stop.is_set():
            self._put_device()
            # Close the windows if the room is closed
            if(self.isRoomClosed() and self.windows_state == "Open"):
                self.windows_state = "Closed"
                self.publish_actuator_data("windows")
            time.sleep(60)

    def publish_actuator_data(self, actuator):
        msg = {
            'bn': self.config['mqttInfos']['basename'],
            'bt': time.time(),
            'e': [
                {
                    'n': "",
                    'u': "state",
                    'v': None
                }
            ]
        }
        if(actuator == "windows"):
            msg['e'][0]['n'] = "windows"
            msg['e'][0]['v'] = self.windows_state
        if(actuator == "ventilation"):
            msg['e'][0]['n'] = "ventilation"
            msg['e'][0]['v'] = self.ventilation_state
        self.mqtt_client.myPublish(self.config['mqttInfos']['basename']+"/"+actuator, json.dumps(msg))

    def setActuator(self, actuator, state):
        if(actuator == "windows"):
            if(self.windows_state == state):
                return 409
            if(self.isRoomClosed() and state == "Open"):
                return 409
            self.windows_state = state
            self.publish_actuator_data("windows")
            return 200
        if(actuator == "ventilation"):
            if(self.ventilation_state == state):
                return 409
            self.ventilation_state = state
            self.publish_actuator_data("ventilation")
            return 200
        
class ActuatorsRestService:
    exposed = True
    def __init__(self, connector):
        self.connector = connector

    def GET(self, *uri, **params):
        if(len(uri) == 0 or uri[0] not in ["windows", "ventilation"]):
            return cherrypy.HTTPError(400, "Invalid URI")
        msg = {
            'bn': self.connector.config['mqttInfos']['basename'] + "/actuators",
            'bt': time.time(),
            'e': [
                {
                    'n': "",
                    'u': "state",
                    'v': None
                }
            ]
        }
        if(uri[0] == "windows"):
            msg['e'][0]['n'] = "windows"
            msg['e'][0]['v'] = self.connector.windows_state
        if(uri[0] == "ventilation"):
            msg['e'][0]['n'] = "ventilation"
            msg['e'][0]['v'] = self.connector.ventilation_state
        return json.dumps(msg).encode('utf-8')
    
    def PUT(self, *uri, **params):
        if(len(uri) == 0 or uri[0] not in ["windows", "ventilation"]):
            return cherrypy.HTTPError(400, "Invalid URI")
        if('state' not in params):
            return cherrypy.HTTPError(400, "Invalid parameters")
        if(params['state'] not in ["On", "Off", "Open", "Closed"]):
            return cherrypy.HTTPError(400, "Invalid state")
        retCode = self.connector.setActuator(uri[0], params['state'])
        if retCode == 200:
            return json.dumps({"result": "State changed successfuly"}).encode('utf-8')
        return cherrypy.HTTPError(retCode, "Error changing state (the room is already in that state or currently closed)")

if __name__ == '__main__':
    config = json.load(open("config-actuator.json"))

    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }

    connector = ActuatorsConnector(config)
    service = ActuatorsRestService(connector)

    # Start the thread that periodically updates the device at the catalog and closes the windows when the room is closed
    t = threading.Thread(target=connector.periodically_register_device_and_close_windows)
    t.start()

    # To stop the thread when CherryPy stops
    def shutdown():
        print("Stopping catalog registering thread...")
        connector.thread_stop.set()
        connector.mqtt_client.stop()

    cherrypy.engine.subscribe('stop', shutdown)

    cherrypy.tree.mount(service, '/', conf)
    cherrypy.config.update({
        'server.socket_port': 8080,
        "tools.response_headers.on": True,
        "tools.response_headers.headers": [("Content-Type", "application/json")]
    })
    cherrypy.engine.start()
    cherrypy.engine.block()