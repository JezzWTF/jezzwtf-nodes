# Set and Get (Remote)

Pass any value across the graph without a wire.

- **Set (Remote)** stores its input under a `key`. It passes the value through, so it can sit in the middle of a chain.
- **Get (Remote)** picks a key from a dropdown of the Set nodes in the graph and outputs that value.

Both nodes share a colour so you can see which pair belongs together, and the key shows as a small badge.

## Good to know

- There is no ordering guarantee. A Get needs its Set to have run earlier in the same queue, or it reports that the key is missing.
- Values live only for the current prompt. A new queue starts clean, so large values such as models are not held in memory after the run.
