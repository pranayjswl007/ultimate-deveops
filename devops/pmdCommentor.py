import os
import json
import requests
import time
from collections import defaultdict
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

console.rule("[bold cyan]GitHub Context")
console.print(f"[bold green]Repository:[/bold green] {github_repository}")
console.print(f"[bold green]PR Number:[/bold green] {pr_number}")
console.print(f"[bold green]Commit ID:[/bold green] {commit_id}")

pmd_violations_file = "apexScanResults.json"

# Load scan results
try:
    with open(pmd_violations_file, "r") as file:
        scan_results = json.load(file)
        violations = scan_results.get("violations", [])
        console.print(f"[bold green]✅ Loaded {len(violations)} violation(s).[/bold green]")
except (FileNotFoundError, json.JSONDecodeError) as e:
    console.print(f"[bold red]❌ Error reading {pmd_violations_file}: {e}[/bold red]")
    exit(1)

# Step 1: Delete old inline PMD comments
console.rule("[bold yellow]🧹 Cleaning up old PMD comments")
comments_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

response = requests.get(comments_url, headers=headers)
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

# Step 2: Prepare grouped line-level comments
console.rule("[bold cyan]🛠️ Preparing Line Comments")
line_comments = []

violations_by_file = defaultdict(list)
for v in violations:
    primary_index = v.get("primaryLocationIndex", 0)
    if primary_index >= len(v["locations"]):
        continue

    loc = v["locations"][primary_index]
    raw_file = loc.get("file", "")
    try:
        file_path = raw_file.split("changed-sources/")[1]
    except IndexError:
        file_path = raw_file

    line = loc.get("startLine", 1)
    message = v.get("message", "")
    rule = v.get("rule", "")
    body = f"PMD Violation: **{rule}**\n\n{message}"
    if v.get("resources"):
        body += f"\n\n[More Info]({v['resources'][0]})"

    line = loc.get("startLine", 1)
    rule = v.get("rule", "")
    engine = v.get("engine", "")
    severity = v.get("severity", "")
    message = v.get("message", "").replace("|", "\\|")  # Escape pipes in message
    url = v.get("resources", [""])[0]

    markdown_table = (
        "| Rule | Engine | Severity | Message | More Info |\n"
        "|------|--------|----------|---------|-----------|\n"
        f"| {rule} | {engine} | {severity} | {message} | [{url}]({url}) |"
    )

    line_comments.append({
        "path": file_path,
        "line": line,
        "side": "RIGHT",
        "commit_id": commit_id,
        "body": f"PMD Violation:\n\n{markdown_table}"
    })
console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(line_comments)} line comment(s)."))

# Step 3: Post line-level comments
console.rule("[bold green]🚀 Submitting Line Comments")
post_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
success = 0
errors = 0

with tqdm(total=len(line_comments), desc="Posting Comments", ncols=80) as pbar:
    for c in line_comments:
        response = requests.post(post_url, json=c, headers=headers)
        if response.status_code == 201:
            success += 1
        else:
            errors += 1
            console.print(f"[red]❌ Failed to post comment on {c['path']} (line {c['line']})[/red]")
            console.print_json(data=response.json())
        pbar.update(1)
        if success % 10 == 0:
            time.sleep(1)

console.rule("[bold cyan]📊 Summary")
console.print(f"[bold green]✅ {success} comment(s) successfully posted.[/bold green]")
if errors:
    console.print(f"[bold red]⚠️ {errors} comment(s) failed. Likely not part of PR diff.[/bold red]")
