import os
import json

import requests  # Add this import

GREEN_TEXT = '\033[32m'
YELLOW_TEXT = '\033[33m'
RED_TEXT = '\033[31m'
BOLD_TEXT = '\033[1m'
RESET = '\033[0m'
CYAN_BG = '\033[46m'



pr_number = os.environ.get('PR_NUMBER')
github_repository = os.environ.get('GITHUB_REPOSITORY')
github_token = os.environ.get('TOKEN_GITHUB')
commit_id = os.environ.get('COMMIT_ID')


print(f"GitHub Repository: {github_repository}")
print(f"GitHub Token: {github_token}")
print(f"PR Number: {pr_number}")
print(f"commit_id: {commit_id}")

# Get the path to the PMD violations file
pmd_violations_file = "apexScanResults.json"

# Read the PMD violations file as JSON
try:
    with open(pmd_violations_file, "r") as file:
        pmd_violations = json.load(file)
        print(json.dumps(pmd_violations))
except FileNotFoundError:
    print(f"{CYAN_BG}{RED_TEXT}Error: The file {pmd_violations_file} was not found.{RESET}")
    exit(1)
except json.JSONDecodeError:
    print(f"{CYAN_BG}{RED_TEXT}Error: The file {pmd_violations_file} is not a valid JSON file.{RESET}")
    exit(1)

# Create comments for each violation
comments = []
for violation in pmd_violations:
    
    # Get the file path and line number of the violation
    file_path = violation["fileName"]
    print("file path is ")
    print(file_path)
    file_path = file_path.split("changed-sources/")[1]
    print(f"File Path: {file_path}")
    
    for vo in violation['violations']:
        line_number = vo["line"]
        endLine = vo["endLine"]
        if endLine == line_number:
            endLine = line_number + 1

    # Create a comment for the violation
        comment = {
            "path": file_path,
            "line": line_number,
            "side": "RIGHT", 
            "commit_id": commit_id,
            "body": f"PMD Violation: {vo['message']}"
            

        }
        comments.append(comment)
    

print(json.dumps(comments))
# Set the headers for the API request
headers = {
    "Authorization": f"Bearer {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

# Set the GitHub API endpoint
api_url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/comments"



# Send a POST request to create the comments
for comment in comments:
    print(f"Creating comment: {comment}")
    response = requests.post(api_url, json=comment, headers=headers)

    # Check the response status code
    if response.status_code == 201:
        print("Comment created successfully.")
    else:
        print(f"{CYAN_BG}{RED_TEXT}Failed to create comment. Status code: {response.status_code}{RESET}")
        print(f"{CYAN_BG}{RED_TEXT}Response: {response.json()}{RESET}")
        exit(1)

print(f"{GREEN_TEXT} PMD Commentor step executed successfully")