"""Same as chunk, but return memoryview into underlying data buffer.

Maintains an internal buffer instead of allocating num chunks to be
returned.  Subclasses can override `parse_view(chunk)`
"""
__all__ = ['Reader', 'BWriter', 'QWriter']
import io
import struct
import traceback

from . import bases, chunk

encodes = chunk.encodes
decodes = chunk.decodes
bitlen_idx = chunk.bitlen_idx

class Reader(bases.BufferedReader):
    parse_view = staticmethod(memoryview.tobytes)
    def __init__(self, *args, **kwargs):
        super(Reader, self).__init__(*args, **kwargs)
        self.chunkend = None

    def extract(self, out, newstart, idx=0):
        """Call self.parse_view() on full memoryview of chunks.

        Return int:
            0 = no full chunks
            -1 = error.  something went wrong, the datastream is
                probably in an invalid state now.
            >0 : number of bytes processed.
        """
        if self.chunkend is not None and self.stop < self.chunkend:
            return 0
        parsed = 0
        idx = 0
        while idx < self.stop:
            lenparse = decodes[decodes[0].unpack_from(self.buf, idx)[0]]
            idx += 1
            end = idx + lenparse.size
            if self.stop < end:
                if parsed:
                    remain = self.view[parsed:self.stop]
                    self.stop -= parsed
                    self.view[:self.stop] = remain
                self.chunkend = None
                return parsed
            length = lenparse.unpack_from(self.buf, idx)[0]
            if length > len(self.buf):
                try:
                    self._grow(length+9)
                except (MemoryError, ValueError):
                    if parsed:
                        remain = self.view[parsed:self.stop]
                        self.stop -= parsed
                        self.view[:self.stop] = remain
                    return -1
            idx = end
            end = idx + length
            if self.stop < end:
                self.chunkend = end - parsed
                if parsed:
                    remain = self.view[parsed:self.stop]
                    self.stop -= parsed
                    self.view[:self.stop] = remain
                return parsed
            else:
                out.append(self.parse_view(self.view[idx:end]))
                parsed = idx = end
        self.stop = 0
        self.chunkend = None
        return parsed

BWriter = chunk.BWriter
QWriter = chunk.QWriter
