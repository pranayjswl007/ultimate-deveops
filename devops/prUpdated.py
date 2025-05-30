import os
import json
import requests
import logging
from typing import List, Dict

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# --- ANSI Colors ---
GREEN_TEXT = '\033[32m'
YELLOW_TEXT = '\033[33m'
RED_TEXT = '\033[31m'
RESET = '\033[0m'

# --- Utility Functions ---
def get_env_vars() -> Dict[str, str]:
    keys = [
        'PR_NUMBER', 'GITHUB_REPOSITORY', 'TOKEN_GITHUB',
        'COMMIT_ID', 'ARTIFACT_URL', 'ARTIFACT_ID', 'RUN_ID'
    ]
    return {key: os.environ.get(key) for key in keys}

def load_json_file(filename: str) -> dict:
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"File not found: {filename}")
        exit(1)
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in {filename}")
        exit(1)

def build_summary(deploy_result: dict, env: dict) -> str:
    result = deploy_result.get("result", {})
    details = result.get("details", {})

    name = deploy_result.get("name", "N/A")
    deployment_id = result.get("id", "N/A")
    deploy_url = result.get("deployUrl", "")

    summary = f"""
### \U0001F680 Deployment/Validation Summary
- **Status:** {"\u2705 Success" if result.get("success") or name=="NothingToDeploy" else "\u274C Failed"}
- **Name:** {name}
- **Start Time:** {result.get("startDate", "N/A")}
- **End Time:** {result.get("completedDate", "N/A")}
- **Components Deployed:** {result.get("numberComponentsDeployed", 0)} / {result.get("numberComponentsTotal", 0)}
- **Component Errors:** {result.get("numberComponentErrors", 0)}
- **Tests Run:** {result.get("numberTestsCompleted", 0)} / {result.get("numberTestsTotal", 0)}

### \ud83d\udccc Deployment Metadata
- **Deployment ID:** {deployment_id}
- **Deployment URL:** [View Deployment]({deploy_url})
- **Artifact URL:** {env['ARTIFACT_URL']}
- **Artifact ID:** {env['ARTIFACT_ID']}
- **Run Id:** {env['RUN_ID']}
"""

    # Add details
    summary += format_failures(details)
    summary += format_coverage(details)
    return summary

def format_failures(details: dict) -> str:
    section = ""
    failures = details.get("runTestResult", {}).get("failures", [])
    coverage_warnings = details.get("runTestResult", {}).get("codeCoverageWarnings", [])
    flow_warnings = details.get("runTestResult", {}).get("flowCoverageWarnings", [])
    component_failures = details.get("componentFailures", [])

    if component_failures:
        section += "\n\n### \u274C Component Failures\n| Type | File | Problem |\n|------|------|---------|\n"
        for cf in component_failures:
            section += f"| {cf.get('componentType')} | `{cf.get('fileName')}` | {cf.get('problem')} |\n"

    if failures:
        section += "\n\n### \u274C Test Failures\n| Name | Method | Message |\n|------|--------|---------|\n"
        for failure in failures:
            section += f"| `{failure['name']}` | `{failure['methodName']}` | {failure['message']} |\n"

    if coverage_warnings:
        section += "\n\n### \u26A0\uFE0F Code Coverage Warnings\n| Name | Message |\n|------|---------|\n"
        for warning in coverage_warnings:
            section += f"| `{warning['name']}` | {warning['message']} |\n"

    if flow_warnings:
        section += "\n\n### \u26A0\uFE0F Flow Coverage Warnings\n| Flow Name | Message |\n|-----------|---------|\n"
        for warning in flow_warnings:
            section += f"| `{warning.get('name')}` | {warning.get('message')} |\n"

    return section

def format_coverage(details: dict) -> str:
    section = ""
    code_coverage = details.get("runTestResult", {}).get("codeCoverage", [])
    flows = details.get("runTestResult", {}).get("flowCoverage", [])

    under_covered = [
        {
            "name": c.get("name"),
            "coverage": round((c.get("numLocations", 0) - c.get("numLocationsNotCovered", 0)) * 100 / c.get("numLocations", 1), 2),
            "uncovered": c.get("numLocationsNotCovered")
        } for c in code_coverage if c.get("numLocations", 0) and round((c.get("numLocations", 0) - c.get("numLocationsNotCovered", 0)) * 100 / c.get("numLocations", 1), 2) < 90
    ]
    under_covered.sort(key=lambda x: x['coverage'])

    if under_covered:
        section += "\n\n### \U0001F9EA Top 10 Apex Classes with <90% Code Coverage\n| Class | Coverage % | Uncovered Lines |\n|-------|-------------|------------------|\n"
        for item in under_covered[:10]:
            section += f"| `{item['name']}` | {item['coverage']}% | {item['uncovered']} |\n"

    flow_coverage = [
        {
            "flowName": f.get("flowName"),
            "coverage": round((f.get("numElements", 0) - f.get("numElementsNotCovered", 0)) * 100 / f.get("numElements", 1), 2),
            "uncovered": f.get("numElementsNotCovered"),
            "processType": f.get("processType")
        } for f in flows if f.get("numElements", 0) and round((f.get("numElements", 0) - f.get("numElementsNotCovered", 0)) * 100 / f.get("numElements", 1), 2) < 90
    ]
    flow_coverage.sort(key=lambda x: x['coverage'])

    if flow_coverage:
        section += "\n\n### \U0001F501 Top 10 Flows with <90% Coverage\n| Flow Name | Type | Coverage % | Uncovered Elements |\n|-----------|------|-------------|---------------------|\n"
        for flow in flow_coverage[:10]:
            section += f"| `{flow['flowName']}` | {flow['processType']} | {flow['coverage']}% | {flow['uncovered']} |\n"

    return section

def format_slowest_tests(details: dict) -> str:
    test_successes = details.get("runTestResult", {}).get("successes", [])
    slowest_tests = sorted(
        [t for t in test_successes if "time" in t],
        key=lambda t: t["time"],
        reverse=True
    )[:10]

    if not slowest_tests:
        return ""

    section = "\n\n### 🐢 Top 10 Slowest Apex Test Methods\n| Class | Method | Time (s) |\n|--------|--------|----------|\n"
    for test in slowest_tests:
        section += f"| `{test['name']}` | `{test['methodName']}` | {test['time']} |\n"

    return section

def extract_comments(details: dict) -> List[Dict[str, str]]:
    comments = []
    for cf in details.get("componentFailures", []):
        path = cf.get("fileName")
        if "changed-sources/" in path:
            path = path.split("changed-sources/")[1]
        comments.append({
            "path": path,
            "position": 1,
            "body": f"[{cf.get('componentType')}] {cf.get('problem')}"
        })
    return comments

def post_review(env: dict, summary: str, comments: List[Dict[str, str]]):
    owner, repo = env['GITHUB_REPOSITORY'].split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{env['PR_NUMBER']}/reviews"

    headers = {
        "Authorization": f"Bearer {env['TOKEN_GITHUB']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    payload = {
        "commit_id": env['COMMIT_ID'],
        "body": summary,
        "event": "COMMENT",
        "comments": comments
    }

    logging.info("Submitting PR review...")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in (200, 201):
        print(f"{GREEN_TEXT}✅ Review submitted successfully!{RESET}")
    else:
        print(f"{RED_TEXT}❌ Failed to submit review: {response.status_code}{RESET}")
        print(response.text)
        exit(1)

    # Decide exit status
    result = load_json_file("deploymentResult.json").get("result", {})
    name = load_json_file("deploymentResult.json").get("name", "")
    if result.get("success") or name == "NothingToDeploy":
        exit(0)
    else:
        exit(1)

# --- Main Execution ---
def main():
    env = get_env_vars()
    deploy_result = load_json_file("deploymentResult.json")
    summary = build_summary(deploy_result, env)
    details = deploy_result.get("result", {}).get("details", {})
    comments = extract_comments(details)
    post_review(env, summary, comments)
    summary += format_slowest_tests(details)


if __name__ == "__main__":
    main()
