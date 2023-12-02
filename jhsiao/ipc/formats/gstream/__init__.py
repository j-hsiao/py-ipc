"""Implement reading/writing via generators.

Using generators automatically saves the current step in the generator.
Otherwise, each call would need to re-check what the next step is
explicitly.  This might simplify some code.  Test performance diffs.

For writing, this probably isn't as necessary since it just writes
chunks of bytes.  There generally is only 2 states: has data to write or
no data to write.
"""

# TODO: merge gstream/stream?
