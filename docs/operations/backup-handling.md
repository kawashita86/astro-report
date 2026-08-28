# Operator handling of the `GET /backup` file

The durable record of how the operator-held backup file is stored, retained, and
rotated. Started per epic-6 retrospective / action item `epic-6-retro-item-53`,
which flagged that the route serves a full unencrypted PII dump and no policy
governed the file once downloaded. Indexed as **RGD-6** in
[`docs/decisions/README.md`](../decisions/README.md).

**Ratified.** Francesco, 2026-08-28.

## What the file is

`GET /backup` (`shell/http/routes/backup.py`, Story 6.5) returns **every row of
every durability-relevant table as one plaintext JSON file** —
`backup-<UTCtimestamp>.json`, `Content-Disposition: attachment`,
`Cache-Control: no-store`, built fully in memory. It is unencrypted and
unfiltered: every Client's name, birth date, and birth place, every Report
Payload, Draft, Theme, and Gate result, every Export record, and the Style
Guide. It is the application's real durability mechanism (AD-17: Neon's free
plan has no scheduled backups, only a ~6-hour point-in-time window), so the file
matters — and so does keeping it out of the wrong hands.

The restore side is [`docs/release-validation/restore-rehearsal.md`](../release-validation/restore-rehearsal.md)
(Story 8.5, `python -m shell.restore`).

## Encryption at rest

**Decision (Francesco, 2026-08-28): full-disk encryption only, no per-file
encryption.**

- Backup files are kept **only on a full-disk-encrypted personal machine**
  (FileVault on macOS / LUKS on Linux). The browser's download directory is
  "at rest" for this purpose — the machine the file lands on is the FDE machine.
- The plaintext JSON must **never** come to rest on a volume that is not
  full-disk-encrypted: no unencrypted USB stick, no folder that syncs to an
  unencrypted host, no consumer cloud drive.
- No `age`/`gpg` per-file wrapping is applied.

**Accepted residual.** Anyone with the machine unlocked can read every Client's
PII from a backup file. This is accepted under the single-operator model (there
is exactly one account, and that operator already holds the live database
credentials). **Revisit — per-file encryption becomes mandatory — if** a second
person ever needs a copy, or a backup ever has to leave the FDE machine (transfer
to another host, hand-off, off-site archive).

## Retention and rotation

**Decision (Francesco, 2026-08-28): monthly rotation, keep every backup.**

- **Take a fresh backup monthly.** Use the reports page's **"Back up now"** link,
  which hits `GET /backup?record=1` — the `?record=1` flag writes the
  `backup_record` row that Story 6.6's staleness warning reads, so the app knows
  a backup was taken. A bare `GET /backup` (no flag) downloads the file but does
  **not** update staleness tracking.
- **Keep every backup.** Old files are **not** deleted. One backup is a small
  JSON file (tens of KiB to low MiB at target volume), so accumulation is
  bounded in practice, and an older snapshot has real point-in-time value if a
  corruption is discovered late. The filename timestamp is UTC and sorts
  lexically, so the newest file is always last.
- **Cadence reminder.** Story 6.6's in-app staleness warning fires when the last
  `?record=1` backup is old. That warning **is** the reminder — act on it.

## On machine decommission or disk disposal

Destroy the FDE key (standard FileVault / LUKS decommission) before the disk
leaves your control, so every retained backup on it becomes unrecoverable. Do not
hand on, sell, or recycle the machine with the volume still unlockable.

## References

- Route: [`shell/http/routes/backup.py`](../../shell/http/routes/backup.py) —
  `download_backup`, the `?record=1` gate, the `no-store` header.
- **RGD-4** in [`docs/decisions/README.md`](../decisions/README.md) — the
  accepted `GET`-with-side-effects deviation on `/backup` and the export routes
  (a separate ruling; this file governs the *file*, RGD-4 governs the *route*).
- Story 6.5 (export), Story 6.6 (staleness warning), Story 8.5
  ([restore rehearsal](../release-validation/restore-rehearsal.md)).
- Corpus PII position — **RGD-5** in [`docs/decisions/README.md`](../decisions/README.md)
  (verbatim storage, operator-only, phase-2 anonymization requirement).
