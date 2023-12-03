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

