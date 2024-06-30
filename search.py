from langchain.utilities import DuckDuckGoSearchAPIWrapper
from langchain.agents import Tool

search = DuckDuckGoSearchAPIWrapper()

search_tool = Tool(name="Current Search",
                   func=search.run,
                   description="Useful to look up current information on the web, such as restaurants nearby."
                   )