import requests
import re
import os

# GitHub API information
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Get the token from GitHub secrets
REPO = os.getenv("GITHUB_REPOSITORY")  # In GitHub Actions, the repository is set as an environment variable
PR_NUMBER = os.getenv("PR_NUMBER")  # You need to pass the PR number or get it from the event

# GitHub API URL
API_URL = f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/comments"

# Request headers with GitHub token for authentication
headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Fetch all comments on the PR
response = requests.get(API_URL, headers=headers)

if response.status_code == 200:
    comments = response.json()

    # Find the latest github-actions[bot] comment
    latest_comment = None
    for comment in comments:
        if comment['user']['login'] == "github-actions[bot]":
            latest_comment = comment['body']
    
    if latest_comment:
        print("Full comment body:")
        print(latest_comment)

        # Extract Deployment ID using regex
        deployment_id_match = re.search(r"Deployment ID:\s*(\S+)", latest_comment)
        if deployment_id_match:
            deployment_id = deployment_id_match.group(1)
            print(f"Deployment ID: {deployment_id}")
            # Set Deployment ID as an environment variable
            os.environ["DEPLOYMENT_ID"] = deployment_id
        else:
            print("Deployment ID not found")

        # Extract Artifact URL using regex
        artifact_url_match = re.search(r"Artifact URL:\s*(\S+)", latest_comment)
        if artifact_url_match:
            artifact_url = artifact_url_match.group(1)
            print(f"Artifact URL: {artifact_url}")
            # Set Artifact URL as an environment variable
            os.environ["ARTIFACT_URL"] = artifact_url
        else:
            print("Artifact URL not found")
    else:
        print("No comment from github-actions[bot] found.")
else:
    print(f"Failed to fetch comments: {response.status_code}")
