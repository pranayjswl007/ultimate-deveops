# devops/replace_env_vars.py
import os
import sys
import yaml
from lxml import etree
import re
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class EnvironmentVariableReplacer:
    def __init__(self, config_dir="environments"):  # Remove target_env from __init__
        self.config_dir = Path(config_dir)
        self.namespaces = {
            'ns': 'http://soap.sforce.com/2006/04/metadata'
        }
    
    def load_config(self, target_env):  # Add target_env parameter here
        """Load the environment-specific YAML configuration file"""
        try:
            env_file = f"{target_env}.yml"
            config_file = self.config_dir / env_file
            
            if not config_file.exists():
                logger.error(f"Configuration file not found: {config_file}")
                sys.exit(1)
            
            with open(config_file, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                logger.info(f"Configuration loaded from: {config_file}")
                return config
                
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            sys.exit(1)
    
    def get_required_variables(self, config):
        """Extract environment variable names (${VARIABLE_NAME}) from the configuration"""
        variables = set()
        
        for replacement in config.get('xpath_replacements', []):
            # Find all ${VARIABLE_NAME} patterns in the value
            matches = re.findall(r'\$\{([^}]+)\}', replacement.get('value', ''))
            variables.update(matches)
        
        return variables
    
    def load_variables(self, required_variables):
        """Load variables from environment (only for ${VARIABLE_NAME} placeholders)"""
        variables = {}
        missing = []
        
        if not required_variables:
            logger.info("No environment variables required (using direct YAML values)")
            return variables
        
        for var_name in required_variables:
            value = os.getenv(var_name)
            if value:
                variables[var_name] = value
                logger.info(f"✓ Loaded environment variable: {var_name}")
            else:
                missing.append(var_name)
        
        if missing:
            logger.error(f"Missing environment variables: {', '.join(missing)}")
            logger.info("Make sure variables are set in GitHub Environment:")
            logger.info("- Use Secrets for sensitive data (API keys, passwords)")
            sys.exit(1)
        
        return variables
    
    def replace_variables_in_value(self, value, variables):
        """Replace ${VARIABLE_NAME} with actual values, or return value as-is if no placeholders"""
        # If no placeholders, return the value directly from YAML
        if '${' not in str(value):
            return str(value)
        
        # Replace environment variable placeholders
        def replace_variable(match):
            var_name = match.group(1)
            return variables.get(var_name, match.group(0))
        
        return re.sub(r'\$\{([^}]+)\}', replace_variable, str(value))
    
    def process_file(self, file_path, replacements, variables):
        """Process a single XML file"""
        full_path = Path(f"./changed-sources/force-app/main/default/{file_path}")
        
        if not full_path.exists():
            logger.info(f"File not in delta, skipping: {file_path}")
            return
        
        logger.info(f"Processing: {file_path}")
        
        try:
            # Parse XML
            tree = etree.parse(str(full_path))
            root = tree.getroot()
            modified = False
            
            # Apply each replacement
            for replacement in replacements:
                xpath = replacement['xpath']
                new_value = self.replace_variables_in_value(replacement['value'], variables)
                
                # Find elements using XPath
                elements = root.xpath(xpath, namespaces=self.namespaces)
                
                if elements:
                    for element in elements:
                        element.text = new_value
                        modified = True
                    logger.info(f"  ✓ Replaced {len(elements)} elements: {xpath}")
                    logger.info(f"    New value: {new_value}")
                else:
                    logger.warning(f"  ⚠ XPath not found: {xpath}")
            
            # Save if modified
            if modified:
                tree.write(str(full_path), encoding='utf-8', xml_declaration=True, pretty_print=True)
                logger.info(f"  ✓ File updated: {file_path}")
        
        except Exception as e:
            logger.error(f"  ✗ Error processing {file_path}: {str(e)}")
    
    def process_environment(self, target_env):
        """Main processing method"""
        logger.info(f"Starting replacement for environment: {target_env}")
        logger.info("=" * 50)
        
        # Load environment-specific config file
        config = self.load_config(target_env)  # Pass target_env here
        
        # Get required environment variables (only for ${} placeholders)
        required_variables = self.get_required_variables(config)
        if required_variables:
            logger.info(f"Required environment variables: {', '.join(sorted(required_variables))}")
        else:
            logger.info("Using direct YAML values (no environment variables needed)")
        
        # Load environment variables (empty if none required)
        variables = self.load_variables(required_variables)
        
        # Check if we have changes to process
        if not Path('./changed-sources').exists():
            logger.info('No changed-sources directory found')
            return
        
        # Group replacements by file
        files_to_process = {}
        for replacement in config.get('xpath_replacements', []):
            file_path = replacement['file']
            if file_path not in files_to_process:
                files_to_process[file_path] = []
            files_to_process[file_path].append(replacement)
        
        # Process each file
        logger.info(f"Processing {len(files_to_process)} files...")
        for file_path, replacements in files_to_process.items():
            self.process_file(file_path, replacements, variables)
        
        logger.info("=" * 50)
        logger.info("Replacement completed successfully!")


def main():
    if len(sys.argv) != 2:
        logger.error('Usage: python replace_env_vars.py <environment>')  # Fixed script name
        sys.exit(1)
    
    target_env = sys.argv[1]
    replacer = EnvironmentVariableReplacer()
    replacer.process_environment(target_env)  # Pass target_env here


if __name__ == "__main__":
    main()