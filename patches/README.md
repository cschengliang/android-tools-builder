# Source compatibility patches

`strace-android-in-addr.patch` makes strace's bundled Linux UAPI header use
Bionic's `bits/in_addr.h` on Android. This retains the Android `in_addr_t`
typedef needed by `arpa/inet.h` as well as the `in_addr` structure.

The same adaptation is maintained in the [Termux strace recipe](https://github.com/termux/termux-packages/blob/master/packages/strace/bundled-linux-include-uapi-linux-in.h.patch).
The original source archive remains pinned in `sources.json`; patches and build
scripts are retained in the distributed corresponding source package.
