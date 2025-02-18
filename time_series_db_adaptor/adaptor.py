import json
import requests
import time
from datetime import datetime

import cherrypy
import mysql.connector

from MyMQTT import *

class TimeSeriesAdaptor:
    exposed = True

    def __init__(self):
        self.settings = json.load(open('config-time-series-db-adaptor.json'))
        print("Connecting to MySQL database...", flush=True)
        time.sleep(10)
        self.db = mysql.connector.connect(
            host=self.settings["dbConnection"]["host"],
            port=self.settings["dbConnection"]["port"],
            user=self.settings["dbConnection"]["user"],
            password=self.settings["dbConnection"]["password"],
            database=self.settings["dbConnection"]["database"]
        )

        self._get_broker()
        self.mqttClient = MyMQTT(self.settings["mqttInfos"]["clientId"], self.brokerIp, self.brokerPort, self)
        self.mqttClient.start()
        self._subscribe_to_all_devices()

    def _get_broker(self):
        self.catalog_ip = self.settings["catalog"]["ip"]
        self.catalog_port = self.settings["catalog"]["port"]
        response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/broker")
        broker_info = response.json()
        self.brokerIp = broker_info["ip"]
        self.brokerPort = broker_info["port"]

    def _subscribe_to_all_devices(self):
        response = requests.get(f"http://{self.catalog_ip}:{self.catalog_port}/devices")
        devices = response.json()

        for device in devices:
            topics = device["endpoints"]["mqtt"]["topics"]
            for topic in topics:
                self.mqttClient.mySubscribe(topic)

    def _fetch_results(self, query, params=None):
        cursor = self.db.cursor(dictionary=True)
        cursor.execute(query, params or ())
        results = cursor.fetchall()
    
        # Convert datetime fields to strings
        for row in results:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.strftime('%Y-%m-%d %H:%M:%S')
        
        return results

    def notify(self, topic, payload):
        message = json.loads(payload)
        message_json = json.loads(message)
        print(f"Received message on topic {topic}: {message_json}", flush=True)
        topic_parts = topic.split("/")
        building = topic_parts[1]
        floor = topic_parts[2]
        room = topic_parts[3]
        measureType = topic_parts[4]
        timestamp = datetime.utcfromtimestamp(message_json["bt"]).strftime('%Y-%m-%d %H:%M:%S')
        value = message_json["e"][0]["v"]
        if(measureType in ["aqi", "windows", "ventilation"]):
            print(f"Inserting data into database: {building}, {floor}, {room}, {measureType}, {value}, {timestamp}", flush=True)
            tables = {"aqi": "air_quality_index", "windows": "windows", "ventilation": "ventilation"}
            query = f"INSERT INTO {tables[measureType]} (building, floor, room, value, timestamp) VALUES (%s, %s, %s, %s, %s)"
            print(query, (building, floor, room, value, timestamp), flush=True)
            self._fetch_results(query, (building, floor, room, value, timestamp))


    def stopMqttClient(self):
        self.mqttClient.stop()

    def GET(self, *uri, **params):
        """Handle GET requests."""
        if not uri:
            return json.dumps({"error": "Invalid endpoint"}).encode('utf-8')

        endpoint = uri[0]
        if endpoint not in ["aqi", "windows", "ventilation"]:
            return json.dumps({"error": "Invalid endpoint"}).encode('utf-8')
        if endpoint == "aqi":
            table = "air_quality_index"
        else :
            table = endpoint

        building = params.get("building")
        floor = params.get("floor")
        room = params.get("room")
        time_range = params.get("range")  # '1h', '30m', '1d', '1y'

        query = f"SELECT * FROM {table} WHERE 1=1"
        query_params = []

        if room:
            query += " AND room = %s"
            query_params.append(room)
        
        if floor:
            query += " AND floor = %s"
            query_params.append(floor)
        
        if building:
            query += " AND building = %s"
            query_params.append(building)

        if time_range:
            time_units = {"m": "MINUTE", "h": "HOUR", "d": "DAY", "y": "YEAR"}
            unit = time_units.get(time_range[-1])  # 'h', 'm', 'y'

            if unit:
                value = int(time_range[:-1])
                query += f" AND timestamp >= NOW() - INTERVAL %s {unit}"
                query_params.append(value)
            else:
                return json.dumps({"error": "Invalid time range unit"}).encode('utf-8')

        results = self._fetch_results(query, query_params)
        print(f"Results: {results}", flush=True)
        return json.dumps(results).encode('utf-8')

if __name__ == '__main__':
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }
    service = TimeSeriesAdaptor()

    # To stop the mqtt client when CherryPy stops
    def shutdown():
        print("Stopping mqtt client...")
        service.stopMqttClient()

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

