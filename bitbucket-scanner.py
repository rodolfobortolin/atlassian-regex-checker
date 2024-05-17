import os
import csv
import regex as re
import logging
import subprocess
from threading import Thread
from queue import Queue
from requests.auth import HTTPBasicAuth
import requests
import shutil
import time

########################
# Configurations
########################

CONFIG = {
    'username': '',
    'token': '',
    'base_url': "https://api.bitbucket.org/2.0",
    'workspace': '',
}

password_file_extensions = [
    # Text and log files
    '.txt', '.md', '.log', 

    # Data and configuration files
    '.csv', '.json', '.xml', '.yaml', '.yml', 
    '.ini', '.conf', '.env', '.properties', '.vm', '.db',

    # Source code files
    '.c', '.cpp', '.h', '.hpp', '.java', 
    '.py', '.rb', '.go', '.rs', '.swift', 
    '.kt', '.kts', '.lua', '.pl', '.php', 
    '.asp', '.aspx', '.cs', '.vb', 
    '.js', '.ts', '.jsx', '.tsx', 
    '.sh', '.bash', '.zsh', '.bat', '.ps1', 
    '.r', '.m', '.mat', 
    '.scala', '.groovy', '.erl', '.hrl', 
    '.ex', '.exs', '.lisp', '.cl', 
    '.el', '.scm', '.ss', '.rkt', 
    '.clj', '.cljs', '.cljc', '.edn', 
    '.ml', '.mli', '.sml', '.sig', '.fun', 

    # Markup and templating files
    '.html', '.htm', '.xhtml', '.vue', '.asp', '.php', '.phtml', '.pl', '.psgi', '.mustache', '.jinja', '.ejs', '.hbs', 

    # Other configuration files
    '.jsonnet', '.jsonc', '.toml', '.cfg', 
    '.editorconfig', '.gitconfig', 
    '.gitattributes', '.gitignore', '.dockerignore', 
    '.npmignore', '.eslintignore', '.prettierignore', 
    '.babelrc', '.eslintrc', '.prettierrc',

    # Infrastructure and deployment files
    '.tf', '.tfvars', '.terraformrc', '.tfstate', 
    '.k8s', '.kubeconfig', '.helm', '.tiller', 
    '.kustomize', '.hcl', 
    '.envrc', '.vault', '.credential', '.credentials', 
    '.pem', '.crt', '.cer', '.p12', '.pfx', '.key'
]


REGEX_PATTERNS_FILE = 'regex_patterns.csv'
FALSE_POSITIVES = 'bitbucket_false_positive.txt'
FOUND_ISSUES_FILE = 'bitbucket_found_issues.csv'
RUNNING_REPOSITORIES_FILE = 'bitbucket_running_repositories.txt'
LOG_FILE = 'bitbucket_application.log'
PROCESSED_REPOSITORIES_FILE = 'bitbucket_processed_repositories.csv'
SKIPPED_EXTENSIONS_FILE = 'skipped_extensions.txt'

AUTH = HTTPBasicAuth(CONFIG['username'], CONFIG['token'])
HEADERS = {"Accept": "application/json"}

# Track skipped extensions
skipped_extensions = set()

########################
# Logging Setup
########################

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
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

def load_repository_keys(file_path='repositories.txt'):
    """Load repository keys from a specified file."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                return [line.strip() for line in file if line.strip()]
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to read repository keys from {file_path}: {e}")
        return None

def append_to_csv(file_name, row):
    try:
        with open(file_name, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(row)
    except Exception as e:
        logging.error(f"Failed to write to file '{file_name}': {e}")

def check_patterns(text, file_path, url):
    false_positives = load_false_positives()
    if file_path in false_positives:
        logging.info(f"File {file_path} is marked as a false positive and will not be processed.")
        return

    if isinstance(text, bytes):
        if text:
            try:
                text = text.decode('utf-8')
                for rule_name, pattern in REGEX_PATTERNS:
                    if re.search(pattern, text):
                        separator = "*" * 50
                        append_to_csv(FOUND_ISSUES_FILE, [file_path, rule_name, url])
                        logging.warning(separator)
                        logging.warning(f"!!! ALERT: Found {rule_name} pattern in file {file_path} !!!")
                        logging.warning(separator)
            except Exception as e:
                logging.warning(f"Failed to check file {file_path}: {e}")

if not os.path.exists(PROCESSED_REPOSITORIES_FILE):
    with open(PROCESSED_REPOSITORIES_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Repository'])

############################
# Data Loading Functions
############################

def delete_file(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Deleted file: {file_path}")
    except Exception as e:
        logging.error(f"Failed to delete file {file_path}: {e}")

def load_false_positives(file_path='false_positive.txt'):
    false_positives = set()
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

def load_processed_repositories():
    processed = set()
    try:
        with open(PROCESSED_REPOSITORIES_FILE, mode='r', newline='') as file:
            reader = csv.reader(file)
            next(reader, None)
            for row in reader:
                processed.add(row[0])
    except FileNotFoundError:
        logging.warning(f"File '{PROCESSED_REPOSITORIES_FILE}' not found. Don't worry, I'll create it.")
    except Exception as e:
        logging.error(f"Error reading from file '{PROCESSED_REPOSITORIES_FILE}': {e}")
    return processed

def load_regex_patterns(file_path):
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

PROCESSED_REPOSITORIES = load_processed_repositories()
REGEX_PATTERNS = load_regex_patterns(os.path.join(os.getcwd(), REGEX_PATTERNS_FILE))

##############################
# API Interaction Functions
##############################

def fetch_all_repositories():
    """Fetch all repositories from Bitbucket."""
    url = f"{CONFIG['base_url']}/repositories/{CONFIG['workspace']}"
    try:
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        response.raise_for_status()
        repositories = response.json()
        return [repo['slug'] for repo in repositories['values']]
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch repositories from Bitbucket: {e}")
        return []

def run_command(command, cwd=None):
    """Execute a system command with optional working directory."""
    logging.info(f"Executing: {command}")
    try:
        result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.stdout:
            logging.debug(result.stdout)
        if result.stderr:
            logging.error(result.stderr)
    except Exception as e:
        logging.exception("Failed to execute command")

def clone_and_process_repo(repo_slug):
    """Clone the repository and process its files."""
    repo_url = f"https://{CONFIG['username']}:{CONFIG['token']}@bitbucket.org/{CONFIG['workspace']}/{repo_slug}.git"
    repo_folder = os.path.join('repositories', repo_slug)

    if not os.path.exists(repo_folder):
        logging.info(f"Cloning repository: {repo_slug}")
        clone_command = f"git clone {repo_url} \"{repo_folder}\""
        run_command(clone_command)
    else:
        logging.info(f"Repository {repo_slug} already exists, pulling latest changes.")
        pull_command = "git pull"
        run_command(pull_command, cwd=repo_folder)

    process_files_recursive_local(repo_folder)
    time.sleep(1)  # Ensure all file handles are released
    delete_repository_folder(repo_folder)

def process_files_recursive_local(repo_folder, path=""):
    """Recursively fetch and process files from a local repository."""
    full_path = os.path.join(repo_folder, path)
    try:
        for root, dirs, files in os.walk(full_path):
            if '.git' in dirs:
                dirs.remove('.git')  # Don't visit .git directories
            for file in files:
                file_path = os.path.relpath(os.path.join(root, file), repo_folder)
                if file_path.lower().endswith(tuple(password_file_extensions)):
                    logging.debug(f"Processing file: {file_path}")
                    with open(os.path.join(root, file), 'rb') as f:
                        file_content = f.read()
                        if file_content:
                            try:
                                check_patterns(file_content, file_path, f"file://{os.path.join(root, file)}")
                            except Exception as e:
                                logging.error(f"Failed to check patterns for file {file_path}: {e}")
                else: 
                    logging.debug(f"Skipping file: {file_path}")
                    skipped_extensions.add(os.path.splitext(file_path)[1].lower())
                
    except Exception as e:
        logging.error(f"Failed to process files in repository at path {full_path}: {e}")

def delete_repository_folder(repo_folder):
    """Delete the local repository folder."""
    try:
        if os.path.exists(repo_folder):
            shutil.rmtree(repo_folder, ignore_errors=True)
            logging.debug(f"Deleted repository folder: {repo_folder}")
    except Exception as e:
        logging.error(f"Failed to delete repository folder {repo_folder}: {e}")

##############################
# Repository Management Functions
##############################

def add_to_running_repositories(repo_slug):
    """Add a repository slug to the running repositories file."""
    with open(RUNNING_REPOSITORIES_FILE, 'a') as file:
        file.write(repo_slug + '\n')

def remove_from_running_repositories(repo_slug):
    """Remove a repository slug from the running repositories file."""
    with open(RUNNING_REPOSITORIES_FILE, 'r') as file:
        lines = file.readlines()
    with open(RUNNING_REPOSITORIES_FILE, 'w') as file:
        for line in lines:
            if line.strip() != repo_slug:
                file.write(line)

def is_repository_running(repo_slug):
    """Check if a repository slug is in the running repositories file."""
    try:
        with open(RUNNING_REPOSITORIES_FILE, 'r') as file:
            for line in file:
                if line.strip() == repo_slug:
                    return True
    except FileNotFoundError:
        return False
    return False

###########################
# Core Processing Functions
###########################

def worker(repository_queue):
    while not repository_queue.empty():
        try:
            repo_slug = repository_queue.get()
            logging.info(f"Processing repository: {repo_slug}")
            if repo_slug not in PROCESSED_REPOSITORIES and not is_repository_running(repo_slug):
                add_to_running_repositories(repo_slug)
                clone_and_process_repo(repo_slug)
                append_to_csv(PROCESSED_REPOSITORIES_FILE, [repo_slug])
                PROCESSED_REPOSITORIES.add(repo_slug)
                remove_from_running_repositories(repo_slug)
        except Exception as e:
            logging.error(f"Error processing repository {repo_slug}: {e}")
        finally:
            repository_queue.task_done()

def process_repositories(thread_count, repo_slugs=None):
    """Process a list of repositories in parallel using threading."""
    repository_queue = Queue()

    if repo_slugs is None or repo_slugs == []:
        repo_slugs = fetch_all_repositories()

    for repo_slug in repo_slugs:
        repository_queue.put(repo_slug)

    threads = []
    for _ in range(thread_count):
        thread = Thread(target=worker, args=(repository_queue,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

# Example usage
if __name__ == '__main__':
    start_time = time.time()

    delete_file(LOG_FILE)
    delete_file(PROCESSED_REPOSITORIES_FILE)
    delete_file(RUNNING_REPOSITORIES_FILE)

    repo_slugs = load_repository_keys()
    thread_count = 1
    process_repositories(thread_count, repo_slugs)

    # Write skipped extensions to file
    with open(SKIPPED_EXTENSIONS_FILE, 'w') as f:
        for ext in sorted(skipped_extensions):
            f.write(ext + '\n')

    end_time = time.time()
    logging.info(f"Total time taken to process: {format_time(end_time - start_time)}")

    delete_file(SKIPPED_EXTENSIONS_FILE)
    delete_file(PROCESSED_REPOSITORIES_FILE)
    delete_file(RUNNING_REPOSITORIES_FILE)
