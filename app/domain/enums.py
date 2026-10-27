from enum import Enum

class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class Category(str, Enum):
    ACADEMIC = "Academic"
    WORK = "Work"
    PERSONAL = "Personal"
    CAREER = "Career"

class Completion(str, Enum):
    INCOMPLETE = "Incomplete"
    COMPLETE = "Complete"

class Source(str, Enum):
    MANUAL = "manual"
    ICS_IMPORT = "ics_import"