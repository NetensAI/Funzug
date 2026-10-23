"""Atomic, fsynced private state; no symlink or in-place overwrite."""
import json
import os
from pathlib import Path
import uuid


def write_state(path,value):
    path=Path(path)
    if path.is_symlink() or path.parent.is_symlink():raise RuntimeError('unsafe_state_path')
    temporary=path.with_name(path.name+'.stage-'+uuid.uuid4().hex)
    with temporary.open('x') as handle:
        if os.name=='posix':os.fchmod(handle.fileno(),0o600)
        json.dump(value,handle,sort_keys=True)
        handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,path)
    if os.name=='posix':
        descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
