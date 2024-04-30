import os
import csv
import regex as re
import logging
import requests
import time  
from http.client import IncompleteRead
from requests.auth import HTTPBasicAuth
from threading import Thread
from queue import Queue
from requests.exceptions import ChunkedEncodingError
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ProtocolError
from requests.packages.urllib3.util.retry import Retry

########################
# Configurations
########################

CONFIG = {
    'email': '<email>', 
    'token' : "",  
    'base_url' : "https://<domain>.atlassian.net",
}

REGEX_PATTERNS_FILE = 'regex_patterns.csv'
FALSE_POSITIVES = 'false_positive.txt'
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

def format_time(duration):
    hours, remainder = divmod(duration, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)} hours, {int(minutes)} minutes, and {seconds:.3f} seconds"
    elif minutes > 0:
        return f"{int(minutes)} minutes and {seconds:.3f} seconds"
    else:
        return f"{seconds:.3f} seconds"

def load_project_keys(file_path='projects.txt'):
    """Load project keys from a specified file."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                return [line.strip() for line in file if line.strip()]
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to read project keys from {file_path}: {e}")
        return None

def load_project_keys(file_path='projects.txt'):
    """Load project keys from a specified file."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                return [line.strip() for line in file if line.strip()]
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to read project keys from {file_path}: {e}")
        return None

def download_attachment(download_url):
    session = setup_retry_session()
    attempt = 0
    max_attempts = 5
    while attempt < max_attempts:
        try:
            response = session.get(download_url, auth=AUTH, headers=HEADERS, timeout=120)
            response.raise_for_status()  # Raises a HTTPError for bad responses
            content_type = response.headers.get('Content-Type')
        
            # If the content type is text, decode it, otherwise return the bytes
            if 'text' in content_type:
                return response.text  # Decodes using response encoding
            else:
                return response.content  # Return bytes for binary content

        except (requests.exceptions.RequestException, ProtocolError, IncompleteRead, ChunkedEncodingError) as e:
            logging.warning(f"Attempt {attempt + 1} failed with error: {e}")
            attempt += 1
            time.sleep(2)  # Wait 2 seconds before retrying
        except Exception as e:
            logging.error(f"Failed to download attachment from {download_url} after {max_attempts} attempts: {e}")
            return None
    return None

def setup_retry_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504), allowed_exceptions=(ProtocolError, IncompleteRead)):
    """Set up a requests session with retry mechanism including ProtocolError."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(['HEAD', 'GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'TRACE']),  # Specify allowed HTTP methods for retries
        raise_on_status=False,
        raise_on_redirect=True,
        history=None,
        respect_retry_after_header=True,
        remove_headers_on_redirect=[],
        other=allowed_exceptions
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

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
    false_positives = load_false_positives()  # Load false positives at the start or periodically refresh if needed
    if issue_key in false_positives:
        logging.info(f"Issue {issue_key} is marked as a false positive and will not be processed.")
        return
    
    if isinstance(text, bytes):
        text = text.decode('utf-8')  # Ensure text is in string format
    if text:
        for rule_name, pattern in REGEX_PATTERNS:
            if re.search(pattern, text):
                separator = "*" * 50  # Creates a line of asterisks
                append_to_csv(FOUND_ISSUES_FILE, [issue_key, rule_name, type, url])
                logging.warning(separator)
                logging.warning(f"!!! ALERT: Found {rule_name} pattern in issue {issue_key} !!!")
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

def delete_file(file_path):
    """Delete a file if it exists."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Deleted file: {file_path}")
    except Exception as e:
        logging.error(f"Failed to delete file {file_path}: {e}")


def load_false_positives(file_path='false_positive.txt'):
    false_positives = set()
    # Ensure the file exists, create it if it doesn't
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            logging.info(f"{file_path} not found. Creating new file.")
    try:
        with open(file_path, 'r') as file:
            for line in file:
                false_positives.add(line.strip())
    except Exception as e:
        logging.error(f"Failed to read false positives from {file_path}: {e}")
    return false_positives

def load_project_keys(file_path='projects.txt'):
    try:
        with open(file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return []
    except Exception as e:
        logging.error(f"Failed to read project keys from {file_path}: {e}")
        return []

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

def fetch_all_projects():
    """Fetch all projects from JIRA using REST API."""
    url = f"{CONFIG['base_url']}/rest/api/3/project"
    try:
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        response.raise_for_status()
        projects = response.json()
        return [project['key'] for project in projects]
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch projects from JIRA: {e}")
        return []

def process_attachments(issue_key):
    """Fetch and process attachments from a Jira issue."""
    url = f"{CONFIG['base_url']}/rest/api/3/issue/{issue_key}"
    # Modify headers to disable automatic gzip compression
    custom_headers = {**HEADERS, 'Accept-Encoding': 'identity', 'Accept-Encoding': 'gzip, deflate', 'Connection': 'keep-alive'}
    response = None  # Initialize response outside try to make it accessible in except

    try:
        response = requests.get(url, auth=AUTH, headers=custom_headers)
        response.raise_for_status()  # Ensure the request was successful
        issue_details = response.json()
        attachments = issue_details['fields'].get('attachment', [])

        for attachment in attachments:
            if attachment['filename'].endswith(('csv', 'txt', 'json', 'yaml', 'yml', 'md', 'conf', 'ini', 'sh', 'bat', 'ps1', 'log')):
                download_url = attachment['content']
                file_content = download_attachment(download_url)
                if file_content:
                    try:
                        check_patterns(file_content, issue_key, 'attachment', f"{CONFIG['base_url']}/browse/{issue_key}")
                    except Exception as e:
                        logging.error(f"Failed to check patterns for attachment in issue {issue_key}: {e}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to retrieve issue details for {issue_key}: {e}")
        if response:
            logging.error(f"Response status code: {response.status_code}")
            logging.error(f"Response content: {response.content[:500]}")  # Log part of the content to inspect it
        else:
            logging.error("No response received due to network or connection error.")

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
        try:
            project_key = project_queue.get()
            logging.info(f"Processing project_key: {project_key}")
            if project_key not in PROCESSED_PROJECTS and not is_project_running(project_key):
                add_to_running_projects(project_key)
                process_issues(project_key)
                append_to_csv(PROCESSED_PROJECTS_FILE, [project_key])
                PROCESSED_PROJECTS.add(project_key)
                remove_from_running_projects(project_key)
        except Exception as e:
            logging.error(f"Error processing project {project_key}: {e}")
        finally:
            project_queue.task_done()
            
def process_issues(project_key):
    start_at = 0
    max_results = 50
    total_issues_count = 0  # This will store the total count of issues for logging
    
    jql_query = f"project=\'{project_key}\'"
    
    issue_counter = 0
    # First, get the total count of issues to be processed
    count_url = f"{CONFIG['base_url']}/rest/api/3/search?jql={jql_query}&maxResults=0"
    count_response = requests.get(count_url, auth=AUTH, headers=HEADERS)
    total_issues = count_response.json().get('total', 0)

    # Initial fetch to determine the total number of issues to process
    try:
        issues_url = f"{CONFIG['base_url']}/rest/api/3/search?jql={jql_query}&startAt={start_at}&maxResults={max_results}"
        initial_response = requests.get(issues_url, auth=AUTH, headers=HEADERS)
        initial_response.raise_for_status()
        total_issues_count = initial_response.json().get('total', 0)
        logging.info(f"Total issues to be processed for project {project_key}: {total_issues_count}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch initial issue data for project {project_key}: {e}")
        return  # Exit the function if initial fetch fails

    # Process all issues
    while True:
        try:
            issues_url = f"{CONFIG['base_url']}/rest/api/3/search?jql=project=\'{project_key}\'&startAt={start_at}&maxResults={max_results}"
            issues_response = requests.get(issues_url, auth=AUTH, headers=HEADERS)
            issues_response.raise_for_status()
            issues_data = issues_response.json()
            issues_list = issues_data.get('issues', [])
            if not issues_list:
                break  # Exit the loop if no more issues are found

            for issue in issues_list:
                issue_key = issue['key']
                issue_counter += 1
                logging.info(f"Processing issue {issue_key} ({issue_counter} of {total_issues})")
                
                try:
                    description = issue['fields'].get('description', {})
                    process_descriptions(issue_key, description)
                except Exception as e:
                    logging.error(f"Failed to process description for issue {issue_key}: {e}")

                try:
                    process_comments(issue_key)
                except Exception as e:
                    logging.error(f"Failed to process comments for issue {issue_key}: {e}")

                try:
                    process_attachments(issue_key)
                except Exception as e:
                    logging.error(f"Failed to process attachments for issue {issue_key}: {e}")

                try:
                    process_history(issue_key)
                except Exception as e:
                    logging.error(f"Failed to process history for issue {issue_key}: {e}")

            start_at += len(issues_list)  # Prepare for the next batch of issues

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching or processing issues for project {project_key}: {e}")
            # Consider whether to break or continue here depending on how critical the failure is

    logging.info(f"Finished processing all issues for project {project_key}")
    
    
def process_projects(thread_count, project_keys=None):
    """Process a list of projects in parallel using threading."""

    project_queue = Queue()

    # Determine which projects to process
    if project_keys is None or project_keys == []:
        project_keys = fetch_all_projects()

    # Enqueue specified or all project keys
    for project_key in project_keys:
        project_queue.put(project_key)

    threads = []
    for _ in range(thread_count):
        thread = Thread(target=worker, args=(project_queue,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

# Example usage
if __name__ == '__main__':
    
    start_time = time.time()
    
    delete_file(LOG_FILE)
    delete_file(PROCESSED_PROJECTS_FILE)
    delete_file(RUNNING_PROJECTS_FILE)
    
    project_keys = load_project_keys()  
    thread_count = 10  # Adjust thread count as needed
    process_projects(thread_count, project_keys)
    
    delete_file(PROCESSED_PROJECTS_FILE)
    delete_file(RUNNING_PROJECTS_FILE)
    
    end_time = time.time()
    logging.info(f"Total time taken to process: {format_time(end_time - start_time)}")

