import os
import json
import requests
import time
from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel

# Rich console
console = Console()

# Environment variables
pr_number = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token = os.environ.get('TOKEN_GITHUB')
commit_id = os.environ.get('COMMIT_ID')

# Print environment info
console.rule("[bold cyan]GitHub Context")
console.print(f"[bold green]Repository:[/bold green] {github_repository}")
console.print(f"[bold green]PR Number:[/bold green] {pr_number}")
console.print(f"[bold green]Commit ID:[/bold green] {commit_id}")

# PMD results file
pmd_violations_file = "apexScanResults.json"

# Load scan results
try:
    with open(pmd_violations_file, "r") as file:
        scan_results = json.load(file)
        violations = scan_results.get("violations", [])
        console.print(f"[bold green]✅ Loaded {len(violations)} violation(s).[/bold green]")
except FileNotFoundError:
    console.print(f"[bold red on cyan]❌ Error: The file '{pmd_violations_file}' was not found.[/bold red on cyan]")
    exit(1)
except json.JSONDecodeError:
    console.print(f"[bold red on cyan]❌ Error: Invalid JSON in '{pmd_violations_file}'.[/bold red on cyan]")
    exit(1)

# Step 1: Remove old PMD-related comments
console.rule("[bold yellow]🧹 Cleaning up old PMD comments")
list_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

response = requests.get(list_url, headers=headers)
if response.status_code != 200:
    console.print(f"[red]❌ Failed to fetch PR comments: {response.status_code}[/red]")
    console.print_json(data=response.json())
    exit(1)

comments_data = response.json()
deleted = 0
for comment in comments_data:
    if "PMD Violation:" in comment.get("body", ""):
        delete_url = comment["url"]
        del_response = requests.delete(delete_url, headers=headers)
        if del_response.status_code == 204:
            deleted += 1
        else:
            console.print(f"[red]⚠️ Failed to delete comment ID {comment['id']}[/red]")

console.print(f"[bold green]✅ Deleted {deleted} old PMD comment(s).")

# Step 2: Prepare new comments
comments = []
for v in violations:
    primary_index = v.get("primaryLocationIndex", 0)
    if primary_index >= len(v["locations"]):
        console.print(f"[yellow]⚠️ Skipping violation due to invalid primaryLocationIndex: {primary_index}[/yellow]")
        continue

    location = v["locations"][primary_index]
    file_path = location["file"]
    line_number = location["startLine"]
    end_line = location.get("endLine", line_number)
    if end_line == line_number:
        end_line = line_number + 1

    message = f"PMD Violation: {v['message']}"
    if v.get("resources"):
        message += "\n\nReferences:\n" + "\n".join(v["resources"])

    comment = {
        "path": file_path,
        "line": line_number,
        "side": "RIGHT",
        "commit_id": commit_id,
        "body": message
    }
    comments.append(comment)

console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(comments)} new comment(s)."))

# Step 3: Submit new comments
api_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
console.rule("[bold cyan]🚀 Submitting Review Comments")
success_count = 0
with tqdm(total=len(comments), desc="Posting Comments", ncols=80) as pbar:
    for comment in comments:
        response = requests.post(api_url, json=comment, headers=headers)
        if response.status_code == 201:
            success_count += 1
        else:
            console.print(f"[red]❌ Failed to create comment (Status {response.status_code})[/red]")
            console.print_json(data=response.json())
            exit(1)
        pbar.update(1)
        if success_count % 10 == 0:
            time.sleep(1)

# Final Summary
console.rule("[bold green]✅ PMD Commentor Summary")
console.print(f"[bold green]🎉 {success_count} new comment(s) successfully posted![/bold green]")
