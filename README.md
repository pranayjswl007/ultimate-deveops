# Salesforce DX Project: Next Steps

Now that you’ve created a Salesforce DX project, what’s next? Here are some documentation resources to get you started.

## How Do You Plan to Deploy Your Changes?

Do you want to deploy a set of changes, or create a self-contained application? Choose a [development model](https://developer.salesforce.com/tools/vscode/en/user-guide/development-models).

## Configure Your Salesforce DX Project

The `sfdx-project.json` file contains useful configuration information for your project. See [Salesforce DX Project Configuration](https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_ws_config.htm) in the _Salesforce DX Developer Guide_ for details about this file.

## Read All About It

- [Salesforce Extensions Documentation](https://developer.salesforce.com/tools/vscode/)
- [Salesforce CLI Setup Guide](https://developer.salesforce.com/docs/atlas.en-us.sfdx_setup.meta/sfdx_setup/sfdx_setup_intro.htm)
- [Salesforce DX Developer Guide](https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_intro.htm)
- [Salesforce CLI Command Reference](https://developer.salesforce.com/docs/atlas.en-us.sfdx_cli_reference.meta/sfdx_cli_reference/cli_reference.htm)

# DevOps Automation Workflows

This repository includes a set of automated workflows and scripts to streamline Salesforce DX development, code quality, deployment, and promotion processes. Below is an overview of each workflow and how to use the supporting scripts.

---

## GitHub Actions Workflows

All workflows are defined in [`.github/workflows/`](.github/workflows/):

- **auto-promote.yml**: Automatically promotes merged PRs to higher environments (e.g., from `develop` to `main`).
- **changeset-downloader.yml**: Downloads and prepares changesets for deployment or validation.
- **code-scanner.yml**: Runs static code analysis (e.g., PMD) and posts results as PR comments.
- **deploy.yml**: Handles deployment of code to Salesforce orgs, including test execution and artifact management.
- **validate.yml**: Validates PRs by running test deployments and reporting results.

Each workflow is triggered by specific GitHub events (e.g., PR opened, push, or manual dispatch).

---

## How to Call a Workflow from Another Repository

You can reuse workflows from this repository in other repositories using GitHub Actions' `workflow_call` feature.

### 1. Define the Called Workflow

In this repository (the called repo), ensure your workflow (e.g., `.github/workflows/deploy.yml`) includes the `workflow_call` trigger:

```yaml
on:
  workflow_call:
    inputs:
      environment:
        required: true
        type: string
    secrets:
      GH_TOKEN:
        required: true
```

### 2. Call the Workflow from the Caller Repository

In your caller repository, reference the workflow using the `uses` keyword:

```yaml
jobs:
  call-deploy:
    uses: pranayjaiswal/ultimate-devops/.github/workflows/deploy.yml@main
    with:
      environment: "production"
    secrets:
      GH_TOKEN: ${{ secrets.GH_TOKEN }}
```

- Replace `pranayjaiswal/ultimate-devops` with the correct owner/repo.
- The `@main` refers to the branch or tag in the called repo.

### 3. Requirements

- The called workflow must be on the default branch or a published tag.
- The caller repository must have access to the called repository if it is private.
- Any required secrets must be passed explicitly.

For more details, see [GitHub Docs: Reusing workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows).

---

## Key DevOps Scripts

All scripts are located in [`devops/`](devops/):

### 1. [`prUpdated.py`](devops/prUpdated.py)

**Purpose:**  
Posts a detailed deployment/validation summary as a review on the PR, including test results, code/flow coverage, and inline comments for component failures.

**How it works:**
- Reads deployment results from `deploymentResult.json`.
- Summarizes status, errors, and coverage.
- Posts a PR review with a markdown summary and line-level comments.
- Exits with status 0 (success) or 1 (failure).

**Usage:**  
Set required environment variables (`PR_NUMBER`, `GITHUB_REPOSITORY`, `TOKEN_GITHUB`, `COMMIT_ID`, etc.) and run:
```sh
python devops/prUpdated.py
```

### 2. [`pmdCommentor.py`](devops/pmdCommentor.py)

**Purpose:**  
Posts PMD static code analysis results as line-level comments on the PR.

**How it works:**
- Reads `apexScanResults.json` for PMD violations.
- Deletes old PMD comments.
- Groups and posts new line-level comments for each violation.

**Usage:**  
Set required environment variables and run:
```sh
python devops/pmdCommentor.py
```

### 3. [`prDeployPreProcessor.py`](devops/prDeployPreProcessor.py)

**Purpose:**  
Fetches the latest PR review comment from GitHub Actions and extracts deployment metadata (e.g., artifact URL, deployment ID) to set as environment variables for downstream jobs.

**Usage:**  
Run as part of your workflow before deployment steps.

### 4. [`promotion_handler.py`](devops/promotion_handler.py)

**Purpose:**  
Automates the creation of promotion PRs between branches and manages PR comments/closure for promotion workflows.

**Usage:**  
Set required environment variables (`REPO`, `PROMO_BRANCH`, `BASE_BRANCH`, `SOURCE_PR`, `GH_PAT`) and run:
```sh
python devops/promotion_handler.py
```

### 5. [`quickDeploymentResultChecker.py`](devops/quickDeploymentResultChecker.py)

**Purpose:**  
Quickly checks and prints deployment results for debugging or CI feedback.

---

## Environment Variables

Most scripts require the following environment variables (set by your workflow or manually):

- `PR_NUMBER`
- `GITHUB_REPOSITORY`
- `TOKEN_GITHUB`
- `COMMIT_ID`
- `ARTIFACT_URL`
- `ARTIFACT_ID`
- `RUN_ID`
- (others as needed per script)

---

## Dependencies

Install Python dependencies from [`devops/requirements.txt`](devops/requirements.txt):

```sh
pip install -r devops/requirements.txt
```

---

## Example Workflow Usage

A typical PR validation workflow might look like:

1. **Run static code analysis:**  
   `python devops/pmdCommentor.py`
2. **Deploy or validate changes:**  
   (Salesforce CLI or custom deployment script)
3. **Post deployment summary to PR:**  
   `python devops/prUpdated.py`

Promotion and artifact handling are managed by their respective scripts and workflows.

---

For more details, see the source code in [`devops/`](devops/).
