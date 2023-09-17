"""Pickle using chunked semantics.

This format sends the size of the pickle before unpickling.  As a result
it does not rely on `pickle.STOP`.  This means that this format does not
have the same drawback as the raw pkl format.
"""
__all__ = ['Reader', 'BWriter', 'QWriter']
import pickle

from . import chunkview

class Reader(chunkview.Reader):
    parse_view = staticmethod(pickle.loads)

class BWriter(chunkview.BWriter):
    def write(self, data):
        super(BWriter, self).write(pickle.dumps(data))

class QWriter(chunkview.QWriter):
    def write(self, data):
        super(QWriter, self).write(pickle.dumps(data))
