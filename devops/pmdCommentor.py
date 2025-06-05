import os
import json
import requests
import time
from collections import defaultdict
from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel

# ────────────────────────────────────────────────────────────────────────────────
# Rich console
console = Console()

# Environment variables
pr_number         = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token      = os.environ.get('TOKEN_GITHUB')
commit_id         = os.environ.get('COMMIT_ID')

console.rule("[bold cyan]GitHub Context")
console.print(f"[bold green]Repository:[/bold green] {github_repository}")
console.print(f"[bold green]PR Number:[/bold green] {pr_number}")
console.print(f"[bold green]Commit ID:[/bold green] {commit_id}")

pmd_violations_file = "apexScanResults.json"

# ────────────────────────────────────────────────────────────────────────────────
# Load scan results
try:
    with open(pmd_violations_file, "r") as file:
        scan_results = json.load(file)
        console.print_json(data=scan_results)
        violations = scan_results.get("violations", [])
        console.print(f"[bold green]✅ Loaded {len(violations)} violation(s).[/bold green]")
except (FileNotFoundError, json.JSONDecodeError) as e:
    console.print(f"[bold red]❌ Error reading {pmd_violations_file}: {e}[/bold red]")
    exit(1)

# ────────────────────────────────────────────────────────────────────────────────
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
    if "| Detail | Value |" in comment.get("body", ""):
        delete_url = comment["url"]
        del_response = requests.delete(delete_url, headers=headers)
        if del_response.status_code == 204:
            deleted += 1
        else:
            console.print(f"[red]⚠️ Failed to delete comment ID {comment['id']}[/red]")

console.print(f"[bold green]✅ Deleted {deleted} old PMD comment(s).")

# ────────────────────────────────────────────────────────────────────────────────
# Step 2: Prepare grouped line‐level comments
console.rule("[bold cyan]🛠️ Preparing Line Comments")
line_comments = []

for v in violations:
    primary_index = v.get("primaryLocationIndex", 0)
    if not isinstance(primary_index, int) or primary_index >= len(v.get("locations", [])):
        continue

    loc = v.get("locations", [{}])[primary_index]
    raw_file = loc.get("file", "")
    try:
        file_path = raw_file.split("changed-sources/")[1]
    except IndexError:
        file_path = raw_file

    line = loc.get("startLine", 1)
    if not isinstance(line, int) or line < 1:
        line = 1

    message = v.get("message", "No message provided").replace("|", "\\|")
    rule     = v.get("rule", "Unknown Rule")
    engine   = v.get("engine", "Unknown Engine")
    severity = v.get("severity", "Unknown Severity")
    url      = v.get("resources", [""])[0] if v.get("resources") else ""

    markdown_table = (
        "| Detail   | Value |\n"
        "|----------|-------|\n"
        f"| Rule     | {rule} |\n"
        f"| Engine   | {engine} |\n"
        f"| Severity | {severity} |\n"
        f"| Message  | {message} |\n"
        f"| More Info| [link]({url}) |"
    )

    if not file_path:
        console.print(f"[red]⚠️ File path is empty for violation: {v}[/red]")
        continue

    line_comments.append({
        "path":      file_path,
        "line":      line,
        "side":      "RIGHT",
        "commit_id": commit_id,
        "body":      f"\n\n{markdown_table}"
    })

console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(line_comments)} line comment(s)."))

# ────────────────────────────────────────────────────────────────────────────────
# If there are no violations, exit early.
if not line_comments:
    console.print("[bold green]✅ No inline violations to post. Exiting.[/bold green]")
    exit(0)

# ────────────────────────────────────────────────────────────────────────────────
# Step 3: Decide whether to inline‐post all, or inline‐post only first 20 + overflow
MAX_INLINE = 20
inline_comments   = line_comments[:MAX_INLINE]
overflow_comments = line_comments[MAX_INLINE:]

console.print(f"[bold blue]ℹ️ Will post {len(inline_comments)} inline comment(s).[/bold blue]")
if overflow_comments:
    console.print(f"[bold yellow]⚠️ {len(overflow_comments)} violations left over; " +
                  "they will be grouped into one table comment.[/bold yellow]")

# ────────────────────────────────────────────────────────────────────────────────
# Step 4: Post up to MAX_INLINE line‐level comments one by one, with back‐off
console.rule("[bold green]🚀 Submitting Up to 20 Inline Comments")
post_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"
success = 0
errors  = 0

# Print out for debugging/payload inspection
print(json.dumps(inline_comments, indent=2))

with tqdm(total=len(inline_comments), desc="Posting Inline Comments", ncols=80) as pbar:
    for idx, c in enumerate(inline_comments, start=1):
        while True:
            response = requests.post(post_url, json=c, headers=headers)

            # 201 => Created successfully
            if response.status_code == 201:
                success += 1
                break

            # 403 with secondary rate‐limit message => back off and retry
            elif response.status_code == 403:
                resp_json = response.json()
                msg = resp_json.get("message", "")
                if "secondary rate limit" in msg.lower():
                    console.print("[yellow]⚠️ Hit GitHub secondary rate limit. Sleeping 30s…[/yellow]")
                    time.sleep(30)
                    continue
                else:
                    # Some other 403 (e.g. permission issue)
                    errors += 1
                    console.print(f"[red]❌ 403 on {c['path']} (line {c['line']}): {msg}[/red]")
                    break

            # Any other non‐201 is a permanent failure for this comment
            else:
                errors += 1
                console.print(
                    f"[red]❌ Failed to post comment on {c['path']} (line {c['line']}) – Status {response.status_code}[/red]"
                )
                console.print_json(data=response.json())
                break

        # After either success (201) or permanent failure, pause before next POST
        time.sleep(1)
        pbar.update(1)

console.rule("[bold cyan]📊 Inline Summary")
console.print(f"[bold green]✅ {success} inline comment(s) successfully posted.[/bold green]")
if errors:
    console.print(f"[bold red]⚠️ {errors} inline comment(s) failed.[/bold red]")

# ────────────────────────────────────────────────────────────────────────────────
# Step 5: If there are overflow_comments, group them into one Markdown table
if overflow_comments:
    console.rule("[bold magenta]🗄️ Posting Overflow as One Table Comment")
    # Build a single Markdown table containing all overflow entries.
    # We’ll use columns: File | Line | Rule | Message
    header   = "| File | Line | Rule | Message |\n|------|------|------|---------|\n"
    body_rows = []
    for oc in overflow_comments:
        # The original `body` starts with "\n\n| Detail ...". We only want the Rule and Message fields,
        # so we can extract those from the markdown_table that we built earlier.
        # But for simplicity, let’s just flatten the entire markdown_table into one cell. That still
        # satisfies “a single table comment,” albeit with a bigger cell.
        entire_md_table = oc["body"].strip()  # that starts with "| Detail | Value |..."
        # Escape any pipe in the table so it doesn’t break the outer table structure:
        cell_md = entire_md_table.replace("|", "\\|")
        file_path = oc["path"]
        line_no   = oc["line"]
        body_rows.append(f"| `{file_path}` | {line_no} | {cell_md} |")

    overflow_table = header + "\n".join(body_rows)

    # Finally, post as a general PR comment (not inline). Use the Issues API endpoint:
    issues_comment_url = f"https://api.github.com/repos/{github_repository}/issues/{pr_number}/comments"
    overflow_payload = {"body": 
        "⚠️ **Too many PMD violations to post inline.**\n\n"
        "Below is a combined table of the remaining violations:\n\n" +
        overflow_table
    }

    resp2 = requests.post(issues_comment_url, json=overflow_payload, headers=headers)
    if resp2.status_code == 201:
        console.print("[bold green]✅ Overflow table comment posted successfully![/bold green]")
    else:
        console.print(f"[bold red]❌ Failed to post overflow table comment: {resp2.status_code}[/bold red]")
        console.print_json(data=resp2.json())

# ────────────────────────────────────────────────────────────────────────────────
console.rule("[bold cyan]🏁 Done")
