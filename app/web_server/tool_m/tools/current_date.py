from datetime import datetime


TOOL_NAME = "current_date"
TOOL_DISPLAY_NAME = "current date"
TOOL_DESCRIPTION = "Returns the current local date, time, and timezone."
TOOL_PARAMETERS = {}


def run(arguments: dict) -> dict:
    now = datetime.now().astimezone()
    return {
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timezone": str(now.tzinfo or ""),
        "iso_datetime": now.isoformat(),
    }
