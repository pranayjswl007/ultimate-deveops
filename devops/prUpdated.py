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
run_id = os.environ.get('RUN_ID')


print(f"GitHub Repository: {github_repository}")
print(f"GitHub Token: {github_token}")
print(f"PR Number: {pr_number}")
print(f"commit_id: {commit_id}")
print(f"Artifact URL: {artifact_url}")
print(f"RUN Id: {run_id}")


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
details = result.get("details", {})

deployment_id = result.get("id", "N/A")
deploy_url = result.get("deployUrl", "")

name = result.get("name", "N/A")
description = ""

# --- Deployment Summary ---
summary = f"""
### 🚀 Deployment/Validation Summary
- **Status:** {"✅ Success" if result.get("success") or name=="NothingToDeploy" else "❌ Failed"}
- **Name:** {name}
- **Start Time:** {result.get("startDate", "N/A")}
- **End Time:** {result.get("completedDate", "N/A")}
- **Components Deployed:** {result.get("numberComponentsDeployed", 0)} / {result.get("numberComponentsTotal", 0)}
- **Component Errors:** {result.get("numberComponentErrors", 0)}
- **Tests Run:** {result.get("numberTestsCompleted", 0)} / {result.get("numberTestsTotal", 0)}


### 📌 Deployment Metadata
- **Deployment ID:** {deployment_id}
- **Deployment URL:** [View Deployment]({deploy_url})
- **Artifact URL:** {artifact_url}
- **Artifact ID:** {artifact_id}
- **Run Id:** {run_id}
"""


# --- Failures for Review Body ---
failures = details.get("runTestResult", {}).get("failures", [])
coverage_warnings = details.get("runTestResult", {}).get("codeCoverageWarnings", [])
component_failures = details.get("componentFailures", [])

if component_failures:
    summary += "\n\n### ❌ Component Failures\n| Type | File | Problem |\n|------|------|---------|\n"
    for cf in component_failures:
        summary += f"| {cf.get('componentType')} | `{cf.get('fileName')}` | {cf.get('problem')} |\n"

if failures:
    summary += "\n\n### ❌ Test Failures\n| Name | Method | Message |\n|------|--------|---------|\n"
    for failure in failures:
        summary += f"| `{failure['name']}` | `{failure['methodName']}` | {failure['message']} |\n"

if coverage_warnings:
    summary += "\n\n### ⚠️ Code Coverage Warnings\n| Name | Message |\n|------|---------|\n"
    for warning in coverage_warnings:
        summary += f"| `{warning['name']}` | {warning['message']} |\n"

# --- Inline Review Comments ---
comments = []
for cf in component_failures:
    path = cf.get("fileName")
    # Trim file path to repo-relative if needed
    if "changed-sources/" in path:
        path = path.split("changed-sources/")[1]
    comment = {
        "path": path,
        "position": 1,  # Fallback line number — GitHub requires it
        "body": f"[{cf.get('componentType')}] {cf.get('problem')}"
    }
    comments.append(comment)

# --- Determine Review Event ---
event = "COMMENT"

# --- GitHub API: PR Review ---
headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

review_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

review_payload = {
    "commit_id": commit_id,
    "body": summary,
    "event": event,
    "comments": comments
}

print(f"{YELLOW_TEXT}📤 Submitting PR review as '{event}'...{RESET}")
response = requests.post(review_url, headers=headers, json=review_payload)

if response.status_code == 200 or response.status_code == 201:
    print(f"{GREEN_TEXT}✅ Review submitted successfully!{RESET}")
    if(result.get("success")):
        exit(0)
    else:
        exit(1)
else:
    print(f"{RED_TEXT}❌ Failed to submit review: {response.status_code}{RESET}")
    print(response.text)
    exit(1)
