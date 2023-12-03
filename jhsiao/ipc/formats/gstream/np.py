"""Numpy array type.
The first 6 bytes are a magic string: exactly \x93NUMPY.

The next 1 byte is an unsigned byte: the major version number of the
file format, e.g. \x01.

The next 1 byte is an unsigned byte: the minor version number of the
file format, e.g. \x00. Note: the version of the file format is not tied
to the version of the numpy package.


The next 2 bytes form a little-endian unsigned short int: the length of
the header data HEADER_LEN. (version 2.0 = 4 bytes)

Next HEADER_LEN bytes = a dict followed by newline and space padding
(descr, fortran_order, shape)

version 3.0: enforces dict str is unicode
"""
import ast
import struct
import sys
import traceback
import pickle
if sys.version_info.major > 2:
    decode = str
else:
    decode = unicode

import numpy as np

from . import base


_MAGIC = b'\x93NUMPY'
_MAGIC_END = len(_MAGIC)
_VERSION = struct.Struct('BB')
_VERSION_END = _MAGIC_END + _VERSION.size

_HLEN1 = struct.Struct('<H')
_HSTART1 = _VERSION_END + _HLEN1.size
_HLEN2 = struct.Struct('<L')
_HSTART2 = _VERSION_END + _HLEN2.size
_NP_HEADER_CHUNK = 64
DEFAULT_NP_HEADER_SIZE = 128

class GNumpyReader(base.Reader):
    def _iter(self, allow_pickle=False):
        buf = bytearray(128)
        view = memoryview(buf)
        out = self.out
        start = stop = 0
        while 1:
            versionend = start + _VERSION_LEN
            while stop < versionend:
                stop += (yield view[stop:])
            vstart = start + _MAGIC_LEN
            if buf[start:vstart] != b'\x93NUMPY':
                yield None
            major, minor = _VERSION.unpack_from(buf, vstart)
            if major == 1:
                size = _HLEN1
            else:
                size = _HLEN2
            headstart = versionend + size.size
            while stop < headstart:
                stop += (yield buf[stop:])
            headend = headstart + size.unpack_from(buf, versionend)[0]
            if headend > len(buf):
                headsize = headend - start
                if headsize > len(buf):
                    nbuf = bytearray(headsize)
                    nbuf[:stop-start] = view[start:stop]
                    buf = nbuf
                    view = memoryview(buf)
                else:
                    view[:stop-start] = view[start:stop]
                stop -= start
                start = 0
            while stop < headend:
                stop += (yield view[stop:])
            header = ast.literal_eval(
                decode(view[headstart:headend], 'utf-8'))
            dt = np.dtype(header['descr'])
            if dt.hasobject:
                if allow_pickle:
                    # a python pickle
                    raise NotImplementedError
                else:
                    yield None
            else:
                array = np.empty(
                    header['shape'], dt,
                    order='F' if header['fortran_order'] else 'C')
                rav = memoryview(array.ravel().view(np.uint8))
                pos = stop - headend
                if pos >= len(rav):
                    dataend = headend + len(rav)
                    rav[:] = view[headend:dataend]
                    if len(buf) - dataend < _VMAX:
                        nstop = stop - start
                        view[:nstop] = view[start:stop]
                        stop = nstop
                        start = 0
                    else:
                        start = dataend
                else:
                    stop = start = 0
                    rav[:pos] = view[headend:stop]
                    while pos < len(rav):
                        pos += (yield rav[pos:])
                out.append(array)


def np_iter(f, out, verbose=False buffersize=DEFAULT_NP_HEADER_SIZE):
    """Iterate on numpy arrays (np.save)"""
    tryread = base.tryreader(f.readinto)
    buf = bytearray(max(buffersize, _NP_HEADER_CHUNK))
    view = memoryview(buf)
    try:
        while 1:
            stop = 0
            while stop < _VERSION_END:
                amt = tryread(view[stop:])
                if amt is None or amt < 0:
                    yield amt
                elif amt > 0:
                    stop += amt
                    yield amt
                else:
                    yield -1
            if view[:_MAGIC_END] != _MAGIC:
                yield -1
                continue
            major, minor = _VERSION.unpack_from(view, _MAGIC_END)
            if major == 1:
                size = _HLEN1
            else:
                size = _HLEN2
            length = size.unpack_from(view, _VERSION_END)[0]
            headstart = _VERSION_END + size.size
            headend = headstart + length
            if headend > len(buf):
                nbuf = bytearray(headend)
                nbuf[:stop] = view[:stop]
                view = memoryview(nbuf)
                buf = nbuf
            while stop < headend:
                amt = tryread(view[stop:])
                if amt is None or amt < 0:
                    yield amt
                elif amt > 0:
                    stop += amt
                    yield amt
                else:
                    yield -1
            header = ast.literal_eval(
                decode(view[headstart:headend], 'utf-8'))
            dt = np.dtype(header['descr'])
            if dt.hasobject:
                if allow_pickle:
                    pickle.loads()
                    # TODO
                    pass
                else:
                    yield -1
            else:
                array = np.empty(
                    header['shape'], dt,
                    order='CF'[int(header['fortran_order'])])
                rav = memoryview(array.ravel().view(np.uint8))
                nbytes = array.nbytes
                pos = stop - headend
                if nbytes <= pos:
                    dataend = headend + nbytes
                    rav[:] = view[headend:dataend]
                    nstop = stop - dataend
                    view[:nstop] = view[dataend:stop]
                    stop = nstop
                else:
                    rav[:pos] = view[headend:stop]
                    while pos < nbytes:
                        amt = tryread(rav[pos:])
                        if amt is None or amt < 0:
                            yield amt
                        elif amt > 0:
                            pos += amt
                            yield amt
                        else:
                            yield -1
                out.append(array)
    except Exception:
        if verbose:
            traceback.print_exc()
        yield -1
