
import argparse
import logging

from exam_manager import add_exam, get_exam_countdowns, insert_countdowns_into_note
from calendar_export import export_to_ics

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    parser = argparse.ArgumentParser(description="A note-taking app with academic productivity features.")
    subparsers = parser.add_subparsers(dest="command")

    # Add exam command
    add_parser = subparsers.add_parser("add-exam", help="Add a new exam.")
    add_parser.add_argument("subject", type=str, help="The subject of the exam.")
    add_parser.add_argument("date", type=str, help="The date of the exam (e.g., 'next Monday', 'in 3 weeks').")

    # Show countdowns command
    subparsers.add_parser("show-countdowns", help="Show countdowns for all exams.")

    # Insert countdowns command
    subparsers.add_parser("insert-countdowns", help="Insert countdowns into a Markdown note.")
    
    # Export calendar command
    subparsers.add_parser("export-calendar", help="Export exams to an .ics file.")

    args = parser.parse_args()

    try:
        if args.command == "add-exam":
            message = add_exam(args.subject, args.date)
            logging.info(message)
        elif args.command == "show-countdowns":
            countdowns = get_exam_countdowns()
            for exam in countdowns:
                print(f"- {exam['subject']}: {exam['days_left']} days left {exam['color_code']}")
        elif args.command == "insert-countdowns":
            markdown = insert_countdowns_into_note()
            # In a real app, you would insert this into a note.
            # For this example, we'll just print it.
            print(markdown)
        elif args.command == "export-calendar":
            message = export_to_ics()
            logging.info(message)
        else:
            parser.print_help()
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
