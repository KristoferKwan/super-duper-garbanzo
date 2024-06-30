from dotenv import load_dotenv
load_dotenv("./.env")

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.tools import tool
from langchain_core.prompts.chat import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from google_calendar import geteventstool, createeventtool
from datetime import date
from location import GetCurrentLocationTool

@tool
def getDate() -> str:
    """Retrieves the real time date and time. You should use this tool whenever the user tries to schedule an event."""
    return date.today()


llm = ChatOpenAI(temperature=0.0)
tools = load_tools(
    ["human"]
)

tools.append(TavilySearchResults())
tools.append(geteventstool)
tools.append(createeventtool)
tools.append(getDate)
tools.append(GetCurrentLocationTool())

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant. You may not need to use tools for every query - the user may just want to chat!",
        ),
        ("placeholder", "{messages}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

agent = create_tool_calling_agent(llm, tools, prompt)

# Create an agent executor by passing in the agent and tools
agent_executor = AgentExecutor(
     agent=agent, tools=tools, verbose=True, handle_parsing_errors=True, memory=memory
)

demo_ephemeral_chat_history_for_chain = ChatMessageHistory()

conversational_agent_executor = RunnableWithMessageHistory(
    agent_executor,
    lambda session_id: demo_ephemeral_chat_history_for_chain,
    input_messages_key="messages",
    output_messages_key="output",
)

while True:
    user_input = input("Enter a message (type q to quit): ")
    if user_input == "q":
        break
    conversational_agent_executor.invoke({"messages": [HumanMessage(content=user_input)]}, {"configurable" : {"session_id": "demo"}})
    #agent_executor.invoke({"input": user_input})
    #agent_chain.invoke(user_input)