"""
Centralized logging configuration for the application
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime


class LoggerConfig:
    """Centralized logger configuration"""
    
    @staticmethod
    def setup_logger(name: str = None, level: str = None) -> logging.Logger:
        """
        Setup and return a configured logger
        
        Args:
            name: Logger name (defaults to calling module)
            level: Log level (defaults to INFO or LOG_LEVEL env var)
        
        Returns:
            Configured logger instance
        """
        if name is None:
            # Get the calling module name
            frame = sys._getframe(1)
            name = frame.f_globals.get('__name__', 'app')
        
        logger = logging.getLogger(name)
        
        # Avoid duplicate handlers
        if logger.handlers:
            return logger
        
        # Set log level
        log_level = level or os.getenv('LOG_LEVEL', 'INFO')
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        logger.addHandler(console_handler)
        
        # File handler with rotation
        log_dir = os.getenv('LOG_DIR', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'{name.replace(".", "_")}.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
        
        # Error file handler
        error_log_file = os.path.join(log_dir, f'{name.replace(".", "_")}_errors.log')
        error_file_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(detailed_formatter)
        logger.addHandler(error_file_handler)
        
        return logger
    
    @staticmethod
    def get_logger(name: str = None) -> logging.Logger:
        """Get a logger instance (creates if doesn't exist)"""
        return LoggerConfig.setup_logger(name)


# Convenience function for easy imports
def get_logger(name: str = None) -> logging.Logger:
    """Get a configured logger instance"""
    return LoggerConfig.get_logger(name) 