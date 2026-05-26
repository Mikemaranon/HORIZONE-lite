from datetime import datetime


TOOL_NAME = "current_date"
TOOL_DISPLAY_NAME = "current date"
TOOL_DESCRIPTION = "Returns the current local date, time, and timezone."
TOOL_PARAMETERS = {}
TOOL_CAPABILITIES = [
    "read the current local date",
    "read the current local time and timezone",
]
TOOL_USE_WHEN = [
    "The answer depends on the current date, time, day, or timezone.",
]
TOOL_RISK_LEVEL = "read_only"


def run(arguments: dict) -> dict:
    now = datetime.now().astimezone()
    return {
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timezone": str(now.tzinfo or ""),
        "iso_datetime": now.isoformat(),
    }
