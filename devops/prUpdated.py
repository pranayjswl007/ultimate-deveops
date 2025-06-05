import os
import json
import requests
import datetime

GREEN_TEXT = '\033[32m'
YELLOW_TEXT = '\033[33m'
RED_TEXT = '\033[31m'
RESET = '\033[0m'
CYAN_BG = '\033[46m'

pr_number         = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token      = os.environ.get('TOKEN_GITHUB')
commit_id         = os.environ.get('COMMIT_ID')
artifact_url      = os.environ.get('ARTIFACT_URL')
artifact_id       = os.environ.get('ARTIFACT_ID')
run_id            = os.environ.get('RUN_ID')

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

result  = deploy_result.get("result", {})
details = result.get("details", {})

deployment_id = result.get("id", "N/A")
deploy_url    = result.get("deployUrl", "")
name          = deploy_result.get("name", "N/A")

# --- Build the big 'body' of the review ---
summary = f"""
### 🚀 Deployment/Validation Summary
- **Status:** {"✅ Success" if result.get("success") or name == "NothingToDeploy" else "❌ Failed"}
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

# --- Append Component Failures if any ---
component_failures = details.get("componentFailures", [])
if component_failures:
    summary += "\n\n### ❌ Component Failures\n| Type | File | Problem |\n|------|------|---------|\n"
    for cf in component_failures:
        # show raw path; no inline attaching
        summary += f"| {cf.get('componentType')} | `{cf.get('fileName')}` | {cf.get('problem')} |\n"

# --- Append Test Failures if any ---
failures = details.get("runTestResult", {}).get("failures", [])
if failures:
    summary += "\n\n### ❌ Test Failures\n| Name | Method | Message |\n|------|--------|---------|\n"
    for failure in failures:
        summary += f"| `{failure['name']}` | `{failure['methodName']}` | {failure['message']} |\n"

# --- Append Code Coverage Warnings if any ---
coverage_warnings = details.get("runTestResult", {}).get("codeCoverageWarnings", [])
if coverage_warnings:
    summary += "\n\n### ⚠️ Code Coverage Warnings\n| Name | Message |\n|------|---------|\n"
    for warning in coverage_warnings:
        summary += f"| `{warning['name']}` | {warning['message']} |\n"

# --- Append Flow Coverage Warnings if any ---
flow_warnings = details.get("runTestResult", {}).get("flowCoverageWarnings", [])
if flow_warnings:
    summary += "\n\n### ⚠️ Flow Coverage Warnings\n| Flow Name | Message |\n|-----------|---------|\n"
    for warning in flow_warnings:
        summary += f"| `{warning.get('name')}` | {warning.get('message')} |\n"

# --- Append Top 10 Apex Classes with <90% Coverage ---
coverage_info   = details.get("runTestResult", {}).get("codeCoverage", [])
coverage_data   = []
for item in coverage_info:
    total    = item.get("numLocations", 0)
    uncovered= item.get("numLocationsNotCovered", 0)
    if total == 0:
        continue
    coverage_pct = round((total - uncovered) * 100 / total, 2)
    if coverage_pct < 90:
        coverage_data.append({
            "name":     item.get("name"),
            "coverage": coverage_pct,
            "uncovered": uncovered
        })
coverage_data.sort(key=lambda x: x["coverage"])
if coverage_data:
    summary += "\n\n### 🧪 Top 10 Apex Classes with <90% Code Coverage\n| Class | Coverage % | Uncovered Lines |\n|-------|-------------|------------------|\n"
    for item in coverage_data[:10]:
        summary += f"| `{item['name']}` | {item['coverage']}% | {item['uncovered']} |\n"

# --- Append Top 10 Flows with <90% Coverage ---
flow_info      = details.get("runTestResult", {}).get("flowCoverage", [])
flow_data      = []
for flow in flow_info:
    total     = flow.get("numElements", 0)
    uncovered = flow.get("numElementsNotCovered", 0)
    if total == 0:
        continue
    coverage_pct = round((total - uncovered) * 100 / total, 2)
    if coverage_pct < 90:
        flow_data.append({
            "flowName":    flow.get("flowName"),
            "coverage":    coverage_pct,
            "uncovered": uncovered,
            "processType": flow.get("processType")
        })
flow_data.sort(key=lambda x: x["coverage"])
if flow_data:
    summary += "\n\n### 🔁 Top 10 Flows with <90% Coverage\n| Flow Name | Type | Coverage % | Uncovered Elements |\n|-----------|------|-------------|---------------------|\n"
    for flow in flow_data[:10]:
        summary += f"| `{flow['flowName']}` | {flow['processType']} | {flow['coverage']}% | {flow['uncovered']} |\n"

# --- Append Top 10 Slowest Test Methods ---
slow_methods   = []
test_successes = details.get("runTestResult", {}).get("successes", [])
for test_item in test_successes:
    class_name  = test_item.get("name")
    method_name = test_item.get("methodName")
    time_ms     = test_item.get("time", 0)
    if class_name and method_name:
        slow_methods.append({
            "class":  class_name,
            "method": method_name,
            "time":   time_ms
        })
slow_methods.sort(key=lambda x: x["time"], reverse=True)
if slow_methods:
    summary += "\n\n### 🐢 Top 10 Slowest Test Methods\n| Class | Method | Time (ms) |\n|--------|--------|------------|\n"
    for test_item in slow_methods[:10]:
        summary += f"| `{test_item['class']}` | `{test_item['method']}` | {test_item['time']} |\n"

# ────────────────────────────────────────────────────────────────────────────────
# Build review payload WITHOUT any inline comments:
review_payload = {
    "commit_id": commit_id,
    "body":      summary,
    "event":     "COMMENT"
}

# Call the Create‐Review endpoint:
headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept":        "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}
review_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

print(f"{YELLOW_TEXT}📤 Submitting a single, large review comment…{RESET}")
response = requests.post(review_url, headers=headers, json=review_payload)

if response.status_code in (200, 201):
    print(f"{GREEN_TEXT}✅ Review submitted successfully!{RESET}")
    if result.get("success") or name == "NothingToDeploy":
        exit(0)
    else:
        exit(1)
else:
    print(f"{RED_TEXT}❌ Failed to submit review: {response.status_code}{RESET}")
    print(review_payload)
    print(response.text)
    exit(1)
