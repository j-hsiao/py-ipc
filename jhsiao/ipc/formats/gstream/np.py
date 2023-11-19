"""Numpy array type.
The first 6 bytes are a magic string: exactly \x93NUMPY.

The next 1 byte is an unsigned byte: the major version number of the
file format, e.g. \x01.

The next 1 byte is an unsigned byte: the minor version number of the
file format, e.g. \x00. Note: the version of the file format is not tied
to the version of the numpy package.

The next 2 bytes form a little-endian unsigned short int: the length of
the header data HEADER_LEN.
"""
import ast
import struct
import sys
if sys.version_info.major > 2:
    decode = str
else:
    decode = unicode

import numpy as np

from . import base


_MAGIC_LEN = 6
_VERSION = struct.Struct('BB')
_VERSION_LEN = _MAGIC_LEN + _VERSION.size
_HLEN1 = struct.Struct('<h')
_HLEN2 = struct.Struct('<L')
_VMAX = _VERSION_LEN + _HLEN2.size

class GNumpyReader(base.Reader):
    def _iter(self, allow_pickle=False):
        buf = bytearray(128)
        view = memoryview(buf)
        out = self._out
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