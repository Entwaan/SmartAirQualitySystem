import cherrypy
import json

received_data = None

class WeatherAdapter:
    exposed = True

    def GET(self, *uri, **params):
      
        if not uri:
            return json.dumps({"status": "success", "message": "Weather Adaptor API is running"})
        elif uri[0] == "data":
            return self.get_data()
        else:
            return json.dumps({"status": "error", "message": "Invalid endpoint"})

    def POST(self, *uri, **params):
        global received_data
        try:
            content_length = cherrypy.request.headers['Content-Length']
            raw_body = cherrypy.request.body.read(int(content_length))
            received_data = json.loads(raw_body)

            if not received_data:
                return json.dumps({"status": "error", "message": "No data received"})
            
            # Sanity check
            print("Received JSON data (first line):", received_data[0])
            
            return json.dumps({"status": "success", "message": "Data received successfully"})
        except Exception as e:
            print(f"Error receiving data: {e}")
            return json.dumps({"status": "error", "message": "Internal Server Error"})

    def get_data(self):
        global received_data
        if received_data is None:
            return json.dumps({"status": "error", "message": "No data received yet"})

        return json.dumps({"first_line": received_data[0]})

if __name__ == "__main__":
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8080,
        'log.screen': True
    })
    cherrypy.quickstart(WeatherAdapter(), '/')
