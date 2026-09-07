# EFS Marker Path Sharding

## Objective

Keep the current marker behavior unchanged while replacing the single flat EFS
directory with deterministic, sharded directories.

The current layout stores every START, END, and lock file directly below one
EFS path. Marker lookup uses a filename glob, so EFS must enumerate a directory
whose size continually increases. Under load, and while other pods modify the
same directory, this metadata operation can take 18–20 seconds even when the
requested marker does not exist.

The sharded layout makes each lookup calculate one exact directory containing
only the files for the requested `(queue_name, trace_id)`. Lookup cost therefore
depends on that message's small marker history instead of the total number of
markers on EFS.

## Recommended directory layout

Use this path directly below the configured EFS root:

```text
<EFS_ROOT>/<hash[0:2]>/<hash[2:4]>/<full-hash>/<existing-marker-file>
```

For example:

```text
/efs/mps/
└── a1/
    └── 64/
        └── a164f94dcb7d051542edbc850503d3164ac0bff4831c14f62683f565572025f8/
            ├── trace-123__input__queue__lock
            ├── trace-123__input__queue__start__0__1786590053.123
            └── trace-123__input__queue__end__0__1786590078.456
```

Only the parent directory changes. Keep the existing marker filename and file
content exactly as they are today.

## Hash calculation

Calculate the full 64-character SHA-256 digest from both `queue_name` and
`trace_id`. Including the queue name prevents the same trace ID on two queues
from sharing marker state.

Use a stable, length-prefixed encoding so field boundaries are unambiguous:

```python
import hashlib
from pathlib import Path


IDENTITY_PREFIX = b"MPS2\0"


def length_prefixed(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def marker_identity_digest(trace_id: str, queue_name: str) -> str:
    framed = (
        IDENTITY_PREFIX
        + length_prefixed(queue_name)
        + length_prefixed(trace_id)
    )
    return hashlib.sha256(framed).hexdigest()


def sharded_message_directory(
    storage_path: str | Path,
    trace_id: str,
    queue_name: str,
) -> Path:
    digest = marker_identity_digest(trace_id, queue_name)
    return Path(storage_path) / digest[:2] / digest[2:4] / digest
```

Do not use Python's built-in `hash()`: its value is not stable across processes
or restarts. The digest algorithm, prefix, field order, and length framing form
a permanent path contract and must be used by every marker operation.

### Path calculation frequency

Calculating the SHA-256 digest for each independent marker operation is
expected. It is a small in-memory CPU operation and is negligible compared with
an EFS network and metadata operation.

The digest calculation is not a directory search. It directly produces the
exact message directory; runtime must not enumerate the first-level or
second-level hash directories.

Use one central message-directory helper and follow these rules:

- each independent lock, START, or END operation may call the helper;
- within one method, calculate the message directory once and reuse that local
  variable for every path needed by the method;
- do not introduce a process-wide or unbounded path cache because most trace
  IDs are unique and such a cache would continuously grow;
- lock, START, and END operations for the same `(queue_name, trace_id)` must all
  use the identical helper and therefore resolve to the same directory.

## Why two shard levels

Each two-character hexadecimal prefix has 256 possible values. Two levels
provide 65,536 leaf shards before the full-digest message directory.

This is sufficient for a very large marker population because SHA-256 spreads
identities evenly. Runtime does not list either shard level; it calculates the
complete path directly.

Adding more levels does not improve message lookup. Every additional directory
component adds another EFS/NFS metadata operation. The depth should therefore
remain fixed rather than changing with marker volume.

## MPS manager implementation

### 1. Calculate the message directory

Add one internal helper that returns the deterministic full-digest directory
below the configured EFS root.

### 2. Restrict marker searches

Build the existing marker glob below the calculated message directory:

```text
<message-directory>/<trace-id>__<queue-name>__<type>__*
```

A lookup must never glob the EFS root or either prefix directory. A read miss
must return immediately and must not create any directories.

### 3. Create directories lazily

Immediately before creating a START, END, or lock file, create the calculated
message directory with:

```python
message_directory.mkdir(parents=True, exist_ok=True)
```

Concurrent `mkdir(..., exist_ok=True)` calls for the same identity are expected
and safe. Directory creation must not happen during a read-only duplicate check.

### 4. Place every message-specific file together

Update the paths used by:

- START creation;
- END creation;
- per-message lock-file creation;
- START and END lookup;
- stale START removal.

All files belonging to one `(queue_name, trace_id)` must use the same calculated
full-digest directory. Keep the existing filename builder, parser, marker
contents, duplicate decisions, stale timeout, lock behavior, and marker method
signatures unchanged.

### Lock behavior after sharding

Sharding changes the lock-file parent directory, not the locking algorithm.
For one `(queue_name, trace_id)`, every thread and pod calculates the same full
digest and therefore the same lock-file path:

```text
<EFS_ROOT>/<hash[0:2]>/<hash[2:4]>/<full-hash>/<existing-lock-filename>
```

Keep both existing lock layers:

1. Calculate the message directory and create it with
   `mkdir(parents=True, exist_ok=True)` before opening the lock file.
2. Use the complete sharded lock-file path as the key for the existing
   process-local `threading.Lock`. This serializes worker threads in the same
   Python process because `fcntl` locks do not provide thread-to-thread
   exclusion within one process.
3. After acquiring the thread lock, open the lock file at the calculated EFS
   path and acquire the existing exclusive `fcntl` lock. This serializes
   processes and pods that share the EFS mount.
4. Perform the existing marker recheck and START creation while holding both
   locks.
5. Release the `fcntl` lock and close its file descriptor, then release the
   process-local thread lock in the same order used today.

The lock is per message, not per shard. Messages with different hashes use
different lock files and can proceed concurrently even when their paths share
the same first-level or second-level shard.

All pods must use the same EFS root, the same digest function, and the exact
same `queue_name` and `trace_id` values. Any difference would calculate another
lock path and would prevent cross-pod coordination.

Do not delete or recreate a message's lock file during normal START or END
processing. Its pathname and inode must remain stable while another thread,
process, or pod might be using it.

### 5. Adapt maintenance cleanup

The current flat cleanup cannot find nested markers. Maintenance cleanup must
traverse the `<EFS_ROOT>/<two-hex>/<two-hex>/<full-digest>` structure and apply
the existing age and deletion rules to the files it finds.

Recursive traversal is acceptable for scheduled maintenance, but it must never
be called by normal duplicate lookup or START creation.

## Testing

### Path tests

- The same queue and trace always produce the same digest and path.
- Different traces produce different paths.
- The same trace on different queues produces different paths.
- IDs containing Unicode or glob characters remain deterministic and cannot
  escape the configured EFS root.
- A read miss does not create a directory.

### Behavior tests

- Existing START, END, and lock filenames remain unchanged.
- Existing marker file contents remain unchanged.
- Successful END, failed END, live START, stale START, and new-message behavior
  produce the same decisions as the flat implementation.
- Marker searches inspect only the requested full-digest directory.
- Existing cleanup rules work in the sharded tree without traversing it at
  runtime.

### Concurrency tests

- With many threads claiming the same identity, exactly one START claim wins.
- With multiple processes or pods claiming the same identity through EFS,
  exactly one START claim wins.
- Different identities can progress independently.

### Production-scale validation

Run against the same EFS class and mount configuration used by production, with
at least the current marker population plus projected growth and the normal pod
and thread count.

Acceptance targets for marker lookup are:

- p95 at or below 500 ms;
- p99 at or below 1 second;
- zero duplicate START winners;
- no material latency increase when unrelated marker volume grows.

Sharding addresses lookup latency by reducing directory enumeration. It does
not reduce the total number or storage size of marker files.
