import os
import json
import requests
import time
import subprocess
import re
from collections import defaultdict
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

# GraphQL endpoint
graphql_url = "https://api.github.com/graphql"
headers = {
    "Authorization": f"Bearer {github_token}",
    "Content-Type": "application/json"
}

def execute_graphql_query(query, variables=None):
    """Execute a GraphQL query/mutation"""
    payload = {
        "query": query,
        "variables": variables or {}
    }
    
    response = requests.post(graphql_url, json=payload, headers=headers)
    
    if response.status_code != 200:
        console.print(f"[red]❌ GraphQL request failed: {response.status_code}[/red]")
        console.print_json(data=response.json())
        return None
    
    result = response.json()
    if "errors" in result:
        console.print("[red]❌ GraphQL errors:[/red]")
        console.print_json(data=result["errors"])
        return None
    
    return result["data"]

# Delete old PMD comments using GraphQL
console.rule("[bold yellow]🧹 Cleaning up old PMD comments")

# First, get PR node ID and existing comments
get_pr_query = """
query GetPRInfo($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      id
      headRefOid
      baseRefOid
      reviews(first: 100) {
        nodes {
          id
          body
          comments(first: 100) {
            nodes {
              id
              body
            }
          }
        }
      }
      comments(first: 100) {
        nodes {
          id
          body
        }
      }
    }
  }
}
"""

owner, repo_name = github_repository.split('/')
pr_data = execute_graphql_query(get_pr_query, {
    "owner": owner,
    "name": repo_name,
    "number": int(pr_number)
})

if not pr_data:
    console.print("[red]❌ Failed to get PR information[/red]")
    exit(1)

pr_node_id = pr_data["repository"]["pullRequest"]["id"]
head_oid = pr_data["repository"]["pullRequest"]["headRefOid"]
console.print(f"[bold green]PR Node ID:[/bold green] {pr_node_id}")
console.print(f"[bold green]Head OID:[/bold green] {head_oid}")

# Delete old PMD comments
deleted_count = 0
comments_to_delete = []

# Check review comments
for review in pr_data["repository"]["pullRequest"]["reviews"]["nodes"]:
    if "🔍 **PMD Analysis**" in review.get("body", ""):
        comments_to_delete.append(("review", review["id"]))
    for comment in review["comments"]["nodes"]:
        if "🔍 **PMD Analysis**" in comment.get("body", "") or "| Detail" in comment.get("body", ""):
            comments_to_delete.append(("comment", comment["id"]))

# Check PR comments
for comment in pr_data["repository"]["pullRequest"]["comments"]["nodes"]:
    if "🔍 **PMD Analysis**" in comment.get("body", "") or "| Detail" in comment.get("body", ""):
        comments_to_delete.append(("issue_comment", comment["id"]))

# Delete comments in batches using GraphQL mutations
if comments_to_delete:
    console.print(f"[yellow]Found {len(comments_to_delete)} old PMD comments to delete[/yellow]")
    
    for comment_type, comment_id in comments_to_delete:
        if comment_type == "review":
            delete_mutation = """
            mutation DeleteReview($reviewId: ID!) {
              deleteReview(input: {reviewId: $reviewId}) {
                clientMutationId
              }
            }
            """
            result = execute_graphql_query(delete_mutation, {"reviewId": comment_id})
        elif comment_type == "comment":
            delete_mutation = """
            mutation DeleteComment($commentId: ID!) {
              deletePullRequestReviewComment(input: {id: $commentId}) {
                clientMutationId
              }
            }
            """
            result = execute_graphql_query(delete_mutation, {"commentId": comment_id})
        elif comment_type == "issue_comment":
            delete_mutation = """
            mutation DeleteIssueComment($commentId: ID!) {
              deleteIssueComment(input: {id: $commentId}) {
                clientMutationId
              }
            }
            """
            result = execute_graphql_query(delete_mutation, {"commentId": comment_id})
        
        if result:
            deleted_count += 1
        time.sleep(0.5)  # Small delay between deletions

console.print(f"[bold green]✅ Deleted {deleted_count} old PMD comment(s).[/bold green]")

# Get PR files using REST API (GraphQL doesn't provide patch data)
console.rule("[bold cyan]🗂️ Getting PR Files")

pr_files_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/files"
pr_files_headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

pr_files_response = requests.get(pr_files_url, headers=pr_files_headers)
if pr_files_response.status_code != 200:
    console.print(f"[red]❌ Failed to get PR files: {pr_files_response.status_code}[/red]")
    console.print_json(data=pr_files_response.json())
    exit(1)

pr_files = pr_files_response.json()
console.print(f"[bold green]✅ Found {len(pr_files)} changed files in PR[/bold green]")

# Build file mapping with line numbers that can accept comments
changed_files = {}
for file_data in pr_files:
    filename = file_data['filename']  # REST API uses 'filename' not 'path'
    # Only process files that have changes (not just renamed/moved)
    if file_data['status'] in ['added', 'modified'] and file_data.get('patch'):
        changed_files[filename] = {
            'patch': file_data['patch'],
            'valid_lines': set()
        }
        
# Build file mapping with line numbers and their diff positions
changed_files = {}
for file_data in pr_files:
    filename = file_data['filename']  # REST API uses 'filename' not 'path'
    # Only process files that have changes (not just renamed/moved)
    if file_data['status'] in ['added', 'modified'] and file_data.get('patch'):
        changed_files[filename] = {
            'patch': file_data['patch'],
            'valid_lines': set(),
            'line_to_position': {}  # Maps line number to diff position
        }
        
        # Parse patch to find lines that can receive comments and their positions
        patch_lines = file_data['patch'].split('\n')
        current_line = 0
        diff_position = 0
        
        for patch_line in patch_lines:
            if patch_line.startswith('@@'):
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                match = re.match(r'@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@', patch_line)
                if match:
                    current_line = int(match.group(1))
                # Hunk headers don't count as diff positions for comments
            elif patch_line.startswith('+') and not patch_line.startswith('+++'):
                # This is a new line that can receive comments
                diff_position += 1
                changed_files[filename]['valid_lines'].add(current_line)
                changed_files[filename]['line_to_position'][current_line] = diff_position
                current_line += 1
            elif patch_line.startswith(' '):
                # Context line
                diff_position += 1
                changed_files[filename]['valid_lines'].add(current_line)
                changed_files[filename]['line_to_position'][current_line] = diff_position
                current_line += 1
            elif patch_line.startswith('-'):
                # Deleted line - contributes to diff position but not to new line numbers
                diff_position += 1
            # Other lines (like file headers) don't affect position or line numbers

console.print(f"[bold green]✅ Processed {len(changed_files)} files with changes[/bold green]")

def normalize_file_path(raw_file_path):
    """Normalize file path to match PR files"""
    if "changed-sources/" in raw_file_path:
        try:
            normalized = raw_file_path.split("changed-sources/")[1]
        except IndexError:
            normalized = raw_file_path
    else:
        normalized = raw_file_path
    
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
    
    # Try partial path matching
    for available_file in available_files:
        if available_file.endswith(file_path) or file_path.endswith(available_file):
            return available_file
            
    return None

# Prepare inline comments for GraphQL review
console.rule("[bold cyan]🛠️ Preparing Inline Comments")
review_comments = []
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
        "line": line,
        "body": f"🔍 **PMD Analysis**\n\n{markdown_table}"
    }
    
    review_comments.append(comment_data)

# Limit to 20 comments for GraphQL review
if len(review_comments) > MAX_INLINE:
    overflow_from_limit = review_comments[MAX_INLINE:]
    review_comments = review_comments[:MAX_INLINE]
    
    # Convert excess comments to overflow format
    for comment in overflow_from_limit:
        overflow_comments.append({
            "type": "inline_overflow",
            "comment": comment
        })

console.print(Panel.fit(f"[bold yellow]💬 Prepared {len(review_comments)} inline comment(s), {len(overflow_comments)} overflow."))

# Post review with all inline comments using GraphQL
console.rule("[bold green]🚀 Submitting Review with Inline Comments")
if review_comments:
    create_review_mutation = """
    mutation CreateReview($pullRequestId: ID!, $commitOID: GitObjectID!, $body: String!, $comments: [DraftPullRequestReviewComment!]!) {
      addPullRequestReview(input: {
        pullRequestId: $pullRequestId,
        commitOID: $commitOID,
        body: $body,
        event: COMMENT,
        comments: $comments
      }) {
        pullRequestReview {
          id
          createdAt
          comments(first: 100) {
            totalCount
            nodes {
              id
              path
              line
            }
          }
        }
      }
    }
    """
    
    # Convert comments to GraphQL format
    graphql_comments = []
    for comment in review_comments:
        graphql_comments.append({
            "path": comment["path"],
            "position": comment["position"],  # Use position for GraphQL
            "body": comment["body"]
        })
    
    review_body = f"🔍 **PMD Analysis Results**\n\nFound {len(review_comments)} code quality issues in this PR."
    if overflow_comments:
        review_body += f" {len(overflow_comments)} additional violations are listed in the summary comment below."
    
    variables = {
        "pullRequestId": pr_node_id,
        "commitOID": head_oid,
        "body": review_body,
        "comments": graphql_comments
    }
    
    console.print(f"[dim]Creating review with {len(graphql_comments)} inline comments[/dim]")
    
    result = execute_graphql_query(create_review_mutation, variables)
    
    if result and result.get("addPullRequestReview"):
        review_data = result["addPullRequestReview"]["pullRequestReview"]
        comment_count = review_data["comments"]["totalCount"]
        console.print(f"[bold green]✅ Successfully created review with {comment_count} inline comments![/bold green]")
        console.print(f"[dim]Review ID: {review_data['id']}[/dim]")
    else:
        console.print("[bold red]❌ Failed to create review with inline comments[/bold red]")
        
        # Fallback: Add comments individually (but this defeats the purpose)
        console.print("[yellow]⚠️ Consider using REST API fallback if needed[/yellow]")

# Post overflow comments as summary
if overflow_comments:
    console.rule("[bold magenta]🗄️ Posting Overflow as Summary Comment")
    
    # Create issue comment using GraphQL
    create_comment_mutation = """
    mutation CreateIssueComment($subjectId: ID!, $body: String!) {
      addComment(input: {
        subjectId: $subjectId,
        body: $body
      }) {
        commentEdge {
          node {
            id
            createdAt
          }
        }
      }
    }
    """
    
    header = "| File | Line | Rule | Severity | Message |\n|------|------|----------|----------|----------|\n"
    body_rows = []
    
    for v in overflow_comments:
        # Handle both regular violations and inline overflow comments
        if v.get("type") == "inline_overflow":
            comment_data = v["comment"]
            file_path = comment_data["path"]
            position = comment_data["position"]
            
            # For display purposes, try to map position back to line number
            # This is approximate since we're going backwards
            line_no = "?"
            for filename, data in changed_files.items():
                if filename == file_path:
                    for line_num, pos in data['line_to_position'].items():
                        if pos == position:
                            line_no = line_num
                            break
            
            # Extract from comment body
            body = comment_data["body"]
            rule_match = re.search(r'\| Rule\s+\| ([^|]+) \|', body)
            severity_match = re.search(r'\| Severity \| ([^|]+) \|', body)
            message_match = re.search(r'\| Message\s+\| ([^|]+) \|', body)
            
            rule = rule_match.group(1).strip() if rule_match else "Unknown Rule"
            severity = severity_match.group(1).strip() if severity_match else "Unknown Severity"
            message = message_match.group(1).strip() if message_match else "No message"
            
            body_rows.append(f"| `{file_path}` | {line_no} | {rule} | {severity} | {message} |")
        else:
            # Regular violation
            locs = v.get("locations", [])
            loc = locs[v.get("primaryLocationIndex", 0)] if locs else {}
            file_path = normalize_file_path(loc.get("file", "Unknown"))
            line_no = loc.get("startLine", "?")
            
            rule = v.get("rule", "Unknown Rule")
            severity = v.get("severity", "Unknown Severity")
            message = v.get("message", "No message provided")
            url = v.get("resources", [""])[0] if v.get("resources") else ""
            
            rule_display = f"[{rule}]({url})" if url else rule
            message = str(message).replace("|", "\\|").replace("\n", " ")
            if len(message) > 100:
                message = message[:97] + "..."
            
            body_rows.append(f"| `{file_path}` | {line_no} | {rule_display} | {severity} | {message} |")
    
    overflow_table = header + "\n".join(body_rows)
    
    # Count different types of overflow
    regular_overflow = len([v for v in overflow_comments if v.get("type") != "inline_overflow"])
    limit_overflow = len([v for v in overflow_comments if v.get("type") == "inline_overflow"])
    
    overflow_title = "⚠️ **PMD Analysis Results**"
    if regular_overflow > 0 and limit_overflow > 0:
        overflow_title += f" ({regular_overflow} not mapped to changes, {limit_overflow} over {MAX_INLINE} comment limit)"
    elif regular_overflow > 0:
        overflow_title += f" ({regular_overflow} violations not mapped to changed lines)"
    elif limit_overflow > 0:
        overflow_title += f" ({limit_overflow} violations over {MAX_INLINE} comment limit)"
    
    comment_body = f"{overflow_title}\n\nThe following violations could not be posted as inline comments:\n\n{overflow_table}"
    
    variables = {
        "subjectId": pr_node_id,
        "body": comment_body
    }
    
    result = execute_graphql_query(create_comment_mutation, variables)
    
    if result and result.get("addComment"):
        comment_id = result["addComment"]["commentEdge"]["node"]["id"]
        console.print(f"[bold green]✅ Posted overflow summary comment![/bold green]")
        console.print(f"[dim]Comment ID: {comment_id}[/dim]")
    else:
        console.print("[bold red]❌ Failed to post overflow summary comment[/bold red]")

console.rule("[bold cyan]🏁 Done")