"""yield from = syntax error with py2 so put in separate file and import if not py2
"""
import io
import struct

from . import base

def chunk_iter2(
    f, out, verbose=False,
    buffersize=io.DEFAULT_BUFFER_SIZE, size='<Q',
    process=memoryview.tobytes):
    """Iterator for parsing chunks of data.

    buffersize: size of the buffer.
    size: struct.Struct string for parsing the size of a chunk.
    """
    readinto = f.readinto
    tryread = base.tryreader(f.readinto, verbose)
    s = struct.Struct(size)
    buf = bytearray(max(buffersize, s.size))
    view = memoryview(buf)
    start = end = 0
    out = out
    while 1:
        target = start + s.size
        if target > len(buf):
            cursize = end - start
            view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = s.size
        if end < target:
            p = [end]
            yield from base.readtil(readinto, view, p, target)
            end = p[0]
        nbytes = s.unpack_from(buf, start)[0]
        start = target
        target = start + nbytes
        if target > len(buf):
            cursize = end - start
            if nbytes > len(buf):
                buf = bytearray(nbytes + s.size)
                buf[:cursize] = view[start:end]
                view = memoryview(buf)
            else:
                view[:cursize] = view[start:end]
            start = 0
            end = cursize
            target = nbytes
        if end < target:
            p = [end]
            yield from base.readtil(readinto, view, p, target)
            end = p[0]
        out.append(process(view[start:target]))
        if end == target:
            start = end = 0
        else:
            start = target
