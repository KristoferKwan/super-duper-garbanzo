from __future__ import annotations
from datetime import datetime, timedelta
from dateutil import parser, tz
from typing import Any, List, Dict, Optional, Type, TYPE_CHECKING
from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from langchain_community.tools.gmail.utils import (
    build_resource_service,
    get_gmail_credentials,
)
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import BaseTool, tool
if TYPE_CHECKING:
    # This is for linting and IDE typehints
    from googleapiclient.discovery import Resource
else:
    try:
        # We do this so pydantic can resolve the types when instantiating
        from googleapiclient.discovery import Resource
    except ImportError:
        pass


class TimeZoneInput(BaseModel):
    timezone: str = Field(
        description="The timezone in TZ Database Name format, e.g. 'America/New_York'"
    )


@tool("get_current_time", args_schema=TimeZoneInput)
def get_current_time(timezone: str) -> str:
    """Look up the current time based on timezone, returns %Y-%m-%d %H:%M:%S format"""
    
    user_timezone = tz.gettz(timezone)
    # cannot use tz.tzlocal() on server
    now = datetime.now(tz=user_timezone)
    return now.strftime('%Y-%m-%d %H:%M:%S')


class GoogleCalendarBaseTool(BaseTool):
    """Base class for Google Calendar tools."""
    
    api_resource: Resource = Field(default_factory=build_resource_service)
    
    @classmethod
    def from_api_resource(cls, api_resource: Resource) -> "GoogleCalendarBaseTool":
        """Create a tool from an api resource.

        Args:
            api_resource: The api resource to use.

        Returns:
            A tool.
        """
        return cls(api_resource=api_resource)
    

# List events tool
class GetEventsSchema(BaseModel):
    # https://developers.google.com/calendar/api/v3/reference/events/list
    start_datetime: str = Field(
        #default=datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        description=(
            " The start datetime for the event in the following format: "
            ' YYYY-MM-DDTHH:MM:SS, where "T" separates the date and time '
            " components, "
            ' For example: "2023-06-09T10:30:00" represents June 9th, '
            " 2023, at 10:30 AM"
            "Do not include timezone info as it will be automatically processed."
        )
    )
    end_datetime: str = Field(
        #default=(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S'),
        description=(
            " The end datetime for the event in the following format: "
            ' YYYY-MM-DDTHH:MM:SS, where "T" separates the date and time '
            " components, "
            ' For example: "2023-06-09T10:30:00" represents June 9th, '
            " 2023, at 10:30 AM"
            "Do not include timezone info as it will be automatically processed."
        )
    )
    max_results: int = Field(
        default=10,
        description="The maximum number of results to return.",
    )
    timezone: str = Field(
        default="America/Chicago",
        description="The timezone in TZ Database Name format, e.g. 'America/New_York'"
    )    
    
    
class ListGoogleCalendarEvents(GoogleCalendarBaseTool):
    name: str = "list_google_calendar_events"
    description: str = (
        " Use this tool to search for the user's calendar events (can also be called users's schedule)."
        " The input must be the start and end datetimes for the search query."
        " Start time is default to the current time. You can also specify the"
        " maximum number of results to return. The output is a JSON list of "
        " all the events in the user's calendar between the start and end times."
    )
    args_schema: Type[BaseModel] = GetEventsSchema
    
    def _parse_event(self, event, timezone):
        # convert to local timezone
        start = event['start'].get('dateTime', event['start'].get('date'))
        start = parser.parse(start).astimezone(tz.gettz(timezone)).strftime('%Y/%m/%d %H:%M:%S')
        end = event['end'].get('dateTime', event['end'].get('date'))
        end = parser.parse(end).astimezone(tz.gettz(timezone)).strftime('%Y/%m/%d %H:%M:%S')
        event_parsed = dict(start=start, end=end)
        for field in ['id','summary','description','location','hangoutLink']: # optional: attendees
            event_parsed[field] = event.get(field, None)
        return event_parsed
    
    def _get_calendars(self):
        calendars = []
        for cal in self.api_resource.calendarList().list().execute().get('items', []):
            if cal.get('selected', None): # select relevant calendars in google calendar UI
                calendars.append(cal['id'])
        return calendars
    
    def _run(
        self, 
        start_datetime: str, 
        end_datetime: str, 
        max_results: int = 10, # max results per calendar
        timezone: str = "America/Chicago",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> List(Dict[str, Any]):

        calendars = self._get_calendars()
        
        events = []
        start = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M:%S')
        start = start.replace(tzinfo=tz.gettz(timezone)).isoformat()
        end = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M:%S')
        end = end.replace(tzinfo=tz.gettz(timezone)).isoformat()
        for cal in calendars:
            events_result = self.api_resource.events().list(
                calendarId=cal,
                timeMin=start,
                timeMax=end,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
                ).execute()
            cal_events = events_result.get('items', [])
            events.extend(cal_events)
        
        events = sorted(events, key=lambda x: x['start'].get('dateTime', x['start'].get('date')))
        
        return [self._parse_event(e, timezone) for e in events]
    
    async def _arun(
        self, 
        start_datetime: str, 
        end_datetime: str, 
        max_results: int = 10, # max results per calendar
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> List(Dict[str, Any]):
        
        raise NotImplementedError("Async version of this tool is not implemented.")


# Create event tool
class CreateEventSchema(BaseModel):
    # https://developers.google.com/calendar/api/v3/reference/events/insert
    
    # note: modifed the tz desc in the parameters, use local time automatically
    start_datetime: str = Field(
        description=(
            " The start datetime for the event in the following format: "
            ' YYYY-MM-DDTHH:MM:SS, where "T" separates the date and time '
            " components, "
            ' For example: "2023-06-09T10:30:00" represents June 9th, '
            " 2023, at 10:30 AM"
            "Do not include timezone info as it will be automatically processed."
        )
    )
    end_datetime: str = Field(
        description=(
            " The end datetime for the event in the following format: "
            ' YYYY-MM-DDTHH:MM:SS, where "T" separates the date and time '
            " components, "
            ' For example: "2023-06-09T10:30:00" represents June 9th, '
            " 2023, at 10:30 AM"
            "Do not include timezone info as it will be automatically processed."
        )
    )
    summary: str = Field(
        description="The title of the event."
    )
    location: Optional[str] = Field(
        default="",
        description="The location of the event."
    )
    description: Optional[str] = Field(
        default="",
        description="The description of the event. Optional."
    )
    timezone: str = Field(
        default="America/Chicago",
        description="The timezone in TZ Database Name format, e.g. 'America/New_York'"
    )
    

class CreateGoogleCalendarEvent(GoogleCalendarBaseTool):
    name: str = "create_google_calendar_event"
    description: str = (
        " Use this tool to create a new calendar event in user's primary calendar."
        " The input must be the start and end datetime for the event, and"
        " the title of the event. You can also specify the location and description"
    )
    args_schema: Type[BaseModel] = CreateEventSchema
    
    def _run(
        self,
        start_datetime: str,
        end_datetime: str,
        summary: str,
        location: str = "",
        description: str = "",
        timezone: str = "America/Chicago",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
            
        start = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M:%S')
        start = start.replace(tzinfo=tz.gettz(timezone)).isoformat()
        end = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M:%S')
        end = end.replace(tzinfo=tz.gettz(timezone)).isoformat()
        
        calendar = '52fe3095fadf982fb7b98c6f738320b0effd235826ed493d803627b8144a4045@group.calendar.google.com' # specific calendar id to target
        body = {
            'summary': summary,
            'start': {
                'dateTime': start
            },
            'end': {
                'dateTime': end
            }
        }
        if location != "":
            body['location'] = location
        if description != "":
            body['description'] = description
        
        event = self.api_resource.events().insert(calendarId=calendar, body=body).execute()
        
        return "Event created: " + event.get('htmlLink', 'Failed to create event')
    
    async def _arun(
        self,
        start_datetime: str,
        end_datetime: str,
        summary: str,
        location: str = "",
        description: str = "",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        
        raise NotImplementedError("Async version of this tool is not implemented.")


# Update event tool
class UpdateEventSchema(BaseModel):
    # https://developers.google.com/calendar/api/v3/reference/events/insert
    event_id : str = Field(
        description="The event id to update. This can be retrieved from the id field in the event object returned by list_google_calendar_events tool."
    )
    # note: modifed the tz desc in the parameters, use local time automatically
    start_datetime: Optional[str] = Field(
        description=(
            " The start datetime for the event in the following format: "
            ' YYYY-MM-DDTHH:MM:SS, where "T" separates the date and time '
            " components, "
            ' For example: "2023-06-09T10:30:00" represents June 9th, '
            " 2023, at 10:30 AM"
            "Do not include timezone info as it will be automatically processed."
        )
    )
    end_datetime: Optional[str] = Field(
        description=(
            " The end datetime for the event in the following format: "
            ' YYYY-MM-DDTHH:MM:SS, where "T" separates the date and time '
            " components, "
            ' For example: "2023-06-09T10:30:00" represents June 9th, '
            " 2023, at 10:30 AM"
            "Do not include timezone info as it will be automatically processed."
        )
    )
    summary: Optional[str] = Field(
        description="The title of the event."
    )
    location: Optional[str] = Field(
        description="The location of the event."
    )
    description: Optional[str] = Field(
        description="The description of the event. Optional."
    )
    timezone: Optional[str] = Field(
        default="America/Chicago",
        description="The timezone in TZ Database Name format, e.g. 'America/New_York'"
    )
    

class UpdateGoogleCalendarEvent(GoogleCalendarBaseTool):
    name: str = "update_google_calendar_event"
    description: str = (
        " Use this tool to update an existing calendar event in user's primary calendar."
        " The input can optionally contain the start and end datetime for the event, and"
        " the title of the event. You can also specify the location and description. If no"
        " parameters are provided, the event will not be updated."
    )
    args_schema: Type[BaseModel] = UpdateEventSchema
    
    def _run(
        self,
        event_id: str,
        start_datetime: str = None, 
        end_datetime: str = None,
        summary: str = None,
        location: str = None,
        description: str = None,
        timezone: str = "America/Chicago",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        
        calendar = '52fe3095fadf982fb7b98c6f738320b0effd235826ed493d803627b8144a4045@group.calendar.google.com' # specific calendar id to target
        event = self.api_resource.events().get(calendarId=calendar, eventId=event_id).execute()

        if start_datetime is not None :
            start = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M:%S')
            start = start.replace(tzinfo=tz.gettz(timezone)).isoformat()
            event['start']['dateTime'] = start
        if end_datetime is not None:
            end = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M:%S')
            end = end.replace(tzinfo=tz.gettz(timezone)).isoformat()
            event['end']['dateTime'] = end
        if summary is not None:
            event['summary'] = summary

        if location is not None:
            event['location'] = location
        if description is not None:
            event['description'] = description
        
        event = self.api_resource.events().update(calendarId=calendar, eventId=event['id'], body=event).execute()
        
        return "Event updated: " + event.get('htmlLink', 'Failed to update event')
    
    async def _arun(
        self,
        event_id: str,
        start_datetime: str = None, 
        end_datetime: str = None,
        summary: str = None,
        location: str = None,
        description: str = None,
        timezone: str = "America/Chicago",
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        
        raise NotImplementedError("Async version of this tool is not implemented.")


# Testing Google Calendar tools

credentials = get_gmail_credentials(
token_file="./token.json",
scopes=["https://www.googleapis.com/auth/calendar"],
client_secrets_file="./credentials.json",
)

calendar_service = build_resource_service(credentials=credentials, service_name='calendar', service_version='v3')

geteventstool = ListGoogleCalendarEvents.from_api_resource(calendar_service)
# print(geteventstool.args)
# start = "2024-01-01T10:30:00"
# end = "2024-12-31T10:30:00"
# tool_res = geteventstool.run(tool_input={"start_datetime": start, "end_datetime":end, "max_results":10})
# for e in tool_res:
#     print(e['start'], e['summary'])
    
createeventtool = CreateGoogleCalendarEvent.from_api_resource(calendar_service)
# tool_res = createeventtool.run(tool_input={
#     "start_datetime": "2024-07-01T10:30:00",
#     "end_datetime": "2024-07-01T11:30:00", 
#     "summary": "Test event"
#     })
# print(tool_res)

updateeventtool = UpdateGoogleCalendarEvent.from_api_resource(calendar_service)
