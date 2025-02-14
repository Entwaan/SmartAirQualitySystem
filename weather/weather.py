import cherrypy
import json
import openmeteo_requests
import requests_cache
from retry_requests import retry
import pandas as pd
import requests

# Setup the coordinates of the buildings
locations = {
    "Aule_I": {
        "latitude": 45.065037,
        "longitude": 7.658205,
    }
}

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# Base URL for the API
url = "https://api.open-meteo.com/v1/forecast"

class WeatherService:
    exposed = True

    def GET(self, *uri, **params):
        """
        Provides weather data on demand via REST.
        """
        all_weather_data = []

        for building_name, building_data in locations.items():
            query_params = {
                "latitude": building_data["latitude"],
                "longitude": building_data["longitude"],
                "current": ["temperature_2m", "precipitation", "wind_speed_10m", "wind_direction_10m"],
                "hourly": ["temperature_2m", "precipitation_probability", "wind_speed_10m", "wind_direction_10m"],
                "forecast_days": 1
            }

            responses = openmeteo.weather_api(url, params=query_params)
            for response in responses:
                weather_data = {
                    "building_name": building_name,
                    "coordinates": {
                        "latitude": float(response.Latitude()),
                        "longitude": float(response.Longitude())
                    },
                    "elevation": float(response.Elevation()),
                    "timezone": {
                        "name": response.Timezone(),
                        "abbreviation": response.TimezoneAbbreviation(),
                        "utc_offset_seconds": response.UtcOffsetSeconds()
                    },
                    "current_weather": {},
                    "hourly_weather": []
                }

                # Actual data
                current = response.Current()
                weather_data["current_weather"] = {
                    "time": current.Time(),
                    "temperature_2m": float(current.Variables(0).Value()),
                    "precipitation": float(current.Variables(1).Value()),
                    "wind_speed_10m": float(current.Variables(2).Value()),
                    "wind_direction_10m": float(current.Variables(3).Value())
                }

                # Hourly data process
                hourly = response.Hourly()
                hourly_dates = pd.date_range(
                    start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                    end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                    freq=pd.Timedelta(seconds=hourly.Interval()),
                    inclusive="left"
                )
                hourly_data = {
                    "temperature_2m": [float(val) for val in hourly.Variables(0).ValuesAsNumpy()],
                    "precipitation_probability": [float(val) for val in hourly.Variables(1).ValuesAsNumpy()],
                    "wind_speed_10m": [float(val) for val in hourly.Variables(2).ValuesAsNumpy()],
                    "wind_direction_10m": [float(val) for val in hourly.Variables(3).ValuesAsNumpy()]
                }

                # Add hourly data in the json
                for i, date in enumerate(hourly_dates):
                    weather_data["hourly_weather"].append({
                        "time": str(date),
                        "temperature_2m": hourly_data["temperature_2m"][i],
                        "precipitation_probability": hourly_data["precipitation_probability"][i],
                        "wind_speed_10m": hourly_data["wind_speed_10m"][i],
                        "wind_direction_10m": hourly_data["wind_direction_10m"][i]
                    })

                # Add to global json
                all_weather_data.append(weather_data)

        return json.dumps(all_weather_data)

if __name__ == "__main__":
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8081,
        'log.screen': True
    })
    cherrypy.quickstart(WeatherService(), '/')
