# Identifying silent changes in firmware and package updates

When working with proprietary software, changelogs often contain few details of security fixes, and sometimes part of the changes are not mentioned by the vendor. For this example, we will work from two versions of binary packages provided by an open source project. Using open source software for this example allows us to compare this tool's output to the changes that have been applied to the source code.
The second version includes a fix for a known vulnerability, which we will recover using this tool. This process can be applied to proprietary software to identify silently fixed vulnerabilities, about which no information is known beforehand.

## FRRouting

To quote [their website](https://frrouting.org/):

> FRRouting (FRR) is an IP routing protocol suite for Linux and Unix platforms which includes protocol daemons for BGP, IS-IS, LDP, OSPF, PIM, and RIP.

Though the source code [is available](https://github.com/FRRouting/frr), the pre-compiled packages can serve as a handy example of how changes performed in a update can be identified.

A more practical use case would be to identify changes in a firmware update from a third-party vendor. This could help identify introduced vulnerabilities or silent security fixes. 

## Downloading

### FRRouting

To get started, download the [FRR 3.0.2](https://github.com/FRRouting/frr/releases/download/frr-3.0.2/frr_3.0.2-1-debian8.1_amd64.deb) and [FRR 3.0](https://github.com/FRRouting/frr/releases/download/frr-3.0/frr_3.0-1-debian8.1_amd64.deb) packages for Debian 8 x86_64.
As [CVE-2019-5892](https://frrouting.org/community/security/cve-2019-5892.html) was patched in FRR 3.0.2, we will show how the patch can be identified from the distributed packages.

### Tools

For this example, [Difftool](https://github.com/airbus-seclab/Difftool) and [diffoscope](https://diffoscope.org) will be used. The installation procedure can be found on each project's page. For Difftool, a minimal install is enough.

## Unpacking

### Using `fact_extractor`

If you performed a full install, the packages can be extracted automatically, so you can skip the unpacking step.

### Manually

You can also manually unpack the `.deb` archive using the following commands:

```bash
$ mkdir frr-3.0
$ ar x frr_3.0-1-debian8.1_amd64.deb --output frr-3.0
$ tar -xf frr-3.0/data.tar.xz -C frr-3.0
$ rm frr-3.0/*.tar.*
```

The same process should be done with `frr_3.0.2-1-debian8.1_amd64.deb`.

**Note:** Some archives may be left (e.g. man files), but this shouldn't be an issue. In the next section, add the `--no-extract`  option since the content has already been unpacked. 

## Identifying changed files

Let's start by comparing all the files in the two versions:

```bash
$ time ./main.py frr_3.0-1-debian8.1_amd64.deb frr_3.0.2-1-debian8.1_amd64.deb
Found 0 added files, 0 removed files and 31 changed files (31 files in total)

real	0m17.114s
user	0m23.350s
sys		0m3.768s
```

**Note:** Without the `--extract` option, files are extracted by default to `/tmp/extractor{1,2}`. To avoid unpacking archives each time, you can run the tool on these folders instead and use the `--no-extract` option.

There are a few files that we can ignore, because they are not relevant for our goal: we want to identify vulnerabilities in code. Let's run the tool again, and save the output:

```bash
$ ./main.py frr_3.0-1-debian8.1_amd64.deb frr_3.0.2-1-debian8.1_amd64.deb --exclude "*/changelog*" --exclude-mime "text/plain" --output frr.diff
Found 0 added files, 0 removed files and 15 changed files (15 files in total)
```

## Comparing

Now that we have a list of changed files, we can use [diffoscope](https://diffoscope.org/) to compare their content:

```bash
$ time ./tools/diffoscope.py frr.diff --html-dir /tmp/diffoscope
Copied 30 files

real	1m21.599s
user	1m14.404s
sys		0m19.048s
```

When looking at the content of `/tmp/diffoscope/index.html`, we see there's a bit of noise that isn't of much interest to us. We can run diffoscope again to get rid of it:

```bash
$ ./tools/diffoscope.py frr.diff --html-dir /tmp/diffoscope --exclude-command "stat .*" --exclude-command "readelf .*(notes|data|debug|symbols|got|eh_frame|text|relocs).*" --diff-mask "version [0-9\.]+" --diff-mask "\-?0x[0-9a-f]+" --diff-mask "[0-9a-f]+(?=\s+<)"
```

**Note:** 

* `--exclude-command` ignores commands diffoscope would normally run that match the given regex. In our case, the `stat` command usually shows differences in dates, which we want to ignore. We also want to ignore some sections from readelf that are too verbose.
* `--diff-mask` replaces content matching the given regex by `[masked]` on a line-by-line basis. We use it for the following:
  * Ignore version numbers (`version [0-9\.]+`),
  * Ignore offset changes in `objdump` instructions (`\-?0x[0-9a-f]+`)
  * Ignore explicit addresses when they have been resolved (`[0-9a-f]+(?=\s+<)`)
* These options are quite rough and not ideal, though they should work in this example. For a better implementation, you should checkout [this repository](https://github.com/airbus-seclab/Difftool/tree/master/tools) which contains patches to diffoscope aimed at reducing noise.

This should significantly reduce the size of the output (and the time needed to process the files). We can then very quickly identify which files have significant changes.

In this case, running diffoscope directly on the `.deb` archives would yield a similar result in more or less the same time. However, iterating multiple times to tweak the excluded files or commands can become very time consuming if the whole analysis is performed each time. This becomes even more visible when working on large firmware images, for which diffoscope's output can take hours to be generated. 

## Understanding changes

From the previous step, 3 files with significant differences can be identified:

* `usr/bin/vtysh` with many removed strings, but no code change,
* `usr/lib/frr/isisd`, in which calls to `prefix_ipv6_free` and `prefix_ipv4_free` have been added,
* `usr/lib/frr/bgpd`, with many significant changes.

Because of our use case, we can ignore `usr/bin/vtysh`'s changes.

### isisd

It is quite clear from the changes that calls to `free` were missing, probably resulting in a memory leak.
This is confirmed by version [3.0.2's changelog](https://github.com/FRRouting/frr/releases/tag/frr-3.0.2) which mentions "Fix for a memory leak in ISIS".

### bgpd

Because of the size of the output, some lines are being hidden by diffoscope's output. Let's run diffoscope on this file only to get the full output:

```bash
$ diffoscope /tmp/extractor1/files/usr/lib/frr/bgpd /tmp/extractor2/files/usr/lib/frr/bgpd --exclude-command "readelf .*" --exclude-command "objdump.* --section=\.plt" --html /tmp/diffoscope.html --max-page-diff-block-lines 4096 --max-diff-block-lines 0 --diff-mask "\-?0x[0-9a-f]+" --diff-mask "[0-9a-f]+(?=\s+<)"
```

Since some other changes to `bgpd` were included the update, the changes don't all relate to patching the CVE. Moreover, some moved code and changed registers can be spotted, but are most likely artifacts of recompilation. Relevant changes are discussed below.

#### skip_runas option

The changes visible in `strings`' output is the following:

```
- p:l:rne:
+ p:l:rSne:
```

This reflects the `Enable '-S' usage for BGP` fix mentioned in the changelog.

#### Outbound prefix-list

Multiple changes and a new call to `strcmp` around line 6860 of the `.text` section's diff can be spotted. This is related to the `Check for per-peer outbound configuration, in addition to the peer-group config` change.

#### RFC 4271 6.3

Some changes, including calls to `stream_forward_getp` and `stream_get`, occur around line 26320. This is what we were looking for.

Without going into too many details, these changes aim at implementing [RFC 4271 6.3](https://tools.ietf.org/html/rfc4271#section-6.3), which revised the way errors are reported: the length of attributes should be checked first, and an error should be returned if there is a mismatched with what is expected.

Since the software is open source, the changes can also be compared to those of [the original pull request fixing the CVE](https://github.com/FRRouting/frr/pull/1418) to verify our analysis.

## Conclusion

The described methodology can help identify changes in software for which the source is not directly available. Though performed on a relatively small open-source project, the same concepts easily apply to much larger software, such as firmwares.

This can lead to the discovery of silent security fixes, introduced vulnerabilities, or incomplete patches.