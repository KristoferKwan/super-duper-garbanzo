import requests
from langchain.tools import BaseTool

class GetCurrentLocationTool(BaseTool):
    name = "GetCurrentLocation"
    description = "This tool returns the users current location. use this tool when the user is trying to find places nearby to visit, if you dont already know their current location."

    def _get_location(self):
        response = requests.get(f'http://ip-api.com/json/').json()
        return str(response)

    def _run(self, query : str):
        return self._get_location()

    def _arun(self):
        raise NotImplementedError("This tool does not support async")
