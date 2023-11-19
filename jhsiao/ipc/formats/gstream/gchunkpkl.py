import pickle

from . import gchunk

class GChunkPklReader(gchunk.GChunkReader):
    _process = staticmethod(pickle.loads)

