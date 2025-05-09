# Ultimate DevOps Project

## Overview
The Ultimate DevOps project is designed to streamline the development and deployment processes for Salesforce applications. It utilizes GitHub Actions for continuous integration and deployment, ensuring that code changes are validated and deployed efficiently.

## Project Structure
The project is organized into several key directories and files:

- **.github/workflows/**: Contains GitHub Actions workflows for validating pull requests, deploying to production, and managing change sets.
  - **main-validate.yml**: Validates pull requests by checking the build and running tests.
  - **main-prod-deployment.yml**: Handles deployment to production when changes are pushed to the main branch.
  - **develop-validate-uat.yml**: Validates pull requests in the UAT environment, running tests and scanning code.
  - **changeset-downloader.yml**: Creates a feature branch from a change set and retrieves metadata from Salesforce.
  - **develop-deploy-uat.yml**: Deploys changes to the UAT environment, handling quick deployments and status checks.
  - **reusable/**: Contains reusable workflows for validation, deployment, change set management, and utility functions.

- **devops/**: Contains Python scripts and configuration files for processing pull requests, updating PR bodies, posting comments, and checking deployment results.
  - **prDeployPreProcessor.py**: Processes pull requests before deployment.
  - **prUpdated.py**: Updates the pull request body with relevant information.
  - **pmdCommentor.py**: Posts comments to GitHub based on PMD scan results.
  - **quickDeploymentResultChecker.py**: Checks the results of quick deployments.
  - **requirements.txt**: Lists the Python dependencies required for the scripts.
  - **masterRuleset.xml**: Contains the ruleset configuration for PMD code scanning.

- **force-app/**: Contains Salesforce metadata files that are part of the application.

## Setup Instructions
1. **Clone the Repository**: 
   ```bash
   git clone https://github.com/pranayjswl007/ultimate-devops.git
   cd ultimate-devops
   ```

2. **Install Dependencies**: 
   Ensure you have Node.js and Salesforce CLI installed. You can install the required Python dependencies using:
   ```bash
   pip install -r devops/requirements.txt
   ```

3. **Configure Salesforce CLI**: 
   Authenticate with your Salesforce org using the SFDX_AUTH_URL secret.

4. **Run Workflows**: 
   Use GitHub Actions to trigger workflows for validation and deployment as needed.

## Usage
- **Pull Request Validation**: When a pull request is created, the `main-validate.yml` workflow will automatically run to validate the changes.
- **Production Deployment**: Changes pushed to the main branch will trigger the `main-prod-deployment.yml` workflow for deployment to production.
- **UAT Validation**: The `develop-validate-uat.yml` workflow will validate pull requests in the UAT environment.
- **Change Set Management**: Use the `changeset-downloader.yml` workflow to create feature branches from change sets.
- **UAT Deployment**: The `develop-deploy-uat.yml` workflow handles deployments to the UAT environment.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.