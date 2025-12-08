
from ics import Calendar, Event
from datetime import datetime

from storage import load_exams

def export_to_ics():
    """Exports exams to an iCalendar (.ics) file."""
    exams = load_exams()
    cal = Calendar()

    for exam in exams:
        event = Event()
        event.name = f"{exam['subject']} Exam"
        event.begin = datetime.strptime(exam["date"], "%Y-%m-%d")
        event.make_all_day()
        cal.events.add(event)

    with open('exams.ics', 'w') as f:
        f.writelines(cal)
        
    return "Exams exported to exams.ics"
