import os
import csv
import regex as re
import logging
import requests
import time  
from requests.auth import HTTPBasicAuth
from threading import Thread
from queue import Queue

########################
# Configurations
########################

CONFIG = {
    'email': '<email>', 
    'token' : "",  
    'base_url' : "https://<domain>.atlassian.net",
}

REGEX_PATTERNS_FILE = 'regex_patterns.csv'
FOUND_ISSUES_FILE = 'found_issues.csv'
RUNNING_PROJECTS_FILE = 'running_projects.txt'
LOG_FILE = 'application.log'
PROCESSED_PROJECTS_FILE = 'processed_projects.csv'

AUTH = HTTPBasicAuth(CONFIG['email'], CONFIG['token'])
HEADERS = {"Accept": "application/json"}

########################
# Logging Setup
########################

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler(LOG_FILE)  
file_handler.setLevel(logging.INFO)  
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))  
logger.addHandler(file_handler) 

########################
# Utility Functions
########################

def extract_text_from_node(node):
    text = ''
    if 'text' in node:
        return node['text']
    if 'content' in node:
        for child in node['content']:
            text += extract_text_from_node(child)
    return text

def append_to_csv(file_name, row):
    """Append a row to a CSV file."""
    try:
        with open(file_name, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(row)
    except Exception as e:
        logging.error(f"Failed to write to file '{file_name}': {e}")

def check_patterns(text, issue_key, type, url):
    if text:
        for rule_name, pattern in REGEX_PATTERNS:
            if re.search(pattern, text):
                separator = "*" * 50  # Creates a line of asterisks
                append_to_csv(FOUND_ISSUES_FILE, [issue_key, rule_name, type, url])
                logging.warning(separator)
                logging.warning(f"!!! ALERT: Found {rule_name} pattern in issue {issue_key}  !!!")
                logging.warning(separator)

def extract_text(content):
    full_text = ''
    for node in content['content']:
        full_text += extract_text_from_node(node)
    return full_text

if not os.path.exists(PROCESSED_PROJECTS_FILE):
    with open(PROCESSED_PROJECTS_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Project Key'])
   
########################
# Data Loading Functions
########################

def load_processed_projects():
    """Load processed projects from file."""
    processed = set()
    try:
        with open(PROCESSED_PROJECTS_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            next(reader, None)  # Skip header
            for row in reader:
                processed.add(row[0])
    except FileNotFoundError:
        logging.warning(f"File '{PROCESSED_PROJECTS_FILE}' not found. Don't worry, I'll create it.")
    except Exception as e:
        logging.error(f"Error reading from file '{PROCESSED_PROJECTS_FILE}': {e}")
    return processed

def load_regex_patterns(file_path):
    """Load regex patterns from file."""
    patterns = []
    try:
        with open(file_path, mode='r', newline='') as file:
            reader = csv.DictReader(file, delimiter=',')
            for row in reader:
                patterns.append((row['Rule Name'], row['Regular Expression']))
    except FileNotFoundError:
        logging.error(f"File '{file_path}' does not exist.")
    except Exception as e:
        logging.error(f"Error loading regex patterns from '{file_path}': {e}")
    return patterns

PROCESSED_PROJECTS = load_processed_projects()
REGEX_PATTERNS = load_regex_patterns(os.path.join(os.getcwd(), REGEX_PATTERNS_FILE))

############################
# API Interaction Functions
############################

def process_attachments(issue_key):
    """Fetch and process attachments from a Jira issue."""
    url = f"{CONFIG['base_url']}/rest/api/3/issue/{issue_key}"
    try:
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        response.raise_for_status()
        issue_details = response.json()
        attachments = issue_details['fields'].get('attachment', [])
        for attachment in attachments:
            if attachment['filename'].endswith(('csv', 'txt', 'json', 'yaml', 'yml', 'md', 'conf', 'ini', 'sh', 'bat', 'ps1', 'log')):
                download_url = attachment['content']
                try:
                    file_response = requests.get(download_url, auth=AUTH, headers=HEADERS)
                    file_response.raise_for_status()
                    file_content = file_response.text
                    check_patterns(file_content, issue_key, 'attachment', f"{CONFIG['base_url']}/browse/{issue_key}")
                except requests.exceptions.RequestException as e:
                    logging.error(f"Failed to download attachment {attachment['filename']} from issue {issue_key}: {e}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to retrieve issue details for {issue_key}: {e}")
 
def process_comments(issue_key):
    """Fetch and process all comments for a given issue."""
    comments_response = requests.get(f"{CONFIG['base_url']}/rest/api/3/issue/{issue_key}/comment", auth=AUTH, headers=HEADERS)
    comments = comments_response.json()
    for comment in comments.get('comments', []):
        comment_content = comment.get('body', {})
        check_patterns(extract_text(comment_content), issue_key, "comment", f"{CONFIG['base_url']}/browse/{issue_key}")

def process_descriptions(issue_key, description):
    """Extract and check patterns in the description based on environment."""
    if description:
        check_patterns(extract_text(description), issue_key, "description", f"{CONFIG['base_url']}/browse/{issue_key}")


def process_history(issue_key):
    """Process changelog history for descriptions of a given issue."""
    url = f"{CONFIG['base_url']}/rest/api/3/issue/{issue_key}/changelog"

    response = requests.get(url, auth=AUTH, headers=HEADERS)
    if response.status_code == 200:
        changes = response.json()
        for history_item in changes['values']:
            for item in history_item['items']:
                if item['field'] == 'description':
                    old_description = item.get('fromString', '')
                    check_patterns(old_description, issue_key, "description history", f"{CONFIG['base_url']}/browse/{issue_key}")
    else:
        logging.error(f"Failed to retrieve changelog: {response.status_code}")
        logging.error(response.text)

##############################
# Project Management Functions
##############################

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

###########################
# Core Processing Functions
###########################

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

def process_issues(project_key):
    """Process all issues within a project by extracting necessary information and handling them."""
    start_at = 0
    max_results = 50
    issues_found = True
    while issues_found:
        issues_response = requests.get(f"{CONFIG['base_url']}/rest/api/3/search?jql=project=\'{project_key}\'&startAt={start_at}&maxResults={max_results}", auth=AUTH, headers=HEADERS)
        issues = issues_response.json()
        issues_found = 'issues' in issues and len(issues['issues']) > 0
        
        for issue in issues['issues']:
            issue_key = issue['key']
            logging.info(f"Processing issue {issue_key} in project {project_key}")
            
            description = issue['fields'].get('description', '')
            process_descriptions(issue_key, description)
            process_comments(issue_key)
            process_attachments(issue_key)
            process_history(issue_key)

        start_at += max_results

def process_projects(thread_count, specific_project_key=None):
    start_time = time.time()
    project_queue = Queue()

    if specific_project_key:
        # If a specific project key is provided, enqueue only this project
        project_queue.put(specific_project_key)
    else:
        # Default behavior: scan all projects
        start_at = 0
        max_results = 50
        more_projects = True
        while more_projects:
            projects_response = requests.get(f"{CONFIG['base_url']}/rest/api/3/project?startAt={start_at}&maxResults={max_results}",
                                             auth=AUTH, headers=HEADERS)
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

    end_time = time.time()  # End timing here
    total_time = end_time - start_time  # Calculate the total time taken
    logging.info(f"Total time taken to process: {total_time:.3f} seconds")  # Log the total time taken

if __name__ == '__main__':
    thread_count = 50
    # Optional: specify a project key to scan only that project
    specific_project_key = 'ITSAMPLE'  # Set this to None to scan all projects
    process_projects(thread_count, specific_project_key)
    #process_projects(thread_count) # To scan all projects
