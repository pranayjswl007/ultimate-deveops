import os
import json
import requests
import time
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
    if "| Detail" in comment.get("body", ""):
        delete_url = comment["url"]
        del_response = requests.delete(delete_url, headers=headers)
        if del_response.status_code == 204:
            deleted += 1
        else:
            console.print(f"[red]⚠️ Failed to delete comment ID {comment['id']}[/red]")
console.print(f"[bold green]✅ Deleted {deleted} old PMD comment(s).")

# Fetch PR changed files and patches (for mapping violations to diff positions)
console.rule("[bold cyan]🗂️ Fetching PR Diff Files")
diff_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/files"
diff_response = requests.get(diff_url, headers=headers)
if diff_response.status_code != 200:
    console.print("[red]❌ Failed to fetch PR diff files[/red]")
    exit(1)
diff_files = diff_response.json()

def calculate_diff_position(patch, target_line):
    """Given a unified diff `patch` and a `target_line` in the new file,
    return the position index (0-based) used by GitHub's PR comment API."""
    position = 0
    current_line = None
    for line in patch.splitlines():
        if line.startswith('@@'):
            # e.g., @@ -5,10 +5,20 @@
            parts = line.split(' ')
            new_file_range = parts[2]  # "+5,20"
            new_file_start = int(new_file_range.split(',')[0][1:])
            current_line = new_file_start
            position += 1
        elif line.startswith('+'):
            if current_line == target_line:
                return position
            current_line += 1
            position += 1
        elif line.startswith('-'):
            position += 1  # Still counts for position, but not line number
        else:
            if current_line is not None:
                current_line += 1
            position += 1
    return None

# Prepare inline comments (with positions)
console.rule("[bold cyan]🛠️ Preparing Inline Comments")
line_comments = []
overflow_comments = []
MAX_INLINE = 20

for v in violations:
    primary_index = v.get("primaryLocationIndex", 0)
    locs = v.get("locations", [])
    if primary_index >= len(locs):
        overflow_comments.append(v)
        continue
    
    loc = locs[primary_index]
    raw_file = loc.get("file", "")
    # Map to repo-relative file path (should match PR diff "filename")
    try:
        file_path = raw_file.split("changed-sources/")[1]
    except IndexError:
        file_path = raw_file

    line = loc.get("startLine", 1)
    if not isinstance(line, int) or line < 1:
        line = 1

    # Find matching patch for this file
    patch = None
    for file in diff_files:
        if file.get("filename") == file_path:
            patch = file.get("patch")
            break
    
    if not patch:
        overflow_comments.append(v)
        continue
    
    position = calculate_diff_position(patch, line)
    if position is None:
        overflow_comments.append(v)
        continue

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
    
    line_comments.append({
        "path": file_path,
        "position": position,
        "commit_id": commit_id,
        "body": f"\n\n{markdown_table}"
    })

console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(line_comments)} valid inline comment(s), {len(overflow_comments)} overflow."))

# Only post up to MAX_INLINE inline, rest as summary
inline_to_post = line_comments[:MAX_INLINE]
overflow_comments += line_comments[MAX_INLINE:]

# Post inline comments
console.rule("[bold green]🚀 Submitting Inline Comments")
if inline_to_post:
    post_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
    success = 0
    errors = 0

    with tqdm(total=len(inline_to_post), desc="Posting Inline", ncols=80) as pbar:
        for c in inline_to_post:
            while True:
                response = requests.post(post_url, json=c, headers=headers)
                if response.status_code == 201:
                    success += 1
                    break
                elif response.status_code == 403:
                    resp_json = response.json()
                    msg = resp_json.get("message", "")
                    if "secondary rate limit" in msg.lower():
                        console.print("[yellow]⚠️ Hit GitHub secondary rate limit. Sleeping 30s…[/yellow]")
                        time.sleep(30)
                        continue
                    else:
                        errors += 1
                        console.print(f"[red]❌ 403 on {c['path']} (position {c['position']}): {msg}[/red]")
                        break
                else:
                    errors += 1
                    console.print(f"[red]❌ Failed to post on {c['path']} (position {c['position']}) – {response.status_code}[/red]")
                    console.print_json(data=response.json())
                    break
            time.sleep(1)
            pbar.update(1)

    console.rule("[bold cyan]📊 Inline Summary")
    console.print(f"[bold green]✅ {success} inline comment(s) posted.[/bold green]")
    if errors:
        console.print(f"[bold red]⚠️ {errors} inline comment(s) failed.[/bold red]")

# Overflow comments as one summary comment (if any)
if overflow_comments:
    console.rule("[bold magenta]🗄️ Posting Overflow as Table")
    header = "| File | Line | Rule | Severity | Message |\n|------|------|------|----------|----------|\n"
    body_rows = []
    
    for v in overflow_comments:
        # Handle both violation objects and line_comment objects
        if isinstance(v, dict) and "path" in v:
            # This is from line_comments overflow
            file_path = v["path"]
            line_no = "?"  # Position-based, no line number stored
            # Extract from body or use defaults
            rule = "Unknown Rule"
            severity = "Unknown Severity"
            message = "See inline comment details"
            url = ""
        else:
            # This is a violation object
            locs = v.get("locations", [])
            loc = locs[v.get("primaryLocationIndex", 0)] if locs else {}
            file_path = loc.get("file", "Unknown")
            try:
                file_path = file_path.split("changed-sources/")[1]
            except IndexError:
                pass
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
        f"⚠️ **PMD Analysis Results** ({len(overflow_comments)} violations not mapped to diff or over limit)\n\n"
        "The following violations could not be posted inline due to diff mapping or quantity limits:\n\n" +
        overflow_table
    }
    
    resp2 = requests.post(issues_comment_url, json=overflow_payload, headers=headers)
    if resp2.status_code == 201:
        console.print("[bold green]✅ Overflow table comment posted successfully![/bold green]")
    else:
        console.print(f"[bold red]❌ Failed to post overflow table comment: {resp2.status_code}[/bold red]")
        console.print_json(data=resp2.json())

console.rule("[bold cyan]🏁 Done")