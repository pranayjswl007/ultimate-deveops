import requests
import re
import os

# GitHub API information
TOKEN_GITHUB = os.getenv("TOKEN_GITHUB")  # Get the token from GitHub secrets
REPO = os.getenv("GITHUB_REPOSITORY")  # In GitHub Actions, the repository is set as an environment variable
PR_NUMBER = os.getenv("PR_NUMBER")  # You need to pass the PR number or get it from the event
env_file = os.getenv('GITHUB_ENV')  # Get the path of the runner file

# GitHub API URL
API_URL = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/reviews"

print(f"GitHub API_URL: {API_URL}")

# Request headers with GitHub token for authentication
headers = {
    "Authorization": f"Bearer {TOKEN_GITHUB}",
    "Accept": "application/vnd.github.full+json",
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
        deployment_id_match = re.search(r"\*\*Deployment ID:\*\*\s([A-Za-z0-9]+)", latest_comment)
        if deployment_id_match:
            deployment_id = deployment_id_match.group(1)
            print(f"Deployment ID: {deployment_id}")
            # Set Deployment ID as an environment variable
            with open(env_file, "a") as f:
                f.write(f"DEPLOYMENT_ID={deployment_id}\n")
        else:
            print("Deployment ID not found")

        # Regex pattern to match the Artifact URL
        artifact_url_match = re.search(r"\*\*Artifact URL:\*\*\s([^\s]+)", latest_comment)
        if artifact_url_match:
            artifact_url = artifact_url_match.group(1)
            print(f"Artifact URL: {artifact_url}")
            # Set Artifact URL as an environment variable
            with open(env_file, "a") as f:
                f.write(f"ARTIFACT_URL={artifact_url}\n")
        else:
            print("Artifact URL not found")

        # Regex pattern to match the Artifact ID
        artifact_id_match = re.search(r"\*\*Artifact ID:\*\*\s([^\s]+)", latest_comment)
        if artifact_id_match:
            artifact_id = artifact_id_match.group(1)
            print(f"Artifact ID: {artifact_id}")
            # Set Artifact ID as an environment variable
            with open(env_file, "a") as f:
                f.write(f"ARTIFACT_ID={artifact_id}\n")
        else:
            print("Artifact ID not found")
    else:
        print("No comment from github-actions[bot] found.")
else:
    print(f"Failed to fetch comments: {response.status_code}")
