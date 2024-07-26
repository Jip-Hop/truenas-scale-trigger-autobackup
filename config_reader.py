import sys
import yaml
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
import json
from itertools import chain

# Define a data class for your configuration
@dataclass
class SmtpConfig:
    server: str
    port: int
    login: str
    password: str
    recipients: List[str]
    send_autobackup_output: bool

    def __str__(self):
        data = asdict(self)
        data['password'] = '*****'  # Replace the password when logging
        return json.dumps(data, indent=2)

# Define a data class for the logging configuration
@dataclass
class LoggingConfig:
    level: str
    logfile_path: str
    def __str__(self):
        return json.dumps(asdict(self), indent=2)

# Define a data class for a single pool configuration
@dataclass
class PoolConfig:
    pool_name: str
    split_parameters: bool
    autobackup_parameters: List[str] = field(default_factory=list)
    passphrase: Optional[str] = ""  # Optional, default is empty string
    def __str__(self):
        data = asdict(self)
        data['passphrase'] = '*****' if self.passphrase else self.passphrase  # Replace the passphrase when logging
        return json.dumps(data, indent=2)

# Define a data class for the application configuration including logging and pools
@dataclass
class AppConfig:
    logging: Optional[LoggingConfig] = None
    pools: Dict[str, PoolConfig] = field(default_factory=dict)
    smtp: SmtpConfig = field(default=None)
    def __str__(self):
        data = asdict(self)
        if data.get('smtp'):
            data['smtp']['password'] = '***'
        for pool_key, pool in data.get('pools', {}).items():
            if 'passphrase' in pool and pool['passphrase']:
                data['pools'][pool_key]['passphrase'] = '***'
        return json.dumps(data, indent=2)

# Function to load and validate the YAML config
def read_validate_config(config_path) -> AppConfig:
    with open(config_path, 'r') as stream:
        try:
            config = yaml.safe_load(stream)

            # Check for mandatory fields
            if config.get('logging') is None:
                raise ValueError("The 'logging' field is missing or not set.")
            elif config['logging'].get('logfile_path') is None:
                raise ValueError("The 'logfile_path' field is missing or not set.")
            if config.get('pools') is None or not config['pools']:
                raise ValueError("The 'pools' field is missing or empty.")

            # Check if 'smtp' key is present in the config
            if 'smtp' in config:
                required_keys = ['server', 'port', 'login', 'password', 'recipients']
                missing_keys = [key for key in required_keys if key not in config['smtp']]
                if missing_keys:
                    raise ValueError(f"Missing required smtp config keys: {', '.join(missing_keys)}")
                # Validate each email address in the comma-separated recipients list
                recipients_str = config['smtp']['recipients']
                if not isinstance(recipients_str, str) or not recipients_str:
                    raise ValueError("The 'recipients' key must be a non-empty string.")
                recipients = [email.strip() for email in recipients_str.split(',')]
                invalid_emails = [email for email in recipients if not is_valid_email(email)]
                if invalid_emails:
                    raise ValueError(f"Invalid email addresses found: {', '.join(invalid_emails)}")
                
                # Add validated and stripped recipients back to the config
                config['smtp']['recipients'] = recipients
                smtp_conf = SmtpConfig(**config['smtp'])
            else:
                smtp_conf = None
            
            # Initialize logging configuration if it's present
            logging_conf = None
            if 'logging' in config:
                logging_conf = LoggingConfig(**config['logging'])

            # Initialize pool configurations if they're present
            pool_confs = {}
            if 'pools' in config:
                for pool_key, pool_values in config['pools'].items():
                    if 'pool_name' not in pool_values or 'autobackup_parameters' not in pool_values:
                        raise ValueError(f"Pool '{pool_key}' is missing mandatory parameters 'pool_name', 'autobackup_parameters'.")
                    if 'split_parameters' not in pool_values:
                        pool_values['split_parameters'] = True
                    if pool_values['split_parameters']:
                        # Use map to apply split_if_space to each argument, then flatten the result
                        pool_values['autobackup_parameters'] = list(chain.from_iterable(map(split_if_space, pool_values['autobackup_parameters'])))

                    pool_confs[pool_values['pool_name']] = PoolConfig(**pool_values)
            else:
                raise ValueError(f"missing parameter pools'.")

            # Return an AppConfig instance with logging and pool configurations
            return AppConfig(smtp=smtp_conf, logging=logging_conf, pools=pool_confs)

        except yaml.YAMLError as exc:
            sys.exit(f"Error parsing YAML file: {exc}")
        except ValueError as ve:
            sys.exit(f"Configuration validation error: {ve}")

def is_valid_email(email):
    # Simple regex for validating an email address
    pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(pattern, email) is not None

def split_if_space(arg: str) -> List[str]:
    # Split the argument by spaces if it contains any, otherwise return it as a single-element list.
    return arg.split(' ') if ' ' in arg else [arg]