import os
import json
import requests
import time
import subprocess
import re
from collections import defaultdict
from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel

console = Console()

pr_number         = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token      = os.environ.get('TOKEN_GITHUB')
commit_id         = os.environ.get('COMMIT_ID')

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
        console.print_json(data=scan_results)
        console.print(f"[bold green]✅ Loaded {len(violations)} violation(s).[/bold green]")
except (FileNotFoundError, json.JSONDecodeError) as e:
    console.print(f"[bold red]❌ Error reading {pmd_violations_file}: {e}[/bold red]")
    exit(1)

# Delete old PMD inline comments
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
    if "🔍 **PMD Analysis**" in comment.get("body", "") or "| Detail" in comment.get("body", ""):
        delete_url = comment["url"]
        del_response = requests.delete(delete_url, headers=headers)
        if del_response.status_code == 204:
            deleted += 1
        else:
            console.print(f"[red]⚠️ Failed to delete comment ID {comment['id']}[/red]")
console.print(f"[bold green]✅ Deleted {deleted} old PMD comment(s).")

# Get PR information to get base and head branches
console.rule("[bold cyan]🔍 Getting PR Information")
pr_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}"
pr_response = requests.get(pr_url, headers=headers)
if pr_response.status_code != 200:
    console.print("[red]❌ Failed to fetch PR information[/red]")
    exit(1)

pr_data = pr_response.json()
base_ref = pr_data['base']['ref']
head_ref = pr_data['head']['ref']
base_sha = pr_data['base']['sha']
head_sha = pr_data['head']['sha']
console.print(f"[bold green]Base branch:[/bold green] {base_ref} ({base_sha[:8]})")
console.print(f"[bold green]Head branch:[/bold green] {head_ref} ({head_sha[:8]})")

# Get PR files using GitHub API (more reliable than git diff)
console.rule("[bold cyan]🗂️ Getting PR Files")
pr_files_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/files"
pr_files_response = requests.get(pr_files_url, headers=headers)
if pr_files_response.status_code != 200:
    console.print(f"[red]❌ Failed to fetch PR files: {pr_files_response.status_code}[/red]")
    exit(1)

pr_files = pr_files_response.json()
console.print(f"[bold green]✅ Found {len(pr_files)} changed files in PR[/bold green]")

# Build file mapping with line numbers that can accept comments
changed_files = {}
for file_data in pr_files:
    filename = file_data['filename']
    # Only process files that have changes (not just renamed/moved)
    if file_data['status'] in ['added', 'modified'] and file_data.get('patch'):
        changed_files[filename] = {
            'patch': file_data['patch'],
            'valid_lines': set()
        }
        
        # Parse patch to find lines that can receive comments
        patch_lines = file_data['patch'].split('\n')
        current_line = 0
        
        for line in patch_lines:
            if line.startswith('@@'):
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                match = re.match(r'@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith('+') and not line.startswith('+++'):
                # This is a new line that can receive comments
                changed_files[filename]['valid_lines'].add(current_line)
                current_line += 1
            elif line.startswith(' '):
                # Context line
                changed_files[filename]['valid_lines'].add(current_line)
                current_line += 1
            # Lines starting with '-' don't increment current_line

console.print(f"[bold green]✅ Processed {len(changed_files)} files with changes[/bold green]")
for filename, data in changed_files.items():
    console.print(f"[dim]  - {filename}: {len(data['valid_lines'])} commentable lines[/dim]")

def normalize_file_path(raw_file_path):
    """Normalize file path to match PR files"""
    if "changed-sources/" in raw_file_path:
        try:
            normalized = raw_file_path.split("changed-sources/")[1]
        except IndexError:
            normalized = raw_file_path
    else:
        normalized = raw_file_path
    
    # Remove common prefixes
    prefixes_to_remove = ["./", "/"]
    for prefix in prefixes_to_remove:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    
    return normalized

def find_matching_file(file_path, available_files):
    """Find the best matching file from PR files"""
    file_path = normalize_file_path(file_path)
    
    # Direct match
    if file_path in available_files:
        return file_path
    
    # Try filename only match
    filename = file_path.split('/')[-1]
    for available_file in available_files:
        if available_file.endswith('/' + filename) or available_file == filename:
            return available_file
    
    # Try partial path matching (end matching)
    for available_file in available_files:
        if available_file.endswith(file_path) or file_path.endswith(available_file):
            return available_file
            
    return None

# Prepare inline comments
console.rule("[bold cyan]🛠️ Preparing Inline Comments")
line_comments = []
overflow_comments = []
MAX_INLINE = 20

for i, v in enumerate(violations):
    console.print(f"[dim]Processing violation {i+1}/{len(violations)}[/dim]")
    
    primary_index = v.get("primaryLocationIndex", 0)
    locs = v.get("locations", [])
    if primary_index >= len(locs):
        console.print(f"[yellow]Violation {i+1}: Invalid primary location index[/yellow]")
        overflow_comments.append(v)
        continue
    
    loc = locs[primary_index]
    raw_file = loc.get("file", "")
    
    # Find the matching file in our PR files
    matched_file = find_matching_file(raw_file, changed_files.keys())
    if not matched_file:
        console.print(f"[yellow]Violation {i+1}: No matching PR file for {raw_file}[/yellow]")
        console.print(f"[yellow]  Available files: {list(changed_files.keys())[:3]}...[/yellow]")
        overflow_comments.append(v)
        continue
    
    line = loc.get("startLine")
    if not isinstance(line, int) or line < 1:
        line = loc.get("line", 1)
        if not isinstance(line, int) or line < 1:
            line = 1
    
    # Check if this line can receive comments
    valid_lines = changed_files[matched_file]['valid_lines']
    if line not in valid_lines:
        console.print(f"[yellow]Violation {i+1}: Line {line} not in valid lines for {matched_file}[/yellow]")
        console.print(f"[yellow]  Valid lines: {sorted(list(valid_lines))[:10]}...[/yellow]")
        overflow_comments.append(v)
        continue
    
    console.print(f"[green]Violation {i+1}: Found valid line {line} for {matched_file}[/green]")
    
    # Extract violation details
    message = v.get("message", "No message provided").replace("|", "\\|")
    rule = v.get("rule", "Unknown Rule")
    engine = v.get("engine", "Unknown Engine")
    severity = v.get("severity", "Unknown Severity")
    url = v.get("resources", [""])[0] if v.get("resources") else ""
    
    # Make rule name a hyperlink if URL is available
    rule_display = f"[{rule}]({url})" if url else rule
    
    markdown_table = (
        "| Detail   | Value |\n"
        "|----------|-------|\n"
        f"| Rule     | {rule_display} |\n"
        f"| Engine   | {engine} |\n"
        f"| Severity | {severity} |\n"
        f"| Message  | {message} |"
    )
    
    comment_data = {
        "path": matched_file,
        "line": line,  # Use line instead of position for simplicity
        "body": f"🔍 **PMD Analysis**\n\n{markdown_table}"
    }
    
    line_comments.append(comment_data)

console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(line_comments)} valid inline comment(s), {len(overflow_comments)} overflow."))

# Post inline comments
console.rule("[bold green]🚀 Submitting Inline Comments")
if line_comments:
    # Use the review API for better reliability
    review_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/reviews"
    
    # Prepare review with inline comments
    review_data = {
        "commit_id": commit_id,
        "body": f"🔍 **PMD Analysis Results**\n\nFound {len(line_comments)} code quality issues in this PR.",
        "event": "COMMENT",
        "comments": line_comments
    }
    
    console.print(f"[dim]Posting review with {len(line_comments)} inline comments[/dim]")
    response = requests.post(review_url, json=review_data, headers=headers)
    
    if response.status_code == 200:
        console.print(f"[bold green]✅ Successfully posted review with {len(line_comments)} inline comments![/bold green]")
    else:
        console.print(f"[bold red]❌ Failed to post review: {response.status_code}[/bold red]")
        console.print_json(data=response.json())
        
        # Fallback: try posting individual comments
        console.print("[yellow]⚠️ Falling back to individual comment posting...[/yellow]")
        post_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
        success = 0
        errors = 0
        
        for i, comment in enumerate(line_comments):
            # Add commit_id for individual comments
            comment["commit_id"] = commit_id
            
            response = requests.post(post_url, json=comment, headers=headers)
            if response.status_code == 201:
                success += 1
                console.print(f"[green]✅ Posted individual comment {i+1}[/green]")
            else:
                errors += 1
                console.print(f"[red]❌ Failed individual comment {i+1}: {response.status_code}[/red]")
                if response.status_code == 422:
                    console.print(f"[red]  Error: {response.json()}[/red]")
            time.sleep(1)
        
        console.print(f"[bold yellow]Fallback results: {success} success, {errors} errors[/bold yellow]")

# Overflow comments as one summary comment (if any)
if overflow_comments:
    console.rule("[bold magenta]🗄️ Posting Overflow as Table")
    header = "| File | Line | Rule | Severity | Message |\n|------|------|----------|----------|----------|\n"
    body_rows = []
    
    for v in overflow_comments:
        # Extract violation details
        locs = v.get("locations", [])
        loc = locs[v.get("primaryLocationIndex", 0)] if locs else {}
        file_path = normalize_file_path(loc.get("file", "Unknown"))
        line_no = loc.get("startLine", "?")
        
        rule = v.get("rule", "Unknown Rule")
        severity = v.get("severity", "Unknown Severity")
        message = v.get("message", "No message provided")
        url = v.get("resources", [""])[0] if v.get("resources") else ""
        
        # Make rule a hyperlink if URL is available
        rule_display = f"[{rule}]({url})" if url else rule
        
        # Clean up message for table display
        message = str(message).replace("|", "\\|").replace("\n", " ")
        if len(message) > 100:
            message = message[:97] + "..."
        
        body_rows.append(f"| `{file_path}` | {line_no} | {rule_display} | {severity} | {message} |")
    
    overflow_table = header + "\n".join(body_rows)
    issues_comment_url = f"https://api.github.com/repos/{github_repository}/issues/{pr_number}/comments"
    overflow_payload = {"body": 
        f"⚠️ **PMD Analysis Results** ({len(overflow_comments)} violations not mapped to changed lines)\n\n"
        "The following violations could not be posted inline because they don't correspond to lines changed in this PR:\n\n" +
        overflow_table
    }
    
    resp2 = requests.post(issues_comment_url, json=overflow_payload, headers=headers)
    if resp2.status_code == 201:
        console.print("[bold green]✅ Overflow table comment posted successfully![/bold green]")
    else:
        console.print(f"[bold red]❌ Failed to post overflow table comment: {resp2.status_code}[/bold red]")
        console.print_json(data=resp2.json())

console.rule("[bold cyan]🏁 Done")