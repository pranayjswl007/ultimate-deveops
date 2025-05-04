import os
import json
import requests
import time
from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax

# Initialize rich console
console = Console()

pr_number = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token = os.environ.get('TOKEN_GITHUB')
commit_id = os.environ.get('COMMIT_ID')
artifact_url = os.environ.get('ARTIFACT_URL')

# Print environment variables with rich formatting
console.print(Panel.fit("[bold blue]Deployment Environment Variables[/bold blue]"))
console.print(f"[bold]GitHub Repository:[/bold] [green]{github_repository}[/green]")
console.print(f"[bold]GitHub Token:[/bold] {'***' if github_token else '[red]Not set[/red]'}")
console.print(f"[bold]PR Number:[/bold] [green]{pr_number}[/green]")
console.print(f"[bold]Commit ID:[/bold] [green]{commit_id}[/green]")
console.print(f"[bold]Artifact URL:[/bold] [green]{artifact_url}[/green]")
console.print()

deployment_result_file = "deploymentResult.json"

# Use tqdm and rich for loading file visualization
with console.status("[bold green]Loading deployment result...", spinner="dots") as status:
    try:
        with open(deployment_result_file, "r") as file:
            deploy_result = json.load(file)
            console.print("[bold green]✅ Deployment result loaded.[/bold green]")
            
            # Display the JSON in a nice syntax-highlighted format
            json_str = json.dumps(deploy_result, indent=2)
            syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
            console.print(syntax)
            
    except FileNotFoundError:
        console.print(f"[bold white on red]Error: File {deployment_result_file} not found.[/bold white on red]")
        exit(1)
    except json.JSONDecodeError:
        console.print(f"[bold white on red]Error: Invalid JSON in {deployment_result_file}.[/bold white on red]")
        exit(1)

result = deploy_result.get("result", {})
details = result.get("details", {})

deployment_id = result.get("id", "N/A")
deploy_url = result.get("deployUrl", "")

# --- Deployment Summary ---
summary = f"""
### 🚀 Deployment Summary
- **Status:** {"✅ Success" if result.get("success") else "❌ Failed"}
- **Start Time:** {result.get("startDate", "N/A")}
- **End Time:** {result.get("completedDate", "N/A")}
- **Components Deployed:** {result.get("numberComponentsDeployed", 0)} / {result.get("numberComponentsTotal", 0)}
- **Component Errors:** {result.get("numberComponentErrors", 0)}
- **Tests Run:** {result.get("numberTestsCompleted", 0)} / {result.get("numberTestsTotal", 0)}


### 📌 Deployment Metadata
- **Deployment ID:** {deployment_id}
- **Deployment URL:** [View Deployment]({deploy_url})
- **Artifact URL:** {artifact_url})
"""

# --- Process failures ---
failures = details.get("runTestResult", {}).get("failures", [])
coverage_warnings = details.get("runTestResult", {}).get("codeCoverageWarnings", [])
component_failures = details.get("componentFailures", [])

# Display processing visually with tqdm
total_items = len(component_failures) + len(failures) + len(coverage_warnings)
if total_items > 0:
    console.print("\n[bold yellow]Processing failure reports...[/bold yellow]")
    with tqdm(total=total_items, desc="Processing failures", colour="yellow") as pbar:
        if component_failures:
            summary += "\n\n### ❌ Component Failures\n| Type | File | Problem |\n|------|------|---------|\n"
            for cf in component_failures:
                summary += f"| {cf.get('componentType')} | `{cf.get('fileName')}` | {cf.get('problem')} |\n"
                pbar.update(1)
                time.sleep(0.01)  # Small delay for visual effect

        if failures:
            summary += "\n\n### ❌ Test Failures\n| Name | Method | Message |\n|------|--------|---------|\n"
            for failure in failures:
                summary += f"| `{failure['name']}` | `{failure['methodName']}` | {failure['message']} |\n"
                pbar.update(1)
                time.sleep(0.01)  # Small delay for visual effect

        if coverage_warnings:
            summary += "\n\n### ⚠️ Code Coverage Warnings\n| Name | Message |\n|------|---------|\n"
            for warning in coverage_warnings:
                summary += f"| `{warning['name']}` | {warning['message']} |\n"
                pbar.update(1)
                time.sleep(0.01)  # Small delay for visual effect

# Display the final summary with rich markdown
console.print("\n[bold blue]Generated Summary:[/bold blue]")
console.print(Markdown(summary))

# --- Inline Review Comments ---
comments = []
if component_failures:
    console.print("\n[bold yellow]Preparing review comments...[/bold yellow]")
    
    with tqdm(component_failures, desc="Processing component failures", colour="cyan") as pbar:
        for cf in pbar:
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
            pbar.set_description(f"Processing: {path}")
            time.sleep(0.05)  # Small delay for visual effect

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

# Show submission progress with rich progress bar
console.print(f"\n[bold yellow]📤 Submitting PR review as '{event}'...[/bold yellow]")

with Progress(
    SpinnerColumn(),
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    expand=True
) as progress:
    task = progress.add_task("[yellow]Submitting to GitHub API...", total=100)
    
    # Simulate progress steps
    progress.update(task, completed=30, description="[yellow]Preparing request...")
    time.sleep(0.3)
    progress.update(task, completed=50, description="[yellow]Sending to GitHub...")
    
    response = requests.post(review_url, headers=headers, json=review_payload)
    
    progress.update(task, completed=80, description="[yellow]Processing response...")
    time.sleep(0.2)
    progress.update(task, completed=100, description="[green]Request completed")

# Display the result
if response.status_code == 200 or response.status_code == 201:
    console.print(Panel.fit("[bold green]✅ Review submitted successfully![/bold green]"))
    if(result.get("success")):
        exit(0)
    else:
        exit(1)
else:
    console.print(Panel.fit(f"[bold white on red]❌ Failed to submit review: {response.status_code}[/bold white on red]"))
    console.print(Syntax(response.text, "json", theme="monokai"))
    exit(1)