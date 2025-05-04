import os
import json
import requests
from tqdm import tqdm
from rich import print
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# --- Environment Variables ---
pr_number = os.environ.get("PR_NUMBER")
github_repository = os.environ.get("GITHUB_REPOSITORY")
github_token = os.environ.get("TOKEN_GITHUB")
commit_id = os.environ.get("COMMIT_ID")
artifact_url = os.environ.get("ARTIFACT_URL")

owner, repo = github_repository.split("/") if github_repository else ("", "")

# --- Print Initial Info ---
console.rule("[bold blue]GitHub Deployment Info")
console.print(f"[bold]Repository:[/] {github_repository}")
console.print(f"[bold]PR Number:[/] {pr_number}")
console.print(f"[bold]Commit ID:[/] {commit_id}")
console.print(f"[bold]Artifact URL:[/] {artifact_url}")

# --- Load Deployment Result ---
deployment_result_file = "deploymentResult.json"
deploy_result = {}

steps = [
    "Reading deployment result JSON",
    "Parsing metadata and errors",
    "Formatting review body",
    "Submitting review to GitHub"
]

for step in tqdm(steps, desc="Processing Steps", ncols=100):
    if step == "Reading deployment result JSON":
        try:
            with open(deployment_result_file, "r") as file:
                deploy_result = json.load(file)
        except FileNotFoundError:
            console.print(f"[bold red]❌ Error: '{deployment_result_file}' not found.")
            exit(1)
        except json.JSONDecodeError:
            console.print(f"[bold red]❌ Error: Invalid JSON in '{deployment_result_file}'.")
            exit(1)

    elif step == "Parsing metadata and errors":
        result = deploy_result.get("result", {})
        details = result.get("details", {})
        deployment_id = result.get("id", "N/A")
        deploy_url = result.get("deployUrl", "")

        success = result.get("success", False)
        summary_status = "[green]✅ Success[/green]" if success else "[red]❌ Failed[/red]"

        summary = Panel.fit(
            f"""
[bold]🚀 Deployment Summary[/bold]
• Status: {summary_status}
• Start Time: {result.get("startDate", "N/A")}
• End Time: {result.get("completedDate", "N/A")}
• Components: {result.get("numberComponentsDeployed", 0)} / {result.get("numberComponentsTotal", 0)}
• Component Errors: {result.get("numberComponentErrors", 0)}
• Tests Run: {result.get("numberTestsCompleted", 0)} / {result.get("numberTestsTotal", 0)}
• Deployment ID: {deployment_id}
• [link={deploy_url}]Deployment URL[/link]
• [link={artifact_url}]Artifact URL[/link]
            """,
            title="Deployment Summary",
            border_style="cyan"
        )

        failures = details.get("runTestResult", {}).get("failures", [])
        component_failures = details.get("componentFailures", [])
        coverage_warnings = details.get("runTestResult", {}).get("codeCoverageWarnings", [])

    elif step == "Formatting review body":
        comment_body = summary.renderable
        if component_failures:
            table = Table(title="❌ Component Failures")
            table.add_column("Type")
            table.add_column("File")
            table.add_column("Problem")
            for cf in component_failures:
                table.add_row(cf.get("componentType", "N/A"), cf.get("fileName", "N/A"), cf.get("problem", "N/A"))
            console.print(table)

        if failures:
            table = Table(title="❌ Test Failures")
            table.add_column("Name")
            table.add_column("Method")
            table.add_column("Message")
            for failure in failures:
                table.add_row(failure["name"], failure["methodName"], failure["message"])
            console.print(table)

        if coverage_warnings:
            table = Table(title="⚠️ Code Coverage Warnings")
            table.add_column("Name")
            table.add_column("Message")
            for warn in coverage_warnings:
                table.add_row(warn["name"], warn["message"])
            console.print(table)

        # Inline Comments
        comments = []
        for cf in component_failures:
            path = cf.get("fileName")
            if "changed-sources/" in path:
                path = path.split("changed-sources/")[1]
            comments.append({
                "path": path,
                "position": 1,
                "body": f"[{cf.get('componentType')}] {cf.get('problem')}"
            })

    elif step == "Submitting review to GitHub":
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        review_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        payload = {
            "commit_id": commit_id,
            "body": str(summary),
            "event": "COMMENT",
            "comments": comments
        }

        response = requests.post(review_url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            console.print("[bold green]✅ Review submitted successfully.")
            exit(0 if success else 1)
        else:
            console.print(f"[bold red]❌ Failed to submit review ({response.status_code})")
            console.print(response.text)
            exit(1)
