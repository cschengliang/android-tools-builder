#!/usr/bin/env python3
"""Adapt the maximal generic BusyBox configuration to static Android/Bionic."""
import json
import os
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1])
arch = os.environ['ARCH']
root = pathlib.Path(__file__).resolve().parent.parent
output = root / f'dist/android-{arch}/busybox'
output.mkdir(parents=True, exist_ok=True)

disabled = {
    'PIE': 'Use one fully static executable.',
    'BUILD_LIBBUSYBOX': 'No companion shared library.',
    'FEATURE_SHARED_BUSYBOX': 'No companion shared library.',
    'FEATURE_INDIVIDUAL': 'Keep all applets in one executable.',
    'FEATURE_SUID': 'Use the invoking Android UID and permissions.',
    'PAM': 'Android does not use Linux PAM authentication.',
    'SELINUX': 'No external libselinux; Android SELinux enforcement still applies.',
    'FEATURE_UTMP': 'Bionic does not provide a usable Linux utmp database.',
    'FEATURE_WTMP': 'Bionic does not provide a usable Linux wtmp database.',
    'USE_BB_PWD_GRP': 'Keep Bionic Android UID/group name resolution.',
    'USE_BB_SHADOW': 'Android does not use /etc/shadow authentication.',
    'FEATURE_SHADOWPASSWDS': 'Android does not use /etc/shadow authentication.',
    'FEATURE_INETD_RPC': 'Bionic does not provide SunRPC headers/libraries.',
    'HOSTID': 'Bionic has no gethostid API or Unix hostid file.',
    'SHA1_HWACCEL': 'Use portable hashes on all four Android ABIs.',
    'SHA256_HWACCEL': 'Use portable hashes on all four Android ABIs.',
    'TIME64': 'Use Bionic time interfaces at API 29.',
    'SH_IS_HUSH': 'Select ash as the sh entry point; hush remains available.',
    'SH_IS_NONE': 'Select ash as the sh entry point.',
    'BASH_IS_HUSH': 'Select ash for the optional bash alias.',
    'BASH_IS_NONE': 'Enable the ash bash alias.',
}
for name in ('ADDUSER', 'ADDGROUP', 'DELUSER', 'DELGROUP', 'CHPASSWD', 'PASSWD',
             'LOGIN', 'GETTY', 'SU', 'SULOGIN', 'VLOCK'):
    disabled[name] = 'Traditional Unix account management is incompatible with Android accounts.'

def config_values(text):
    return dict(re.findall(r'^CONFIG_(\w+)=(.*)$', text, re.M))

if len(sys.argv) > 2 and sys.argv[2] == 'record':
    config = (source / '.config').read_text()
    (output / 'config.txt').write_text(config)
    table = (source / 'include/applet_tables.h').read_text()
    applets = re.findall(r'^"([^"\n]+)" "\\0"$', table, re.M)
    count = int(re.search(r'NUM_APPLETS\s+(\d+)', (source / 'include/NUM_APPLETS.h').read_text())[1])
    assert len(applets) == count and len(set(applets)) == count
    (output / 'applets.txt').write_text('\n'.join(applets) + '\n')
    before = config_values((output / 'upstream-defconfig.txt').read_text())
    after = config_values(config)
    report = {'version': '1.38.0', 'architecture': arch, 'android_api': 29,
              'base': 'upstream make defconfig (maximal generic configuration)',
              'applet_count': count, 'explicitly_disabled': disabled,
              'disabled_from_defconfig': sorted(name for name, value in before.items()
                                               if value == 'y' and after.get(name) != 'y'),
              'notes': ['Applet availability is verified against busybox --list in CI.',
                        'Inclusion does not imply Android kernel/permission support.',
                        'Temporary paths use /data/local/tmp; shell defaults use /system/bin/sh.']}
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'BusyBox {arch}: {count} applets')
    raise SystemExit(0)

config = (source / '.config').read_text()
(output / 'upstream-defconfig.txt').write_text(config)
values = {name: 'n' for name in disabled}
values.update({name: 'y' for name in ('STATIC', 'LFS', 'DESKTOP', 'LONG_OPTS', 'SHOW_USAGE',
    'FEATURE_VERBOSE_USAGE', 'BBCONFIG', 'FEATURE_COMPRESS_BBCONFIG', 'ASH', 'HUSH',
    'SH_IS_ASH', 'BASH_IS_ASH', 'FEATURE_SH_STANDALONE', 'FEATURE_SH_NOFORK',
    'FEATURE_PREFER_APPLETS', 'USE_BB_CRYPT', 'USE_BB_CRYPT_SHA', 'FEATURE_NSLOOKUP_BIG')})
values.update({'EXTRA_CFLAGS': json.dumps(os.environ['CFLAGS'] + ' -Wno-ignored-optimization-argument'),
               'EXTRA_LDFLAGS': json.dumps(os.environ['LDFLAGS']),
               'EXTRA_LDLIBS': '"dl m"', 'CROSS_COMPILER_PREFIX': '""', 'SYSROOT': '""',
               'PID_FILE_PATH': '"/data/local/tmp"',
               'FEATURE_CROND_DIR': '"/data/local/tmp/cron"'})
for name, value in values.items():
    pattern = rf'^(?:CONFIG_{name}=.*|# CONFIG_{name} is not set)$'
    replacement = f'# CONFIG_{name} is not set' if value == 'n' else f'CONFIG_{name}={value}'
    config, number = re.subn(pattern, lambda _: replacement, config, flags=re.M)
    if not number:
        raise SystemExit(f'Unknown BusyBox option: {name}')
(source / '.config').write_text(config)

# Adapt filesystem defaults without depending on a Termux installation.
for path in source.rglob('*.c'):
    text = path.read_text(encoding='utf-8', errors='surrogateescape')
    adapted = text.replace('"/tmp', '"/data/local/tmp').replace('"/bin/sh"', '"/system/bin/sh"')
    if adapted != text:
        path.write_text(adapted, encoding='utf-8', errors='surrogateescape')
header = source / 'include/libbb.h'
text = header.read_text().replace('"-/bin/sh"', '"-/system/bin/sh"')
text = text.replace('(bb_default_login_shell+6)', '(bb_default_login_shell+1+sizeof("/system/bin"))')
header.write_text(text)
# Bionic already exports these functions. Keep only BusyBox's pivot_root wrapper
# (not part of API 29) and the old-Android compatibility tcdrain definition.
missing = source / 'libbb/missing_syscalls.c'
text = missing.read_text()
for function in ('getsid', 'sethostname', 'adjtimex'):
    text, count = re.subn(r'\b(?:pid_t|int) ' + function + r'\([^)]*\)\n\{.*?\n\}', '', text, flags=re.S)
    assert count == 1, function
missing.write_text(text)
