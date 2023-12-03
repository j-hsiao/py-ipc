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
from observation:
    n: int, >= 0 = number of bytes for the argument
    -1: variable length until newline?, but some is til 2nd newline
    -2: 1 byte length followed by length bytes
    -3: 4 byte length followed by length bytes
    -4: same as -3
    -5: 8 byte length followed by length bytes

"""
