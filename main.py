import os
import csv
import regex as re  # Import the regex module
import logging
import requests
import sys
from requests.auth import HTTPBasicAuth

config = {
    'email': '<email>', 
    'token' : "",  
    'base_url' : "https://<domain>.atlassian.net",
    'api_version': 3
}

env = 'cloud'

regex_patterns_file = 'regex_patterns.csv'


# Setup basic configuration for logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

# Constants
AUTH = HTTPBasicAuth(config['email'], config['token'])
HEADERS = {"Accept": "application/json"}

def load_regex_patterns(file_path):
    patterns = []
    if os.path.exists(file_path):
        with open(file_path, mode='r', newline='') as file:
            reader = csv.DictReader(file, delimiter=',')  # Specify the delimiter
            for row in reader:
                # Corrected accessing dictionary key
                patterns.append(row['Regular Expression'])
    else:
        logging.error(f"File '{file_path}' does not exist.")
    return patterns

REGEX_PATTERNS = load_regex_patterns(os.path.join(os.getcwd(), regex_patterns_file))
# CSV files for saving data
PROCESSED_PROJECTS_FILE = 'processed_projects.csv'
FOUND_ISSUES_FILE = 'found_issues.csv'

# Check if the processed projects file exists, if not create it
if not os.path.exists(PROCESSED_PROJECTS_FILE):
    with open(PROCESSED_PROJECTS_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Project Key'])

def append_to_csv(file_name, row):
    with open(file_name, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row)

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

def check_patterns(text, issue_key, type, url):
    if text is not None and text != "":
        for pattern in REGEX_PATTERNS:
            if re.search(pattern, text):
                append_to_csv(FOUND_ISSUES_FILE, [issue_key, type, url])
                logging.info(f"Found pattern '{pattern}' in issue {issue_key}")
                
def process_projects(project_key=None):
    start_at = 0
    max_results = 50
    if project_key:
        process_issues(project_key)
        append_to_csv(PROCESSED_PROJECTS_FILE, [project_key])
    else:
        more_projects = True
        while more_projects:
            projects_response = requests.get(f"{config['base_url']}/rest/api/{config['api_version']}/project?startAt={start_at}&maxResults={max_results}", auth=AUTH, headers=HEADERS)
            projects = projects_response.json()
            more_projects = len(projects) == max_results
            
            for project in projects:
                project_key = project['key']
                with open(PROCESSED_PROJECTS_FILE, mode='r') as file:
                    processed_projects = [row[0] for row in csv.reader(file)]
                if project_key in processed_projects:
                    logging.info(f"Skipping already processed project: {project_key}")
                    continue
                
                process_issues(project_key)
                append_to_csv(PROCESSED_PROJECTS_FILE, [project_key])
            
            start_at += max_results

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
                logging.info("Description...")
                if env == 'cloud':
                    check_patterns(extract_text(description), issue_key, "description", f"{config['base_url']}/browse/{issue_key}")
                else:
                    check_patterns(description, issue_key, "description", f"{config['base_url']}/browse/{issue_key}")
            
            comments_response = requests.get(f"{config['base_url']}/rest/api/{config['api_version']}/issue/{issue_key}/comment", auth=AUTH, headers=HEADERS)
            comments = comments_response.json()
            
            logging.info(f"{comments['total']} comment(s)...")
            
            for comment in comments.get('comments', []):
                comment_content = comment.get('body', {})
                if env == 'cloud':
                    check_patterns(extract_text(comment_content), issue_key, "comment", f"{config['base_url']}/browse/{issue_key}")
                else:
                    check_patterns(comment_content, issue_key, "comment", f"{config['base_url']}/browse/{issue_key}")
            logging.info("History...\n")
            check_description_history(issue_key)

        start_at += max_results
        
if __name__ == '__main__':
    project_key = "ITSAMPLE"  
    #process_projects(project_key)
    process_projects()
