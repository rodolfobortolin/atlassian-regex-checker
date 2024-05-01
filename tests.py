import pytest
import requests
from unittest.mock import patch, mock_open, MagicMock
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from requests.packages.urllib3.util.retry import Retry

from main import CONFIG, process_comments, process_history, setup_retry_session, process_attachments, format_time, load_project_keys, download_attachment, setup_retry_session, extract_text_from_node, append_to_csv

AUTH = HTTPBasicAuth(CONFIG['email'], CONFIG['token'])

@pytest.mark.parametrize("duration, expected", [
    (3661, "1 hours, 1 minutes, and 1.000 seconds"),
    (61, "1 minutes and 1.000 seconds"),
    (59, "59.000 seconds")
])
def test_format_time(duration, expected):
    assert format_time(duration) == expected

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data="PROJECT1\nPROJECT2\n")
def test_load_project_keys(mock_file, mock_exists):
    mock_exists.return_value = True
    assert load_project_keys() == ['PROJECT1', 'PROJECT2']

@patch("requests.Session.get")
def test_download_attachment(mock_get):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {'Content-Type': 'text/plain'}
    mock_response.text = "Sample text"
    mock_get.return_value = mock_response
    assert download_attachment("http://example.com/sample.txt") == "Sample text"

@patch("requests.Session")
def test_setup_retry_session(mock_session):
    session = setup_retry_session()
    assert session != None

def test_extract_text_from_node():
    node = {'content': [{'text': 'Hello '}, {'content': [{'text': 'world'}]}]}
    assert extract_text_from_node(node) == 'Hello world'

@patch("builtins.open", new_callable=mock_open)
@patch("csv.writer")
def test_append_to_csv(mock_writer, mock_file):
    mock_writer_instance = MagicMock()
    mock_writer.return_value = mock_writer_instance
    append_to_csv("test.csv", ["data1", "data2"])
    mock_writer_instance.writerow.assert_called_once_with(["data1", "data2"])

@pytest.fixture
def mock_requests_get():
    with patch('requests.get') as mock:
        yield mock

@pytest.fixture
def mock_download_attachment():
    with patch('main.download_attachment') as mock:
        yield mock

@pytest.fixture
def mock_check_patterns():
    with patch('main.check_patterns') as mock:
        yield mock
        
def test_process_attachments_success(mock_requests_get, mock_download_attachment, mock_check_patterns):
    # Setup mock responses for the JIRA API and file download
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        'fields': {
            'attachment': [
                {'filename': 'example.csv', 'content': 'http://example.com/content'}
            ]
        }
    }
    mock_requests_get.return_value = mock_response

    # Setup mock for download_attachment
    mock_download_attachment.return_value = "some content"

    # Call the function
    process_attachments('ISSUE-123')

    # Check that download_attachment and check_patterns were called correctly
    mock_download_attachment.assert_called_once_with('http://example.com/content')
    mock_check_patterns.assert_called_once_with("some content", 'ISSUE-123', 'attachment', 'https://primerica-eazybi.atlassian.net/browse/ISSUE-123')

def test_process_attachments_no_attachments(mock_requests_get):
    # Setup mock responses for the JIRA API with no attachments
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        'fields': {
            'attachment': []
        }
    }
    mock_requests_get.return_value = mock_response

    # Call the function
    process_attachments('ISSUE-123')

    # No further actions should be taken
    mock_requests_get.assert_called()

def test_process_attachments_network_failure(mock_requests_get, mock_download_attachment):
    # Setup the mock to raise a network exception
    mock_requests_get.side_effect = requests.exceptions.RequestException("Network error")

    # Call the function and expect it to handle the error gracefully
    with patch('logging.error') as mock_log:
        process_attachments('ISSUE-123')
        assert mock_log.called

# Constants for the tests
BASE_URL = "https://primerica-eazybi.atlassian.net"
ISSUE_KEY = "TEST-123"

@pytest.fixture
def mock_response():
    """Fixture to create a mock response object."""
    mock = MagicMock()
    mock.json.return_value = {
        "values": [
            {
                "items": [
                    {"field": "description", "fromString": "Old description"}
                ]
            }
        ]
    }
    return mock

def test_process_history_success(mock_response):
    """Test process_history successfully processes changelog."""
    with patch('main.requests.get', return_value=mock_response) as mock_get, \
         patch('main.check_patterns') as mock_check_patterns:
        mock_response.status_code = 200
        process_history(ISSUE_KEY)
        
        # Assert get was called correctly
        mock_get.assert_called_once_with(f"{BASE_URL}/rest/api/3/issue/{ISSUE_KEY}/changelog",
                                         auth=AUTH, headers={"Accept": "application/json"})
        
        # Check if check_patterns was called correctly
        mock_check_patterns.assert_called_once_with("Old description", ISSUE_KEY, "description history", f"{BASE_URL}/browse/{ISSUE_KEY}")

def test_process_history_failure(mock_response):
    """Test process_history handles non-200 responses appropriately."""
    with patch('main.requests.get', return_value=mock_response) as mock_get, \
         patch('main.logging.error') as mock_log:
        mock_response.status_code = 404
        mock_response.text = "Not found"
        process_history(ISSUE_KEY)

        # Assert logging was called correctly
        mock_log.assert_any_call("Failed to retrieve changelog: 404")
        mock_log.assert_any_call("Not found")

def test_process_history_no_description_change(mock_response):
    """Test process_history when no description changes are present."""
    with patch('main.requests.get', return_value=mock_response) as mock_get, \
         patch('main.check_patterns') as mock_check_patterns:
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "values": [
                {
                    "items": [
                        {"field": "status", "fromString": "Open"}
                    ]
                }
            ]
        }
        process_history(ISSUE_KEY)

        # Check if check_patterns was never called
        mock_check_patterns.assert_not_called()

@pytest.mark.parametrize("status_code", [400, 500, 403])
def test_process_history_error_responses(mock_response, status_code):
    """Test process_history handles various error responses."""
    with patch('main.requests.get', return_value=mock_response) as mock_get, \
         patch('main.logging.error') as mock_log:
        mock_response.status_code = status_code
        process_history(ISSUE_KEY)

        # Assert error logging
        assert mock_log.call_count == 2
        
@pytest.fixture
def mock_comments_response():
    """Fixture to create a mock comments response object."""
    mock = MagicMock()
    mock.json.return_value = {
        "comments": [
            {"body": {"content": [{"text": "This is a comment."}]}},
            {"body": {"content": [{"text": "Another comment."}]}}
        ]
    }
    return mock

def test_process_comments_success(mock_comments_response):
    """Test process_comments correctly processes each comment."""
    with patch('main.requests.get', return_value=mock_comments_response) as mock_get, \
         patch('main.extract_text', side_effect=lambda x: x['content'][0]['text']) as mock_extract, \
         patch('main.check_patterns') as mock_check_patterns:
        
        process_comments(ISSUE_KEY)
        
        # Verify the requests.get call
        mock_get.assert_called_once_with(f"{BASE_URL}/rest/api/3/issue/{ISSUE_KEY}/comment",
                                         auth=AUTH, headers={"Accept": "application/json"})
        
        # Check that extract_text and check_patterns were called correctly
        assert mock_extract.call_count == 2
        expected_calls = [
            (("This is a comment.", ISSUE_KEY, "comment", f"{BASE_URL}/browse/{ISSUE_KEY}"),),
            (("Another comment.", ISSUE_KEY, "comment", f"{BASE_URL}/browse/{ISSUE_KEY}"),)
        ]
        mock_check_patterns.assert_has_calls(expected_calls, any_order=True)

def test_process_comments_no_comments(mock_comments_response):
    """Test process_comments when there are no comments."""
    mock_comments_response.json.return_value = {"comments": []}  # No comments
    with patch('main.requests.get', return_value=mock_comments_response) as mock_get, \
         patch('main.check_patterns') as mock_check_patterns:
        
        process_comments(ISSUE_KEY)
        
        # Verify no comments to process
        mock_check_patterns.assert_not_called()
