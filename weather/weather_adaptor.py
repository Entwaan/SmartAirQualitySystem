import json
import requests
import cherrypy

class WeatherAdaptor:
    exposed = True

    def __init__(self):
        with open("config-weather-adaptor.json", "r") as config_file:
            self.config = json.load(config_file)
        self.api_url = self.config["weatherAPI"]["url"]
        self.api_params = self.config["weatherAPI"]["params"]

    def GET(self):
        """Fetch real-time weather data from an external API and return it."""
        try:
            response = requests.get(self.api_url, params=self.api_params)
            response.raise_for_status()
            return json.dumps(response.json()).encode("utf-8")
        except requests.exceptions.RequestException as e:
            cherrypy.response.status = 500
            return json.dumps({"error": str(e)}).encode("utf-8")

if __name__ == "__main__":
    # Load configuration from config-weather-adaptor.json
    with open("config-weather-adaptor.json", "r") as config_file:
        config = json.load(config_file)

    cherrypy.config.update({
        "server.socket_host": config["server"]["host"],
        "server.socket_port": config["server"]["port"],
        "log.screen": True
    })

    # Use MethodDispatcher so that HTTP methods are handled by GET, POST, etc.
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')]
        }
    }

    cherrypy.quickstart(WeatherAdaptor(), '/', conf)
