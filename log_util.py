import logging
from config_reader import LoggingConfig

class Logging:
    def __init__(self, config: LoggingConfig):# enable_logging: bool, logfile: str):
        self.enabled = config != None #enable_logging
        self.logger = logging.getLogger("UDEV-Trigger")

        self.logger.propagate = False  # Disable propagation to root logger
        self.logger.setLevel(logging.DEBUG)
        # Create formatter for console and file
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # Create console handler and set level to debug
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        if self.enabled:
            file_handler = logging.FileHandler(config.logfile_path)
            file_handler.setLevel(config.level)
            file_handler.setFormatter(file_formatter)
            # Add handlers to the logger
            self.logger.addHandler(file_handler)
            print(f"logging enabled to {config.logfile_path}")
        else:
            # logging.disable(true)
            print("Logging disabled")

    def log(self, message: str):
        self.logger.info(message)

    def error(self, message: str):
        self.logger.error(message)

    def exception(self, message: str):
        self.logger.exception(message)