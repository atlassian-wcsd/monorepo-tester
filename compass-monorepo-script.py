import os
import sys
import json
import datetime
from typing import List, Dict, Optional
from github import Github
from github import Auth
import yaml
import pytz

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
        
    def calculate_deployment_time(self, pr_number: int, deployment_time: datetime.datetime) -> float:
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
    deployment_time = datetime.datetime.now(pytz.UTC)
    
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
    affected_components = calculator.get_affected_files(pr_number)
    print(f"PR affects {len(affected_components)} components")
    
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
        'timestamp': datetime.datetime.now(pytz.UTC).isoformat()
    }
    
    # Write metrics to file
    output_file = os.environ.get('METRICS_OUTPUT', 'deployment_metrics.json')
    calculator.write_metrics(metrics, output_file)
    print(f"Metrics written to {output_file}")
    
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