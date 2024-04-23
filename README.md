## Jira Issue Processing Script Usage Guide

This guide explains how to use a Python script designed to interface with a Jira  to process issues across projects. It identifies certain patterns within issue descriptions and comments and logs these findings.

### Saving Processed Projects
The script maintains a record of processed projects in a file named `processed_projects.csv`. If the script is interrupted, it won't reprocess the projects listed in this file when restarted.

### Install regex Python module
```bash
pip install regex
```

### Configuration
You'll need to provide the following configurations in the `config` dictionary within the script:

```python
config = {
    'email': 'your-email@example.com',  # Replace with your Jira email
    'token': 'your-api-token-or-passoword',  # Replace with your Jira API token (if Cloud) or your user Password (if Data Center)
    'base_url': 'http://your-jira-instance:port',  # Replace with your Jira instance URL
    'api_version': 2  # API version of your Jira instance (leave 2 if server, 3 if cloud
}

env = 'server' # change to cloud if the script will run in Jira Cloud

```

## Managing Active Projects

The script includes a mechanism to manage currently running projects using a file named running_projects.txt:

- Addition: When a project starts, its key is added to running_projects.txt.
- Removal: Once the project is no longer active, its key is removed from the file.
- Check: Before processing, the script checks if a project is listed as active to avoid reprocessing.

## Saving Processed Projects
The script maintains a record of processed projects in a file named processed_projects.csv. Projects are added to this file after they have been processed. If the script is interrupted, it won't reprocess the projects listed in this file when restarted.

### Defining REGEX_PATTERNS
Define your own regex patterns to search within issue descriptions and comments. Add them to the `regex_patterns.csv`:

```csv
Rule Name,Regular Expression
AWS_CLIENT_ID,A(?:BIA|CCA|GPA|IDA|IPA|KIA|NPA|NVA|PKA|ROA|SCA|SIA|3T[A-Z0-9])[A-Z0-9]{16}
AWS_MWS_KEY,amzn\.mws\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}
AWS_SECRET_ACCESS_KEY,"(?i)aws.{0,20}?(?-i)[^0-9a-zA-Z/+!@#$%^&*]([0-9a-zA-Z/+]{40})(?=[^0-9a-zA-Z/+!@#$%^&*]|$)"
RSA_PRIVATE_KEY,-----BEGIN RSA PRIVATE KEY-----
SSH_PRIVATE_KEY,-----BEGIN OPENSSH PRIVATE KEY-----
```

### found_issues.csv Contents
The script will record the findings in `found_issues.csv`, with each row containing:

- `ISSUE_KEY`: The key of the Jira issue
- `TYPE`: Where the pattern was found (`"description"` or `"comment"`)
- `URL`: The URL to the Jira issue

Example CSV output:

```csv
ISSUE_KEY, TYPE, URL
EXAMPLE-123, description, http://your-jira-instance:port/browse/EXAMPLE-123
```

### Execution
Run the script from the command line as follows (after all configurations are set within the script):

```shell
python script_name.py  # Replace with the actual file name of the script
```
