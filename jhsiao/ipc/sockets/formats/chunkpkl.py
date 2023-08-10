"""Pickle using chunked semantics."""
__all__ = ['Reader', 'BWriter', 'QWriter']
import pickle

from . import chunk


class Reader(chunk.Reader):
    def readinto1(self, out):
        L = []
        try:
            return super(Reader, self).readinto1(L)
        finally:
            if L:
                try:
                    for data in L:
                        out.append(pickle.loads(data))
                except pickle.UnpicklingError:
                    return -1

class BWriter(chunk.BWriter):
    def write(self, data):
        super(BWriter, self).write(pickle.dumps(data))

class QWriter(chunk.QWriter):
    def write(self, data):
        super(QWriter, self).write(pickle.dumps(data))
