
import json
import os

DATA_FILE = 'exams.json'

def load_exams():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_exams(exams):
    with open(DATA_FILE, 'w') as f:
        json.dump(exams, f, indent=4)
