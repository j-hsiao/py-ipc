"""Implement reading/writing via generators.

Using generators automatically saves the current step in the generator.
Otherwise, each call would need to re-check what the next step is
explicitly.  This might simplify some code.

For writing, this probably isn't as necessary since it just writes
chunks of bytes.  There generally is only 2 states: has data to write or
no data to write.


After some testing:
    1. explicitly saving state and checkinge each iter seems ot have the
       highest overhead and is the slowest.
    2. send() is ok, but having to wrap it in another iterator to make
       it a bit more generic reduces performance vs just wrapping
       readinto in a try/except function.
"""

# TODO: merge gstream/stream?
