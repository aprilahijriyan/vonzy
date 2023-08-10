import logging

from rich.logging import RichHandler

log = logging.getLogger("vonzy")
log.addHandler(RichHandler(rich_tracebacks=True, show_path=False))
log.setLevel(logging.NOTSET)
log.info("Starting vonzy")
