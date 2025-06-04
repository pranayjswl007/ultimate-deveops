import os
import json
import requests
import sys

def fail(message, response=None):
    print(f"❌ {message}")
    if response is not None:
        print(response.text)
    sys.exit(1)

def create_promotion_pr(repo, head, base, source_pr, gh_pat):
    body = f"""Automatically created promotion from PR #{source_pr}

Original PR: #{source_pr}
Source branch: `{head}`
Target branch: `{base}`

This PR was created automatically by the promotion workflow."""

    payload = {
        "title": f"🚀 Promotion: {head} → {base}",
        "head": head,
        "base": base,
        "body": body
    }

    headers = {
        "Authorization": f"token {gh_pat}",
        "Accept": "application/vnd.github+json"
    }

    url = f"https://api.github.com/repos/{repo}/pulls"
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 201:
        fail("Failed to create promotion PR", response)

    pr_number = response.json().get("number")
    print(f"✅ Created promotion PR #{pr_number}")

    # Output to GitHub Actions
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"new_pr_number={pr_number}\n")

    return pr_number

def comment_and_close_original_pr(repo, original_pr, promo_branch, new_pr_number, gh_pat):
    comment_body = f"""🔁 **Promotion Created**

A promotion branch `{promo_branch}` has been created and a new PR #{new_pr_number} has been opened.

This PR is now being closed as the promotion workflow has taken over."""

    headers = {
        "Authorization": f"token {gh_pat}",
        "Accept": "application/vnd.github+json"
    }

    comment_url = f"https://api.github.com/repos/{repo}/issues/{original_pr}/comments"
    close_url = f"https://api.github.com/repos/{repo}/pulls/{original_pr}"

    # Post comment
    response = requests.post(comment_url, headers=headers, json={"body": comment_body})
    if response.status_code != 201:
        fail("Failed to comment on original PR", response)

    # Close PR
    response = requests.patch(close_url, headers=headers, json={"state": "closed"})
    if response.status_code != 200:
        fail("Failed to close original PR", response)

    print(f"✅ Original PR #{original_pr} commented and closed.")

if __name__ == "__main__":
    try:
        repo = os.environ["REPO"]
        promo_branch = os.environ["PROMO_BRANCH"]
        base_branch = os.environ["BASE_BRANCH"]
        original_pr = os.environ["SOURCE_PR"]
        gh_pat = os.environ["GH_PAT"]

        new_pr = create_promotion_pr(repo, promo_branch, base_branch, original_pr, gh_pat)
        comment_and_close_original_pr(repo, original_pr, promo_branch, new_pr, gh_pat)

    except KeyError as e:
        fail(f"Missing environment variable: {e}")
