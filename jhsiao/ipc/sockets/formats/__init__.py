"""Classes for reading/writing different formats.

These classes are non-blocking compatible.  Internal buffers should
remain valid even in the event of EAGAIN or EWOULDBLOCK.

"""
