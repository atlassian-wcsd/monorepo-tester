import os
import sys
import json
from typing import List, Dict, Optional
from github import Github
from github import Auth
import yaml
import pytz
import requests
import os
from datetime import datetime


def getComponentARI(file_path):
    """
    Retrieves the 'id' from a YAML file and splits the given URL by '/'.

    Parameters:
    - file_path (str): The path to the YAML file.
    - url (str): The URL to be split.

    Returns:
     - cloudId from the YAML file, representing the Atlassian site
     - componentId from the YAML file, representing the component
   
    """
    # Read the YAML file
    try:
        with open(file_path, 'r') as file:
            data = yaml.safe_load(file)
            id_value = data.get('id', None)  #Get the ARI value from the YAML file
            if id_value is None:
                raise ValueError("ID not found in YAML file.")
            # Split the URL by '/'
            url_parts = id_value.split(':')
            cloud_id = url_parts[3]
            component_id = id_value
    except Exception as e:
        print(f"Error reading YAML file: {e}")
        return None, None

    
    return component_id, cloud_id   

def find_overlapping_directories(list_a, list_b):
    """
    Given two lists of file paths, evaluates whether there are overlaps
    in directories, ignoring the file names, and returns the full file paths
    from list_a that are in overlapping directories with list_b.
    Parameters:
    - list_a (list): The first list of file paths.
    - list_b (list): The second list of file paths.
    Returns:
    - list: A list of overlapping file paths from list_a found in directories from list_b.
    """
    overlapping_files = []
    # Create a set for quick lookup of directories in list_b
    set_b = {os.path.normpath(os.path.dirname(path)) for path in list_b}
    # Track the deepest file path found in overlapping directories
    deepest_overlapping = {}
    for path_a in list_a:
        # Get the directory of path_a by ignoring the file name
        directory_a = os.path.normpath(os.path.dirname(path_a))
        # Check if the directory_a is in set_b
        if directory_a in set_b:
            # If this directory is already found, we compare to keep the deepest path
            if directory_a not in deepest_overlapping or len(path_a) > len(deepest_overlapping[directory_a]):
                deepest_overlapping[directory_a] = path_a

    # Collect only the deepest overlapping file paths
    overlapping_files = list(deepest_overlapping.values())
    # Print the number of overlapping files found and the list of those files
    print("Found %d overlapping file paths: %s" % (len(overlapping_files), str(overlapping_files)))
    return overlapping_files

def send_compass_event(repository,pull_request,cloud_id,component_id):
    # Environment variables
    user_email = os.getenv('USER_EMAIL')
    user_api_token = os.getenv('USER_API_TOKEN')
    atlassian_site=os.getenv('ATLASSIAN_SITE')
    
    if not ( user_email and user_api_token and atlassian_site):
        print("Atlassian credentials and configuration not set")
        sys.exit(1)

    # Prepare the URL
    url = "https://"+atlassian_site+".atlassian.net/gateway/api/compass/v1/events"
    pr_url = "https://github.com/"+repository+"/pull/"+pull_request

    # Prepare the headers
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Prepare the data payload
    #TODO - update the event name and description
    data = {
        "cloudId": cloud_id,
        "event": {
            "custom": {
                "updateSequenceNumber": 1,
                "displayName": "name",
                "description": "description",
                "url": pr_url,
                "lastUpdated": datetime.now(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "externalEventSourceId": repository,
                "customEventProperties": {
                    "id": "1",
                    "icon": "INFO"
                }
            }
        },
        "componentId": component_id
    }

    # Make the POST request
    response = requests.post(url, json=data, headers=headers, auth=(user_email, user_api_token))

    # Check the response
    if response.status_code == 200:
        print("Event created successfully:", response.json())
    else:
        print("Failed to create event:", response.status_code, response.text)

class MetricsCalculator:
    def __init__(self, github_token: str, repository: str):
        self.github_token = Auth.Token(github_token)
        self.repository_name = repository
        self.g = Github(auth=self.github_token)
        self.repo = self.g.get_repo(repository)
        
    def find_compass_files(self) -> List[str]:
        """Find all compass.yml files in the repository"""
        compass_files = []
        contents = self.repo.get_contents("")
        
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(self.repo.get_contents(file_content.path))
            elif file_content.name == "compass.yml":
                compass_files.append(file_content.path)
        return compass_files

    def get_affected_files(self, pr_number: int) -> List[str]:
        """Get list of files affected by a PR"""
        pr = self.repo.get_pull(pr_number)
        return [file.filename for file in pr.get_files()]

    def calculate_cycle_time(self, pr_number: int) -> Dict[str, float]:
        """Calculate various cycle time metrics for a PR"""
        pr = self.repo.get_pull(pr_number)
        
        # Convert times to UTC
        created_at = pr.created_at.replace(tzinfo=pytz.UTC)
        merged_at = pr.merged_at.replace(tzinfo=pytz.UTC) if pr.merged_at else None
        
        metrics = {
            'pr_cycle_time': 0,
            'time_to_first_review': 0,
            'time_to_merge': 0
        }
        
        if not merged_at:
            return metrics
            
        # Calculate PR cycle time (time from PR creation to merge)
        metrics['pr_cycle_time'] = (merged_at - created_at).total_seconds() / 3600  # in hours
        
        # Calculate time to first review
        reviews = list(pr.get_reviews())
        if reviews:
            first_review = min(review.submitted_at for review in reviews)
            first_review = first_review.replace(tzinfo=pytz.UTC)
            metrics['time_to_first_review'] = (first_review - created_at).total_seconds() / 3600
            
        # Calculate time to merge
        metrics['time_to_merge'] = (merged_at - created_at).total_seconds() / 3600
        
        return metrics
        
    def calculate_deployment_time(self, pr_number: int, deployment_time: datetime) -> float:
        """Calculate deployment time (time from merge to deployment)"""
        pr = self.repo.get_pull(pr_number)
        
        if not pr.merged_at:
            return 0
            
        merged_at = pr.merged_at.replace(tzinfo=pytz.UTC)
        deployment_time = deployment_time.replace(tzinfo=pytz.UTC)
        
        return (deployment_time - merged_at).total_seconds() / 3600  # in hours
        
    def write_metrics(self, metrics: Dict[str, float], output_file: str):
        """Write metrics to a JSON file"""
        with open(output_file, 'w') as f:
            json.dump(metrics, f, indent=2)
            
def main():
    # Get environment variables
    github_token = os.environ.get('GITHUB_TOKEN')
    repository = os.environ.get('GITHUB_REPOSITORY')
    pr_number = int(os.environ.get('PR_NUMBER')) 
    deployment_time = datetime.now(pytz.UTC)
    
    if not all([github_token, repository, pr_number]):
        print("Missing required environment variables")
        if not len(github_token) > 0:
            print("Github Token not found")
        print("Repo: %s, PR Number: %d" % (repository, pr_number))
        sys.exit(1)
    
    # Initialize calculator
    calculator = MetricsCalculator(github_token, repository)
    
    # Find compass files
    compass_files = calculator.find_compass_files()
    print(f"Found {len(compass_files)} compass.yml files")
    
    # Get affected files
    affected_files = calculator.get_affected_files(pr_number)
    print(f"PR affects {len(affected_files)} files")
    
    affected_components = find_overlapping_directories(compass_files,affected_files)
    
    # Calculate metrics
    cycle_time_metrics = calculator.calculate_cycle_time(pr_number)
    deployment_time = calculator.calculate_deployment_time(pr_number, deployment_time)
    
    # Combine all metrics
    metrics = {
        **cycle_time_metrics,
        'deployment_time': deployment_time,
        'compass_files': compass_files,
        'affected_components': affected_components,
        'pr_number': pr_number,
        'repository': repository,
        'timestamp': datetime.now(pytz.UTC).isoformat()
    }
    
    # Write metrics to file
    output_file = os.environ.get('METRICS_OUTPUT', 'deployment_metrics.json')
    calculator.write_metrics(metrics, output_file)
    print(f"Metrics written to {output_file}")
    
    for component in affected_components:
        # Fetch YAML file and get Ids
        cloud_id, component_id = getComponentARI(component)
        print("Wanted to send event for {component_id} on {cloud_id}")
        # Send Compass event
        send_compass_event(repository, pr_number, cloud_id, component_id)
        print("Compass event sent")
    
    # Print summary to console
    print("\nMetrics Summary:")
    print(f"PR Cycle Time: {metrics['pr_cycle_time']:.2f} hours")
    print(f"Time to First Review: {metrics['time_to_first_review']:.2f} hours")
    print(f"Time to Merge: {metrics['time_to_merge']:.2f} hours")
    print(f"Deployment Time: {metrics['deployment_time']:.2f} hours")
    print(f"Total Components Affected: {len(metrics['affected_components'])}")
    print(f"Total Compass Files: {len(metrics['compass_files'])}")

if __name__ == "__main__":
    main()