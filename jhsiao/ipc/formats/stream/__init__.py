"""Classes for reading/writing different stream formats.

Many read/write methods assume blocking mode and leave internals in some
unspecified state.  These classes should guarantee a well-defined state
in the event of EAGAIN/EWOULDBLOCK errors.

The incremental methods (readinto1, flush1) do not handle exceptions.
The non-incremental methods(readinto, flush) will handle exceptions.

Furthermore, these classes have methods more appropriate to streams.
When reading streams, not all written data is available at once.  There
may be partial reads, etc.  As a result, the readers support `readinto1`
that read some data and process it accordingly.  Likewise, `flush1` will
write some data and keep track of any unwritten data.

NOTE: timeouts do not count as EAGAIN/EWOULDBLOCK so timeouts should
either be None for blocking, or 0 for non-blocking.  Timeouts are not
handled.
"""
