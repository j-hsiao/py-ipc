"""Polling to handle multiple resources.

Generic pseudocode polling loop:

wwait: list of items waiting for write to be available and have data to write
rwait: list of items waiting for read to be available

wpend: list of items with pending data to write
rpend: list of items with pending data to read

while 1:
    result = poll(wwait, rwait, timeout)
    for thing in result:
        if readable(thing):
            rpend.append(thing)
        if writable(thing):
            wpend.append(thing)
    for thing in rpend:
        read_a_bit(thing)
        if no_data_ready(thing):
            rwait.append(thing)
        elif errored(thing):
            rpend.remove(thing)
            wpend.remove(thing)
            handle_error(thing)
    for thing in wpend:
        write_a_bit(thing)
        if done(thing):
            wpend.remove(thing)
        elif writestalled:
            wwait.append(thing)
        elif errored(thing):
            rpend.remove(thing)
            wpend.remove(thing)
            handle_error(thing)


The read_a_bit and write_a_bit directly know what the result was so
maybe it should handle the remove or add to respective list.  The result
would be like:

while 1:
    result = poll(wwait, rwait, timeout)
    for thing in result:
        if readable(thing):
            rpend.append(thing)
        if writable(thing):
            wpend.append(thing)
    for thing in rpend:
        handle(thing)
    for thing in wpend:
        handle(thing)

"""
__all__ = ['SelectPoller']

from .select import SelectPoller

import select as _select
if hasattr(_select, 'epoll'):
    from .epoll import EpollPoller
    __all__.append('EpollPoller')

# __all__ = ['RPoller', 'WPoller', 'RWPoller']
# if hasattr(select, 'select'):
#     from .select import *
# if hasattr(select, 'devpoll') or hasattr(select, 'poll'):
#     from .poll import *
# if hasattr(select, 'epoll'):
#     from .epoll import *
# 
# try:
#     RPoller
# except NameError:
#     raise ImportError('Failed to find a polling mechanism.')
