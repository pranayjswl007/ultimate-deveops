import os
import json
import requests
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
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

# Load PMD results
try:
    with open(pmd_violations_file, "r") as file:
        pmd_violations = json.load(file)
        console.print(f"[bold green]✅ Loaded {len(pmd_violations)} file(s) with violations.[/bold green]")
except FileNotFoundError:
    console.print(f"[bold red on cyan]❌ Error: The file '{pmd_violations_file}' was not found.[/bold red on cyan]")
    exit(1)
except json.JSONDecodeError:
    console.print(f"[bold red on cyan]❌ Error: Invalid JSON in '{pmd_violations_file}'.[/bold red on cyan]")
    exit(1)

# Prepare comments
comments = []
for violation in pmd_violations:
    try:
        file_path = violation["fileName"].split("changed-sources/")[1]
    except IndexError:
        file_path = violation["fileName"]

    for vo in violation["violations"]:
        line_number = vo["line"]
        end_line = vo.get("endLine", line_number)
        if end_line == line_number:
            end_line = line_number + 1

        comment = {
            "path": file_path,
            "line": line_number,
            "side": "RIGHT",
            "commit_id": commit_id,
            "body": f"PMD Violation: {vo['message']}"
        }
        comments.append(comment)

console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(comments)} inline comment(s)."))

# GitHub API setup
headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github.v3+json"
}
api_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"

# Send comments with progress
console.rule("[bold cyan]Submitting Review Comments")
success_count = 0
with tqdm(total=len(comments), desc="Posting Comments", ncols=80) as pbar:
    for comment in comments:
        response = requests.post(api_url, json=comment, headers=headers)
        if response.status_code == 201:
            success_count += 1
            if(success_count % 10 == 0):
               time.sleep(1)
        else:
            console.print(f"[red]❌ Failed to create comment[/red] [bold](Status {response.status_code})[/bold]")
            console.print_json(data=response.json())
            exit(1)
        pbar.update(1)

# Summary
console.rule("[bold green]✅ PMD Commentor Summary")
console.print(f"[bold green]🎉 {success_count} comment(s) successfully posted![/bold green]")
