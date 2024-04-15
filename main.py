import os
import csv
import re
import logging
import requests
from requests.auth import HTTPBasicAuth

config = {
    'email': 'admin', 
    'token' : "admin",  
    'base_url' : "http://localhost:8080",
    'api_version': 2
}

env = 'server'


# Setup basic configuration for logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

# Constants
BASE_URL = f"{config['base_url']}"
AUTH = HTTPBasicAuth(config['email'], config['token'])
HEADERS = {"Accept": "application/json"}
REGEX_PATTERNS = ["sk-[a-zA-Z0-9]{40}"]  # List of regex patterns

# CSV files for saving data
PROCESSED_PROJECTS_FILE = 'processed_projects.csv'
FOUND_ISSUES_FILE = 'found_issues.csv'

# Check if the processed projects file exists, if not create it
if not os.path.exists(PROCESSED_PROJECTS_FILE):
    with open(PROCESSED_PROJECTS_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Project Key'])

# Helper function to write to CSV
def append_to_csv(file_name, row):
    with open(file_name, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row)

def extract_text_from_node(node):
    """
    Recursively extract text from a node in the Atlassian document format.
    """
    text = ''
    
    # Check if the node itself contains a 'text' field
    if 'text' in node:
        return node['text']
    
    # If the node contains 'content', recursively extract text from its children
    if 'content' in node:
        for child in node['content']:
            text += extract_text_from_node(child)
    
    return text

def extract_text(content):
    """
    Extract and concatenate text from the 'content' field of the Atlassian document format.
    """
    full_text = ''
    for node in content['content']:
        full_text += extract_text_from_node(node)
    return full_text

def check_patterns(text, issue_key, type, url):
    for pattern in REGEX_PATTERNS:
        if re.search(pattern, text):
            append_to_csv(FOUND_ISSUES_FILE, [issue_key, type, url])
            logging.info(f"Found pattern '{pattern}' in issue {issue_key}")

# Function to process each project with pagination
def process_projects():
    start_at = 0
    max_results = 50
    more_projects = True

    while more_projects:
        projects_response = requests.get(f"{BASE_URL}/rest/api/{config['api_version']}/project?startAt={start_at}&maxResults={max_results}", auth=AUTH, headers=HEADERS)
        projects = projects_response.json()
        more_projects = len(projects) == max_results  # Check if we potentially have more projects
        
        for project in projects:
            project_key = project['key']
            # Check if the project has been processed
            with open(PROCESSED_PROJECTS_FILE, mode='r') as file:
                processed_projects = [row[0] for row in csv.reader(file)]
            if project_key in processed_projects:
                logging.info(f"Skipping already processed project: {project_key}")
                continue
            
            process_issues(project_key)
            # Mark project as processed
            append_to_csv(PROCESSED_PROJECTS_FILE, [project_key])
        
        start_at += max_results  # Update start_at for next batch of projects
        
# Function to fetch and process issues for a given project
def process_issues(project_key):
    start_at = 0
    max_results = 50
    issues_found = True

    while issues_found:
        issues_response = requests.get(f"{BASE_URL}/rest/api/{config['api_version']}/search?jql=project=\'{project_key}\'&startAt={start_at}&maxResults={max_results}", auth=AUTH, headers=HEADERS)
        issues = issues_response.json()
        issues_found = 'issues' in issues and len(issues['issues']) > 0
        
        for issue in issues['issues']:
            issue_key = issue['key']
            logging.info(f"Processing issue {issue_key} in project {project_key}")
            
            # Safely get the description
            description = issue['fields'].get('description', '')
            
            # Check if the description is empty
            if not description:
                logging.info(f"Issue {issue_key} has an empty description.")
            else:
                # Proceed with pattern checks if description is not empty
                if env == 'cloud':
                    check_patterns(extract_text(description), issue_key, "description", f"{BASE_URL}/browse/{issue_key}")
                else:
                    check_patterns(description, issue_key, "description", f"{BASE_URL}/browse/{issue_key}")

            # Fetch and process comments
            comments_response = requests.get(f"{BASE_URL}/rest/api/{config['api_version']}/issue/{issue_key}/comment", auth=AUTH, headers=HEADERS)
            comments = comments_response.json()
            
            for comment in comments.get('comments', []):  # Handle cases where 'comments' may be missing
                comment_content = comment.get('body', {})
                if env == 'cloud':
                    check_patterns(extract_text(comment_content), issue_key, "comment", f"{BASE_URL}/browse/{issue_key}")
                else:
                    check_patterns(comment_content, issue_key, "comment", comments_response.url)

        start_at += max_results  # Prepare the next page of results
        
if __name__ == '__main__':
    process_projects()
