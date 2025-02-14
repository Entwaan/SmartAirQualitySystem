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

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self):
        """Fetch real-time weather data from an external API and return it."""
        try:
            response = requests.get(self.api_url, params=self.api_params)
            response.raise_for_status()
            return response.json()  
        except requests.exceptions.RequestException as e:
            cherrypy.response.status = 500
            return {"error": str(e)}

if __name__ == "__main__":
    
    with open("config-weather-adaptor.json", "r") as config_file:
        config = json.load(config_file)

    cherrypy.config.update({
        "server.socket_host": config["server"]["host"],
        "server.socket_port": config["server"]["port"],
        "log.screen": True
    })
    
    cherrypy.quickstart(WeatherAdaptor(), "/")
