import cherrypy
import datetime
import time
import json
import uuid
import threading

class CatalogService:
    exposed = True

    def __init__(self):
        self.broker = self.load_json("broker.json")
        self.devices = self.load_json("devices.json")
        self.users = self.load_json("users.json")
        self.rooms = self.load_json("rooms.json")

        # Flag to stop the cleaning thread
        self.thread_stop = threading.Event()

        # Start the thread
        cleanup_thread = threading.Thread(target=self.periodic_cleanup)
        cleanup_thread.start()

    @staticmethod
    def validate_fields(required_fields, data):
        """Validate that all required fields are present in the data."""
        for field in required_fields:
            if field not in data:
                raise cherrypy.HTTPError(400, f"Invalid request: '{field}' is required")

    @staticmethod
    def load_json(file_name):
        """Load JSON data from a file."""
        try:
            with open(file_name, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return []

    @staticmethod
    def save_json(file_name, data):
        """Save JSON data to a file."""
        with open(file_name, "w") as file:
            json.dump(data, file, indent=4)

    def periodic_cleanup(self):
        """Periodic cleanup thread to remove old devices every 2 minutes."""
        while not self.thread_stop.is_set():
            print("Running periodic cleanup...")
            devices = CatalogService.load_json("devices.json")
            current_time = datetime.datetime.now(datetime.timezone.utc)
            updated_devices = [
                device for device in devices
                if datetime.datetime.fromisoformat(device["insert-timestamp"]) > current_time - datetime.timedelta(minutes=2)
            ]
            rooms = CatalogService.load_json("rooms.json")
            for room in rooms:
                room["devices"] = [device for device in room["devices"] if device in [d["deviceID"] for d in updated_devices]]
            CatalogService.save_json("devices.json", updated_devices)
            CatalogService.save_json("rooms.json", rooms)
            time.sleep(10)

    def get_item(self, collection, item_id, item_name):
        """Get an item from a collection by ID."""
        item = next((item for item in collection if item[item_name] == item_id), None)
        if item:
            return json.dumps(item).encode('utf-8')
        raise cherrypy.HTTPError(404, f"{item_name.capitalize()} not found")

    def GET(self, *uri, **params):
        """Handle GET requests."""
        if uri[0] == "broker":
            return json.dumps(self.broker).encode('utf-8')
        if uri[0] == "devices":
            if len(uri) == 2:
                return self.get_item(self.devices, uri[1], "deviceID")
            return json.dumps(self.devices).encode('utf-8')
        if uri[0] == "rooms":
            if len(uri) == 2:
                return self.get_item(self.rooms, uri[1], "roomID")
            return json.dumps(self.rooms).encode('utf-8')
        if uri[0] == "users":
            if len(uri) == 2:
                return self.get_item(self.users, uri[1], "userID")
            return json.dumps(self.users).encode('utf-8')

    def add_item(self, collection, item, file_name):
        """Add an item to a collection and save to file."""
        collection.append(item)
        self.save_json(file_name, collection)
        return json.dumps(item).encode('utf-8')

    def POST(self, *uri, **params):
        """Handle POST requests."""
        if uri[0] == "devices":
            device = json.loads(cherrypy.request.body.read())
            self.validate_fields(["ip", "port", "endpoints", "availableResources", "roomID"], device)
            if "mqtt" in device["endpoints"]:
                self.validate_fields(["topics"], device["endpoints"]["mqtt"])
            if "rest" in device["endpoints"]:
                self.validate_fields(["restIP"], device["endpoints"]["rest"])
            if not any(room["roomID"] == device["roomID"] for room in self.rooms):
                raise cherrypy.HTTPError(404, "Referenced room not found")
            device["deviceID"] = str(uuid.uuid4())
            device["insert-timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for room in self.rooms:
                if room["roomID"] == device["roomID"]:
                    room["devices"].append(device["deviceID"])
                    break
            self.save_json("rooms.json", self.rooms)
            return self.add_item(self.devices, device, "devices.json")

        if uri[0] == "rooms":
            room = json.loads(cherrypy.request.body.read())
            self.validate_fields(["number", "floor", "buildingName", "openingHours", "coordinates"], room)
            room["roomID"] = str(uuid.uuid4())
            room["devices"] = []
            return self.add_item(self.rooms, room, "rooms.json")

        if uri[0] == "users":
            user = json.loads(cherrypy.request.body.read())
            self.validate_fields(["username", "telegramChatID", "rooms"], user)
            for roomID in user["rooms"]:
                if not any(room["roomID"] == roomID for room in self.rooms):
                    raise cherrypy.HTTPError(404, "Referenced room not found")
            user["userID"] = str(uuid.uuid4())
            return self.add_item(self.users, user, "users.json")

    def update_item(self, collection, item, item_id, item_name, file_name):
        """Update an item in a collection and save to file."""
        for i, existing_item in enumerate(collection):
            if existing_item[item_name] == item_id:
                collection[i] = item
                self.save_json(file_name, collection)
                return json.dumps(item).encode('utf-8')
        raise cherrypy.HTTPError(404, f"{item_name.capitalize()} not found")

    def PUT(self, *uri, **params):
        """Handle PUT requests."""
        if len(uri) == 2 and uri[0] == "devices":
            device = json.loads(cherrypy.request.body.read())
            self.validate_fields(["ip", "port", "endpoints", "availableResources", "roomID"], device)
            if "mqtt" in device["endpoints"]:
                self.validate_fields(["topics"], device["endpoints"]["mqtt"])
            if "rest" in device["endpoints"]:
                self.validate_fields(["restIP"], device["endpoints"]["rest"])
            if not any(room["roomID"] == device["roomID"] for room in self.rooms):
                raise cherrypy.HTTPError(404, "Referenced room not found")
            device["deviceID"] = uri[1]
            device["insert-timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            return self.update_item(self.devices, device, uri[1], "deviceID", "devices.json")

        if len(uri) == 2 and uri[0] == "rooms":
            room = json.loads(cherrypy.request.body.read())
            self.validate_fields(["number", "floor", "buildingName", "openingHours", "coordinates", "devices"], room)
            room["roomID"] = uri[1]
            return self.update_item(self.rooms, room, uri[1], "roomID", "rooms.json")

        if len(uri) == 2 and uri[0] == "users":
            user = json.loads(cherrypy.request.body.read())
            self.validate_fields(["username", "telegramChatID", "rooms"], user)
            user["userID"] = uri[1]
            for roomID in user["rooms"]:
                if not any(room["roomID"] == roomID for room in self.rooms):
                    raise cherrypy.HTTPError(404, "Referenced room not found")
            return self.update_item(self.users, user, uri[1], "userID", "users.json")

        raise cherrypy.HTTPError(400, "Invalid request")

    def delete_item(self, collection, item_id, item_name, file_name):
        """Delete an item from a collection and save to file."""
        for i, item in enumerate(collection):
            if item[item_name] == item_id:
                del collection[i]
                self.save_json(file_name, collection)
                return
        raise cherrypy.HTTPError(404, f"{item_name.capitalize()} not found")

    def DELETE(self, *uri, **params):
        """Handle DELETE requests."""
        if len(uri) == 2 and uri[0] == "devices":
            return self.delete_item(self.devices, uri[1], "deviceID", "devices.json")

        if len(uri) == 2 and uri[0] == "rooms":
            for i, room in enumerate(self.rooms):
                if room["roomID"] == uri[1]:
                    del self.rooms[i]
                    self.devices = [d for d in self.devices if d["roomID"] != uri[1]]
                    self.save_json("rooms.json", self.rooms)
                    self.save_json("devices.json", self.devices)
                    return
            raise cherrypy.HTTPError(404, "Room not found")

        if len(uri) == 2 and uri[0] == "users":
            return self.delete_item(self.users, uri[1], "userID", "users.json")

        raise cherrypy.HTTPError(400, "Invalid request")

if __name__ == '__main__':
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }

    service = CatalogService()

    # To stop the thread when CherryPy stops
    def shutdown():
        print("Stopping cleaning thread...")
        service.thread_stop.set()

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
