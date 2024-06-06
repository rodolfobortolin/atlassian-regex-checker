
# Repository Usage Guide

This repository contains various scripts to automate tasks related to Jira and Bitbucket. The current scripts include:

1. **Jira Scanner Script**: Identifies patterns in Jira issue descriptions and comments.
2. **Bitbucket Scanner Script**: Checks for regex patterns within Bitbucket repositories.

## Setup

### Install Required Python Modules
Install the necessary Python modules using pip:
```bash
pip install regex urllib3 requests
```

## Jira Scanner Script

### Overview
This script interfaces with a Jira instance to process issues across projects. It identifies specific patterns within issue descriptions, comments, and attachments and logs these findings.

### Configuration
Provide the following configurations in the `CONFIG` dictionary within the script:

```python
CONFIG = {
    'email': 'your-email@example.com',  # Replace with your Jira email
    'token': 'your-api-token-or-password',  # Replace with your Jira API token (Cloud) or password (Data Center)
    'base_url': 'https://<domain>.atlassian.net'  # Replace with your Jira instance URL
}
```

### Managing Active Projects
The script manages currently running projects using `jira_running_projects.txt`:
- **Addition**: Project key is added when a project starts.
- **Removal**: Project key is removed when the project ends.
- **Check**: Ensures a project is not reprocessed if already active.

### Saving Processed Projects
The script records processed projects in `jira_processed_projects.csv`. Projects listed here will not be reprocessed if the script restarts.

### Defining Regex Patterns
Add your regex patterns to `regex_patterns.csv`:

```csv
Rule Name,Regular Expression
AWS_CLIENT_ID,A(?:BIA|CCA|GPA|IDA|IPA|KIA|NPA|NVA|PKA|ROA|SCA|SIA|3T[A-Z0-9])[A-Z0-9]{16}
AWS_MWS_KEY,amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}
AWS_SECRET_ACCESS_KEY,"(?i)aws.{0,20}?(?-i)[^0-9a-zA-Z/+!@#$%^&*]([0-9a-zA-Z/+]{40})(?=[^0-9a-zA-Z/+!@#$%^&*]|$)"
RSA_PRIVATE_KEY,-----BEGIN RSA PRIVATE KEY-----
SSH_PRIVATE_KEY,-----BEGIN OPENSSH PRIVATE KEY-----
```

### Logging Findings
The script logs findings in `jira_found_issues.csv`, including:
- `ISSUE_KEY`: Jira issue key
- `TYPE`: Location of the pattern (`description`, `comment`, or `attachment`)
- `URL`: URL to the Jira issue

Example:
```csv
ISSUE_KEY, TYPE, URL
EXAMPLE-123, description, http://your-jira-instance:port/browse/EXAMPLE-123
```

### Execution
Run the script:
```shell
python jira-scanner.py  # Replace with the actual script name
```

## Bitbucket Scanner Script

### Overview
This script checks for specified regex patterns within Bitbucket repositories.

### Configuration
Provide the following configurations in the `CONFIG` dictionary within the script:

```python
CONFIG = {
    'username': 'your-username',  # Replace with your Bitbucket username
    'token': 'your-app-password',  # Replace with your Bitbucket app password
    'base_url': 'https://api.bitbucket.org/2.0',
    'workspace': 'your-workspace'  # Replace with your Bitbucket workspace ID
}
```

### Defining Regex Patterns
Add your regex patterns to `regex_patterns.csv`:

```csv
Rule Name,Regular Expression
AWS_CLIENT_ID,A(?:BIA|CCA|GPA|IDA|IPA|KIA|NPA|NVA|PKA|ROA|SCA|SIA|3T[A-Z0-9])[A-Z0-9]{16}
AWS_MWS_KEY,amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}
AWS_SECRET_ACCESS_KEY,"(?i)aws.{0,20}?(?-i)[^0-9a-zA-Z/+!@#$%^&*]([0-9a-zA-Z/+]{40})(?=[^0-9a-zA-Z/+!@#$%^&*]|$)"
RSA_PRIVATE_KEY,-----BEGIN RSA PRIVATE KEY-----
SSH_PRIVATE_KEY,-----BEGIN OPENSSH PRIVATE KEY-----
```

### Logging Findings
The script logs findings in `bitbucket_found_issues.csv`, including:
- `File Path`: Path of the file in the repository
- `Rule Name`: Name of the regex rule matched
- `URL`: URL to the file in the repository
- `Branch`: Branch in which the file was found

Example:
```csv
File Path, Rule Name, URL, Branch
example/path/file.txt, AWS_CLIENT_ID, https://bitbucket.org/your-workspace/repo-name/src/branch/path/to/file.txt, main
```

### Execution
Run the script:
```shell
python bitbucket-scanner.py  # Replace with the actual script name
```
