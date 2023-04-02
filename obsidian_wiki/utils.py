from pathlib import Path
from typing import Union
import logging

def normalize(self, target:Path):
    """
    Inverse of relative_to, honestly no idea why this isn't already in pathlib.Path
    
    #### Parameters
    target (Path)
    :    Path to normalize against.
    
    #### Returns
    Path
    :    Normalized path
    """
    rel = target.relative_to(self)
    norm = Path()
    for p in rel.parents:
        if p != Path():
            norm /= ".."
    return norm
Path.normalize = normalize

# Shorthand pathlike type (Path or str)
pathlike = Union[Path, str]

# Shift regular logging messages by a tab
logging._info = logging.info
def info(msg, before=True):
    # Add tab before if requested
    if before:
        msg = f"\t{msg}"
    # Continue as normal
    logging._info(msg)
logging.info = info

logging._warn = logging.warn
def warn(msg, before=True):
    # Add tab before if requested
    if before:
        msg = f"\t{msg}"
    # Continue as normal
    logging._warn(msg)
logging.warn = warn

# Shorthand for delimiter
def delim(msg):
    # Pad with spaces
    msg = f"  {msg}  "
    # Pad to 60 with #
    msg = msg.center(60, "#")
    # Log
    logging.info(msg, before=False)
logging.delim = delim

def start_delim(msg):
    logging.info("", before=False)
    delim(msg)
logging.start_delim = start_delim

def end_delim(msg):
    delim(msg)
    logging.info("", before=False)
logging.end_delim = end_delim