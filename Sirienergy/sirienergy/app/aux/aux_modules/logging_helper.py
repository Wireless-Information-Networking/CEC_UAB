import logging

# ANSI color codes
COLORS = {
    "info": "\033[34m",  # Blue
    "debug": "\033[32m",  # Green
    "error": "\033[31m",  # Red
    "model": "\033[33m",  # Yellow
    "controller": "\033[35m",  # Magenta
    "view": "\033[36m",  # Cyan
    "reset": "\033[0m",  # Reset to default
    "white": "\033[37m",  # White
}

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger()

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        log_type = record.levelname.lower()
        log_color = COLORS.get(log_type, COLORS["white"])  # Color for log level
        mvc_color = COLORS.get(getattr(record, "mvc", "").lower(), COLORS["white"])  # MVC color
        module_color = mvc_color  # Same as MVC
        function_color = mvc_color # Same as MVC

        formatted_message = (
            f"{log_color}[{record.levelname.upper()}]{COLORS['reset']} "
            f"{mvc_color}[{getattr(record, 'mvc', '').upper()}]{COLORS['reset']} "
            f"{module_color}[{getattr(record, 'module_name', '')}]{COLORS['reset']} "
            f"{function_color}[{getattr(record, 'function_name', '')}]{COLORS['reset']} \n"
            f"{COLORS['white']} --> {record.getMessage()}{COLORS['reset']}"
        )
        return formatted_message

# Apply custom formatter to logger
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logger.handlers = [handler]

def log_message(log_type, mvc, module_name, function_name, message):
    if log_type.lower() not in ["info", "debug", "error"]:
        log_type = "info"  # Default to info if invalid

    # Create log record manually with extra attributes
    log_record = logger.makeRecord(
        name=logger.name,
        level=getattr(logging, log_type.upper()),
        fn=function_name,
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
        extra={"mvc": mvc, "module_name": module_name, "function_name": function_name},
    )
    logger.handle(log_record)  # Send the record to the logger
