
import dateparser
from datetime import datetime
import uuid

from storage import load_exams, save_exams

def add_exam(subject, date_str):
    """Adds an exam to the list."""
    exam_date = dateparser.parse(date_str)
    if not exam_date:
        raise ValueError("Invalid date format")

    exams = load_exams()
    exams.append({
        "id": str(uuid.uuid4()),
        "subject": subject,
        "date": exam_date.strftime("%Y-%m-%d")
    })
    save_exams(exams)
    return f"Exam '{subject}' on {exam_date.strftime('%Y-%m-%d')} added."

def get_exam_countdowns():
    """Returns a list of exams with countdowns."""
    exams = load_exams()
    today = datetime.now()
    
    countdowns = []
    for exam in exams:
        exam_date = datetime.strptime(exam["date"], "%Y-%m-%d")
        days_left = (exam_date - today).days
        
        if days_left < 3:
            color_code = "🔴"  # Red
        elif 3 <= days_left <= 7:
            color_code = "🟡"  # Yellow
        else:
            color_code = "🟢"  # Green
            
        countdowns.append({
            "subject": exam["subject"],
            "days_left": days_left,
            "color_code": color_code
        })
    
    # Sort by urgency
    countdowns.sort(key=lambda x: x["days_left"])
    return countdowns

def insert_countdowns_into_note():
    """Formats the countdowns for Markdown."""
    countdowns = get_exam_countdowns()
    
    markdown_output = "## Upcoming Exams\n"
    for exam in countdowns:
        markdown_output += f"- {exam['subject']}: {exam['days_left']} days left {exam['color_code']}\n"
        
    return markdown_output
