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
    def __init__(self, config_dir=""):
        self.config_dir = Path(config_dir)
        self.namespaces = {
            'ns': 'http://soap.sforce.com/2006/04/metadata'
        }
    
    def load_config(self):
        """Load the single XPath configuration file"""
        try:
            config_file = self.config_dir / "environment.yml"
            
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
        """Extract all variable names from the configuration"""
        variables = set()
        
        for replacement in config.get('xpath_replacements', []):
            # Find all ${VARIABLE_NAME} patterns in the value
            matches = re.findall(r'\$\{([^}]+)\}', replacement.get('value', ''))
            variables.update(matches)
        
        return variables
    
    def load_variables(self, required_variables):
        """Load all variables from environment (GitHub handles secrets vs variables automatically)"""
        variables = {}
        missing = []
        
        for var_name in required_variables:
            value = os.getenv(var_name)
            if value:
                variables[var_name] = value
                logger.info(f"✓ Loaded: {var_name}")
            else:
                missing.append(var_name)
        
        if missing:
            logger.error(f"Missing variables: {', '.join(missing)}")
            logger.info("Make sure variables are set in GitHub Environment:")
            logger.info("- Use Secrets for sensitive data (API keys, passwords)")
            logger.info("- Use Variables for non-sensitive data (URLs, emails)")
            sys.exit(1)
        
        return variables
    
    def replace_variables_in_value(self, value, variables):
        """Replace ${VARIABLE_NAME} with actual values"""
        def replace_variable(match):
            var_name = match.group(1)
            return variables.get(var_name, match.group(0))
        
        return re.sub(r'\$\{([^}]+)\}', replace_variable, value)
    
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
    
    def process_environment(self):
        """Main processing method"""
        logger.info(f"Starting replacement for environment")
        logger.info("=" * 50)
        
        # Load single config file
        config = self.load_config()
        
        # Get required variables
        required_variables = self.get_required_variables(config)
        logger.info(f"Required variables: {', '.join(sorted(required_variables))}")
        
        # Load variables from environment
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
   
    replacer = EnvironmentVariableReplacer()
    #print alll environment variablle in Python
    logger.info("Environment Variables:")
    for key, value in os.environ.items():
        logger.info(f"{key}: {value}")  
    replacer.process_environment()


if __name__ == "__main__":
    main()