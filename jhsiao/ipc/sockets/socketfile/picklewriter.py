__all__ = ['PickleWriter']
import pickle
from socketfile import bases

class PickleWriter(bases.Writer):
    def write(self, item):
        pickle.dump(item, self.f)

    def flush(self):
        self.f.flush()
