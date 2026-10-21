# Source compatibility patches

`strace-android-in-addr.patch` makes strace's bundled Linux UAPI header use
Bionic's `bits/in_addr.h` on Android. This retains the Android `in_addr_t`
typedef needed by `arpa/inet.h` as well as the `in_addr` structure.

The same adaptation is maintained in the [Termux strace recipe](https://github.com/termux/termux-packages/blob/master/packages/strace/bundled-linux-include-uapi-linux-in.h.patch).
The original source archive remains pinned in `sources.json`; patches and build
scripts are retained in the distributed corresponding source package.

## BusyBox 1.38.0

The patches in `busybox/` are retained from the Termux BusyBox recipe at
commit `b68a22c1019dd675efc9e2fbf0c57769c02f6908`:
https://github.com/termux/termux-packages/tree/b68a22c1019dd675efc9e2fbf0c57769c02f6908/packages/busybox

They address Clang optimization of BusyBox's mutable global state, the Bionic
strchrnul declaration, duplicate IPv6 structures, unavailable addmntent, and
the explicit_bzero API baseline. No Termux installation paths or changes to
user-switching/authentication behavior are imported.

`scripts/configure-busybox.py` records the maximal generic upstream defconfig,
adapts Android paths and static linking, removes already-provided Bionic syscall
wrappers, and records all explicit configuration exclusions and the final config.
The final applet list is extracted from the generated applet table and compared
with the executable's actual `--list` output in CI.
