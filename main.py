import os
import csv
import regex as re
import logging
import requests
import sys
from requests.auth import HTTPBasicAuth
from threading import Thread
from queue import Queue

config = {
    'email': '<email>', 
    'token' : "",  
    'base_url' : "https://<domain>.atlassian.net",
    'api_version': 3
}

env = 'cloud'
regex_patterns_file = 'regex_patterns.csv'
log_file = 'application.log'  # Define the log file name

AUTH = HTTPBasicAuth(config['email'], config['token'])
HEADERS = {"Accept": "application/json"}
PROCESSED_PROJECTS_FILE = 'processed_projects.csv'
FOUND_ISSUES_FILE = 'found_issues.csv'
RUNNING_PROJECTS_FILE = 'running_projects.txt'

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler(log_file)  
file_handler.setLevel(logging.INFO)  
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))  
logger.addHandler(file_handler) 

# Load processed projects from file
def load_processed_projects():
    processed = set()
    if os.path.exists(PROCESSED_PROJECTS_FILE):
        with open(PROCESSED_PROJECTS_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            next(reader, None)  # Skip header
            for row in reader:
                processed.add(row[0])
    return processed

# Load regex patterns from file along with rule names
def load_regex_patterns(file_path):
    patterns = []
    if os.path.exists(file_path):
        with open(file_path, mode='r', newline='') as file:
            reader = csv.DictReader(file, delimiter=',')
            logging.info("Detected CSV Headers: %s", reader.fieldnames)
            for row in reader:
                patterns.append((row['Rule Name'], row['Regular Expression']))
    else:
        logging.error(f"File '{file_path}' does not exist.")
    return patterns

PROCESSED_PROJECTS = load_processed_projects()
REGEX_PATTERNS = load_regex_patterns(os.path.join(os.getcwd(), regex_patterns_file))

def add_to_running_projects(project_key):
    """Add a project key to the running projects file."""
    with open(RUNNING_PROJECTS_FILE, 'a') as file:
        file.write(project_key + '\n')

def remove_from_running_projects(project_key):
    """Remove a project key from the running projects file."""
    with open(RUNNING_PROJECTS_FILE, 'r') as file:
        lines = file.readlines()
    with open(RUNNING_PROJECTS_FILE, 'w') as file:
        for line in lines:
            if line.strip() != project_key:
                file.write(line)

def is_project_running(project_key):
    """Check if a project key is in the running projects file."""
    try:
        with open(RUNNING_PROJECTS_FILE, 'r') as file:
            for line in file:
                if line.strip() == project_key:
                    return True
    except FileNotFoundError:
        return False
    return False

# Initialize files if not present
if not os.path.exists(PROCESSED_PROJECTS_FILE):
    with open(PROCESSED_PROJECTS_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Project Key'])

# Append rows to CSV files
def append_to_csv(file_name, row):
    with open(file_name, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row)
        
# Text extraction and pattern checking functions
def extract_text_from_node(node):
    text = ''
    if 'text' in node:
        return node['text']
    if 'content' in node:
        for child in node['content']:
            text += extract_text_from_node(child)
    return text

def extract_text(content):
    full_text = ''
    for node in content['content']:
        full_text += extract_text_from_node(node)
    return full_text

# Function to check text against patterns
def check_patterns(text, issue_key, type, url):
    if text:
        for rule_name, pattern in REGEX_PATTERNS:
            if re.search(pattern, text):
                separator = "*" * 50  # Creates a line of asterisks
                append_to_csv(FOUND_ISSUES_FILE, [issue_key, rule_name, type, url])
                logging.warning(separator)
                logging.warning(f"!!! ALERT: Found {rule_name} pattern in issue {issue_key}  !!!")
                logging.warning(separator)
                
# Main functions to process projects and issues
def worker(project_queue):
    while not project_queue.empty():
        project_key = project_queue.get()
        if project_key not in PROCESSED_PROJECTS and not is_project_running(project_key):
            add_to_running_projects(project_key)
            try:
                process_issues(project_key)
                append_to_csv(PROCESSED_PROJECTS_FILE, [project_key])
                PROCESSED_PROJECTS.add(project_key)
            finally:
                remove_from_running_projects(project_key)
        project_queue.task_done()
def check_description_history(issue_key):

    url = f"{config['base_url']}/rest/api/{config['api_version']}/issue/{issue_key}/changelog"

    response = requests.get(url, auth=AUTH, headers=HEADERS)
    if response.status_code == 200:
        changes = response.json()
        for history_item in changes['values']:
            for item in history_item['items']:
                if item['field'] == 'description':
                    old_description = item.get('fromString', '')
                    #new_description = item.get('toString', '')
                    check_patterns(old_description, issue_key, "comment", f"{config['base_url']}/browse/{issue_key}")

    else:
        logging.error(f"Failed to retrieve changelog: {response.status_code}")
        logging.error(response.text)


def process_issues(project_key):
    start_at = 0
    max_results = 50
    issues_found = True
    while issues_found:
        issues_response = requests.get(f"{config['base_url']}/rest/api/{config['api_version']}/search?jql=project=\'{project_key}\'&startAt={start_at}&maxResults={max_results}", auth=AUTH, headers=HEADERS)
        issues = issues_response.json()
        issues_found = 'issues' in issues and len(issues['issues']) > 0
        
        for issue in issues['issues']:
            issue_key = issue['key']
            logging.info(f"Processing issue {issue_key} in project {project_key}")
            description = issue['fields'].get('description', '')
            if description:
                #logging.info("Description...")
                if env == 'cloud':
                    check_patterns(extract_text(description), issue_key, "description", f"{config['base_url']}/browse/{issue_key}")
                else:
                    check_patterns(description, issue_key, "description", f"{config['base_url']}/browse/{issue_key}")
            
            comments_response = requests.get(f"{config['base_url']}/rest/api/{config['api_version']}/issue/{issue_key}/comment", auth=AUTH, headers=HEADERS)
            comments = comments_response.json()
            
            #logging.info(f"{comments['total']} comment(s)...")
            
            for comment in comments.get('comments', []):
                comment_content = comment.get('body', {})
                if env == 'cloud':
                    check_patterns(extract_text(comment_content), issue_key, "comment", f"{config['base_url']}/browse/{issue_key}")
                else:
                    check_patterns(comment_content, issue_key, "comment", f"{config['base_url']}/browse/{issue_key}")
            #logging.info("History...\n")
            check_description_history(issue_key)

        start_at += max_results

def process_projects(thread_count=50):
    project_queue = Queue()
    # Load projects into the queue
    start_at = 0
    max_results = 50
    more_projects = True
    while more_projects:
        projects_response = requests.get(f"{config['base_url']}/rest/api/{config['api_version']}/project?startAt={start_at}&maxResults={max_results}", auth=AUTH, headers=HEADERS)
        if projects_response.status_code == 200:
            projects = projects_response.json()
            more_projects = len(projects) == max_results
            for project in projects:
                project_key = project['key']
                project_queue.put(project_key)
        else:
            logging.error(f"Failed to load projects: {projects_response.status_code}")
            break
        start_at += max_results

    threads = []
    for _ in range(thread_count):
        thread = Thread(target=worker, args=(project_queue,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
if __name__ == '__main__':
    thread_count = int(sys.argv[1]) if len(sys.argv) > 1 else 5  # Default to 5 threads if not specified
    process_projects(thread_count)

