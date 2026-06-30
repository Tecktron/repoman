# Why repoman

## The upgrade problem

Every Ubuntu version upgrade ends the same way: your third-party repositories stop working. Ubuntu disables them as part of the upgrade process — it replaces `Enabled: yes` with `Enabled: no` in every `.sources` file and strips `.list` repos of their comments. No warning, no summary of what changed, no tool to fix it.

The expected workflow is to visit every repository's website, find the updated PPA or install instructions for the new release, and re-add each one manually. If you run ten or fifteen third-party repos, this takes a while. If you can't remember what half of them were for — because Ubuntu removed your comments — it takes longer.

## The silent failure nobody talks about

There's a second problem that's easier to miss.

Some repositories survive the upgrade process with `Enabled: yes` but don't actually carry packages for the new Ubuntu codename. When `apt update` hits those repos, it returns a 404. APT reports this as a generic "failed to fetch" error buried in the update output. The package index for that repo doesn't update. If you're not watching carefully, you might not notice for weeks — until something that was supposed to auto-update quietly stops getting updates.

repoman explicitly checks for this case. A repository that is enabled but has no packages for your current release is treated as needing attention, same as a repo that was explicitly disabled.

## Why not just use the existing tools?

The existing GUI tools for APT repository management — Software & Updates, and its successors — handle the repositories that ship with Ubuntu. They're not designed for the post-upgrade third-party repo workflow. The closest tool that used to exist was `ppa-purge` combined with manual re-adding, but that's destructive and requires knowing exactly which PPAs you had.

There's no maintained tool that:

- Survives across Ubuntu upgrades with your repo list intact
- Checks both disabled and silently-failing repos in one pass
- Lets you annotate repos with notes that don't get stripped on upgrade
- Gives you a guided workflow to assess and fix everything after an upgrade
- Provides a full-time GUI for adding, removing, and editing repositories day-to-day — no more editing `.sources` files manually
- Manages GPG signing keys alongside the repos they authenticate
- Lets you save and restore your complete repo configuration across reinstalls and machines

repoman is that tool.
