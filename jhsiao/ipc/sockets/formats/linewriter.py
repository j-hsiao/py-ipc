"""Write lines (size followed by bytes).

"""
import struct

from jhsiao.ipc.sockets.socketfile import bases

codes = ['>BB', '>BH', '>BL', '>BQ']
thresholds = [0xFF, 0xFFFF, 0xFFFFFFFF]

class LineWriter(bases.Writer):
    def write(self, item):
        i = 0
        L = len(item)
        while L > thresholds[i]:
            i += 1
        self.f.write(struct.pack(codes, i, L))
        self.f.write(item)
