## Jira Issue Processing Script Usage Guide

This guide explains how to use a Python script designed to interface with a Jira  to process issues across projects. It identifies certain patterns within issue descriptions and comments and logs these findings.

### Saving Processed Projects
The script maintains a record of processed projects in a file named `processed_projects.csv`. If the script is interrupted, it won't reprocess the projects listed in this file when restarted.

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

### Defining REGEX_PATTERNS
Define your own regex patterns to search within issue descriptions and comments. Add them to the `REGEX_PATTERNS` list:

```python
REGEX_PATTERNS = [
    "sk-[a-zA-Z0-9]{40}", #example of regex that detects OpenAI API Keys
    "regex-2",
    "regex-3",
    ]  # List of regex patterns
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
