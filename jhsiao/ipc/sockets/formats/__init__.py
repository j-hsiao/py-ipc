"""Classes for reading/writing different formats.

These classes are non-blocking compatible.  Internal buffers should
remain valid even in the event of EAGAIN or EWOULDBLOCK.

NOTE: regarding sockets, socket.timeout generally does NOT have
errno set to EWOULDBLOCK or EAGAIN so having non-zero timeout will
result in an exception.  As a result, when used with sockets, these
classes should only be used with 0 timeout or No timeout.  This likely
applies to any non-zero timeout (besides None).
"""
