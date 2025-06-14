import os
import json
import requests
import sys
import time

def fail(message, response=None):
    print(f"❌ {message}")
    if response is not None:
        print(response.text)
    sys.exit(1)

def get_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

def find_existing_promotion_pr(repo, head, base, gh_pat):
    """Check if a promotion PR already exists for this head->base combination"""
    url = f"https://api.github.com/repos/{repo}/pulls"
    params = {
        "head": f"{repo.split('/')[0]}:{head}",  # owner:branch_name
        "base": base,
        "state": "open"
    }
    
    response = requests.get(url, headers=get_headers(gh_pat), params=params)
    
    if response.status_code != 200:
        print(f"⚠️ Warning: Could not search for existing PRs: {response.status_code}")
        return None
    
    prs = response.json()
    if prs:
        existing_pr = prs[0]  # Get the first matching PR
        pr_number = existing_pr.get("number")
        print(f"ℹ️ Found existing promotion PR #{pr_number} for {head} → {base}")
        return pr_number
    
    return None

def close_existing_promotion_pr(repo, pr_number, gh_pat, reason="Recreating promotion PR with new changes"):
    """Close an existing promotion PR"""
    
    # Add a comment explaining why it's being closed
    comment_body = f"""### 🔄 Promotion PR Update

This promotion PR is being closed and recreated to include new changes.

**Reason:** {reason}

A new promotion PR will be created shortly with the latest changes.

---

_Managed by Auto Promotion Bot_
"""

    # Add comment
    response = requests.post(
        f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
        headers=get_headers(gh_pat),
        json={"body": comment_body}
    )
    if response.status_code != 201:
        print(f"⚠️ Warning: Could not comment on existing PR #{pr_number}")
    
    # Close the PR
    response = requests.patch(
        f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
        headers=get_headers(gh_pat),
        json={"state": "closed"}
    )
    
    if response.status_code == 200:
        print(f"✅ Closed existing promotion PR #{pr_number}")
    else:
        print(f"⚠️ Warning: Could not close existing PR #{pr_number}: {response.status_code}")

def delete_branch(repo, branch_name, gh_pat):
    """Delete a branch from the repository"""
    response = requests.delete(
        f"https://api.github.com/repos/{repo}/git/refs/heads/{branch_name}",
        headers=get_headers(gh_pat)
    )
    
    if response.status_code == 204:
        print(f"✅ Deleted branch: {branch_name}")
    elif response.status_code == 422:
        print(f"ℹ️ Branch {branch_name} does not exist or already deleted")
    else:
        print(f"⚠️ Warning: Could not delete branch {branch_name}: {response.status_code}")

def create_promotion_branch(repo, source_branch, promo_branch, gh_pat):
    """Create or recreate the promotion branch from the source branch"""
    
    # First, get the latest commit SHA from the source branch
    response = requests.get(
        f"https://api.github.com/repos/{repo}/git/refs/heads/{source_branch}",
        headers=get_headers(gh_pat)
    )
    
    if response.status_code != 200:
        fail(f"Failed to get source branch {source_branch}", response)
    
    source_sha = response.json()["object"]["sha"]
    print(f"ℹ️ Source branch {source_branch} SHA: {source_sha}")
    
    # Try to update existing branch first (in case it exists)
    update_response = requests.patch(
        f"https://api.github.com/repos/{repo}/git/refs/heads/{promo_branch}",
        headers=get_headers(gh_pat),
        json={"sha": source_sha}
    )
    
    if update_response.status_code == 200:
        print(f"✅ Updated existing promotion branch: {promo_branch}")
        return
    
    # If update failed, create new branch
    create_response = requests.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=get_headers(gh_pat),
        json={
            "ref": f"refs/heads/{promo_branch}",
            "sha": source_sha
        }
    )
    
    if create_response.status_code == 201:
        print(f"✅ Created promotion branch: {promo_branch}")
    else:
        fail(f"Failed to create promotion branch {promo_branch}", create_response)

def create_promotion_pr(repo, head, base, source_pr, source_branch, gh_pat, has_conflict):
    if head.count("promotion") > 1:
        fail("🚨 Recursion detected in promotion branch name. Aborting.")

    # Check if a promotion PR already exists
    existing_pr_number = find_existing_promotion_pr(repo, head, base, gh_pat)
    
    if existing_pr_number:
        print(f"📋 Found existing promotion PR #{existing_pr_number} - will close and recreate")
        
        # Close the existing promotion PR
        close_existing_promotion_pr(repo, existing_pr_number, gh_pat, 
                                   f"Recreating with changes from PR #{source_pr}")
        
        # Delete the old promotion branch to ensure clean state
        delete_branch(repo, head, gh_pat)

    # Create/recreate the promotion branch from source
    create_promotion_branch(repo, source_branch, head, gh_pat)

    # Create a new promotion PR
    conflict_note = (
        "\n\n⚠️ **Warning:** This PR currently has merge conflicts and cannot be merged until resolved."
        if has_conflict else ""
    )

    body = f"""## 🚀 Auto Promotion PR

This pull request was created automatically to promote changes from [PR #{source_pr}](https://github.com/{repo}/pull/{source_pr}) into the `{base}` branch.

### 🔁 Promotion Details
- **Source Branch:** `{head}`
- **Target Branch:** `{base}`
- **Original PR:** #{source_pr}{conflict_note}

---

_This PR was generated by the **Auto Promotion Workflow**._
"""

    payload = {
        "title": f"🚀 Promote `{head}` → `{base}`",
        "head": head,
        "base": base,
        "body": body
    }

    url = f"https://api.github.com/repos/{repo}/pulls"
    response = requests.post(url, headers=get_headers(gh_pat), json=payload)

    if response.status_code == 422:
        # Handle the specific case where PR already exists (race condition)
        error_data = response.json()
        if "pull request already exists" in error_data.get("message", "").lower():
            print("🔄 PR was created by another process during recreation...")
            # If this happens, just find it and return it
            existing_pr_number = find_existing_promotion_pr(repo, head, base, gh_pat)
            if existing_pr_number:
                print(f"📋 Using the existing PR: #{existing_pr_number}")
                
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    f.write(f"new_pr_number={existing_pr_number}\n")
                
                return existing_pr_number
        
        fail("Failed to create promotion PR", response)

    if response.status_code != 201:
        fail("Failed to create promotion PR", response)

    pr_number = response.json().get("number")
    print(f"✅ Created new promotion PR #{pr_number}")

    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"new_pr_number={pr_number}\n")

    return pr_number

def check_conflicts(repo, pr_number, gh_pat):
    for attempt in range(5):
        response = requests.get(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
            headers=get_headers(gh_pat)
        )
        if response.status_code != 200:
            fail("Failed to fetch PR info for conflict check", response)

        pr_data = response.json()
        mergeable = pr_data.get("mergeable")

        if mergeable is not None:
            print(f"ℹ️ Mergeable status: {mergeable}")
            return mergeable is False

        print("⏳ Waiting for GitHub to compute mergeability...")
        time.sleep(2)

    print("⚠️ Could not determine merge conflict status.")
    return False

def close_original_pr_and_feature_branch(repo, original_pr, feature_branch, promo_branch, promotion_pr_number, gh_pat, has_conflict):
    conflict_note = (
        "\n\n⚠️ **Note:** The promotion PR has merge conflicts and will require manual resolution before merging."
        if has_conflict else ""
    )

    comment_body = f"""### 🔁 Promotion Workflow Notification

A promotion branch `{promo_branch}` has been created and [PR #{promotion_pr_number}](https://github.com/{repo}/pull/{promotion_pr_number}) has been opened.

This original PR is now closed as the promotion workflow has taken over.{conflict_note}

**Note:** The feature branch `{feature_branch}` will also be deleted as part of this process.

---

_Managed by Auto Promotion Bot_
"""

    # Comment on the original PR
    response = requests.post(
        f"https://api.github.com/repos/{repo}/issues/{original_pr}/comments",
        headers=get_headers(gh_pat),
        json={"body": comment_body}
    )
    if response.status_code != 201:
        fail("Failed to comment on original PR", response)

    # Close the original PR
    response = requests.patch(
        f"https://api.github.com/repos/{repo}/pulls/{original_pr}",
        headers=get_headers(gh_pat),
        json={"state": "closed"}
    )
    if response.status_code != 200:
        fail("Failed to close original PR", response)

    print(f"✅ Original PR #{original_pr} commented and closed.")

    # Delete the feature branch
    delete_branch(repo, feature_branch, gh_pat)

if __name__ == "__main__":
    try:
        repo = os.environ["REPO"]
        promo_branch = os.environ["PROMO_BRANCH"]
        base_branch = os.environ["BASE_BRANCH"]
        original_pr = os.environ["SOURCE_PR"]
        source_branch = os.environ.get("FEATURE_BRANCH")  # Source branch name
        gh_pat = os.environ["GH_PAT"]

        if not source_branch:
            fail("Missing FEATURE_BRANCH environment variable")

        # Create/recreate promotion PR (this handles closing existing ones)
        promotion_pr_number = create_promotion_pr(repo, promo_branch, base_branch, original_pr, source_branch, gh_pat, has_conflict=False)
        
        # Check for conflicts
        has_conflict = check_conflicts(repo, promotion_pr_number, gh_pat)
        
        # Close original PR and delete feature branch
        if source_branch:
            close_original_pr_and_feature_branch(repo, original_pr, source_branch, promo_branch, promotion_pr_number, gh_pat, has_conflict)
        else:
            print("⚠️ Warning: FEATURE_BRANCH not provided, skipping branch deletion")

    except KeyError as e:
        fail(f"Missing environment variable: {e}")