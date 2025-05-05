import os
import json
import requests
import datetime

GREEN_TEXT = '\033[32m'
YELLOW_TEXT = '\033[33m'
RED_TEXT = '\033[31m'
RESET = '\033[0m'
CYAN_BG = '\033[46m'

pr_number = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token = os.environ.get('TOKEN_GITHUB')
commit_id = os.environ.get('COMMIT_ID')
artifact_url = os.environ.get('ARTIFACT_URL')
artifact_id = os.environ.get('ARTIFACT_ID')
env_file = os.getenv('GITHUB_ENV')  # Get the path of the runner file



print(f"GitHub Repository: {github_repository}")
print(f"GitHub Token: {github_token}")
print(f"PR Number: {pr_number}")
print(f"commit_id: {commit_id}")
print(f"Artifact URL: {artifact_url}")

owner, repo = github_repository.split("/")

deployment_result_file = "deploymentResult.json"

try:
    with open(deployment_result_file, "r") as file:
        deploy_result = json.load(file)
        print("✅ Deployment result loaded.")
        print(json.dumps(deploy_result, indent=2))
except FileNotFoundError:
    print(f"{CYAN_BG}{RED_TEXT}Error: File {deployment_result_file} not found.{RESET}")
    exit(1)
except json.JSONDecodeError:
    print(f"{CYAN_BG}{RED_TEXT}Error: Invalid JSON in {deployment_result_file}.{RESET}")
    exit(1)

result = deploy_result.get("result", {})
with open(env_file, "a") as f:
    f.write(f"QUICK_DEPLOY_STATUS={result.success}\n")


