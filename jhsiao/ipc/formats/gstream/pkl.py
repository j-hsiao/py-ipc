"""Concatenated pickle files.

Pickle is a series of 1-byte latin-1 opcodes
followed by possible argument.

Last opcode is always pickle.STOP

pickletools is a helper module for pickle.

option1:
    read until encounter pickle.STOP
    try to unpickle
option2:
    read opcodes, try read arguments if applicable
    continue until pickle.STOP
    unpickle

opcode: class representing the op code
    name, arg,...

opcode.arg: class representing an argument
    name, n, reader
n: number of bytes or variable if negative:
    UP_TO_NEWLINE: -1, to next (and including) '\n'
        ending with _pair is to 2nd '\n'
    TAKEN_FROM_ARGUMENT1: -2, 1 byte uint length + length bytes
    TAKEN_FROM_ARGUMENT4: -3, 4 byte int length + length bytes
    TAKEN_FROM_ARGUMENT4U: -4, 4 byte uint length + length bytes
    TAKEN_FROM_ARGUMENT8U: -5, 8 byte uint length + length bytes
    (all little endian)
"""
from __future__ import print_function
import struct
import codecs
import pickle
import pickletools

opdecode = codecs.getdecoder('latin-1')
sizestruct = [
    struct.Struct('<Q'),
    struct.Struct('<I'),
    struct.Struct('<i'),
    struct.Struct('<B'),
    None
]

def stopop(buf, view, codepos, end):
    """Calculate the position of the stop op code.

    If the stop opcode is not found, then return the next known
    position of an opcode.
    """
    while codepos < end:
        code = view[codepos:codepos+1]
        if code == pickle.STOP:
            return codepos
        try:
            op = pickletools.code2op[opdecode(code)[0]]
        except KeyError:
            return -1
        arg = op.arg
        if arg is None:
            codepos += 1
        else:
            N = arg.n
            if N > 0:
                codepos += 1 + N
            elif N == -1:
                if arg.name.endswith('pair'):
                    npos = buf.find(b'\n', codepos+1, end)
                    if npos < 0:
                        return codepos
                    npos = buf.find(b'\n', npos+1, end)
                    if npos < 0:
                        return codepos
                    else:
                        codepos = npos + 1
                else:
                    npos = buf.find(b'\n', codepos+1, end)
                    if npos < 0:
                        return codepos
                    else:
                        codepos = npos+1
            else:
                sz_start = codepos + 1
                size = sizestruct[N]
                sz_stop = sz_start + size.size
                if end < sz_stop:
                    return codepos
                codepos = sz_stop + size.unpack_from(view, sz_start)[0]
    return codepos

if __name__ == '__main__':
    L = ['hello', b'world', bytearray(b'whatever'), 1, 3.14, ('a', b'b')]
    L.append(L)
    data = pickle.dumps(L)
    print(repr(data))
    for end in range(len(data)+1):
        print(end, stopop(data, memoryview(data), 0, end))
