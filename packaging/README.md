# NOVA packaging

Skeleton systemd + Debian packaging for NOVA. This is not wired up to a
build yet - see "What's stubbed" below before assuming any of this runs
end-to-end.

## What each file is for

- `systemd/nova.service` - the systemd unit that runs the FastAPI backend
  (`uvicorn backend.app.main:app`) as the unprivileged `nova` system user, restarts
  it on failure, and sends its stdout/stderr to the journal. Does not touch
  the audit log (`backend/app/audit_log.py`), which is a separate,
  application-level, tamper-evident ledger written by NOVA itself, not by
  systemd.
- `debian/control` - package metadata: name, description, and the
  `python3` / `python3-venv` dependency baseline.
- `debian/postinst` - runs after files are unpacked. Creates the `nova`
  system user/group if missing, creates `/opt/nova` (app code + venv) and
  `/var/lib/nova` (audit log + persistent state) with correct ownership,
  and enables (but does not start) the service.
- `debian/prerm` - runs before files are removed. Stops and disables the
  service so nothing is left running against a half-removed install.

## Testing the systemd unit locally, without building a .deb

You don't need a `.deb` to sanity-check the unit file itself:

```sh
# 1. Make sure the paths the unit expects actually exist, or edit the
#    unit to point at wherever your working tree/venv actually is.
sudo mkdir -p /opt/nova /var/lib/nova
sudo cp -r backend /opt/nova/
sudo python3 -m venv /opt/nova/venv
sudo /opt/nova/venv/bin/pip install -r /opt/nova/backend/requirements.txt uvicorn

# 2. Create the nova user by hand (postinst does this for you in a real
#    install, but there is no postinst running here).
sudo adduser --system --group --no-create-home \
    --home /var/lib/nova --shell /usr/sbin/nologin nova
sudo chown nova:nova /var/lib/nova

# 3. Install and start the unit.
sudo cp packaging/systemd/nova.service /etc/systemd/system/nova.service
sudo systemctl daemon-reload
sudo systemctl start nova
sudo systemctl status nova
journalctl -u nova -f
```

To undo: `sudo systemctl stop nova && sudo systemctl disable nova && sudo rm /etc/systemd/system/nova.service`.

## What's real vs. stubbed

Real:
- The unit file's shape (dependencies, `Restart=on-failure`, running as an
  unprivileged user, journal logging, basic sandboxing via
  `ProtectSystem=strict` + `NoNewPrivileges`) follows normal systemd
  practice and will work as-is once the paths it references exist.
- `postinst`/`prerm` follow the standard Debian maintainer-script
  case-statement shape (`configure` / `remove,deconfigure` /
  `upgrade,failed-upgrade`) and are safe to read as a reference for how
  the real scripts should behave.
- **`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` are set as `Environment=`
  lines on the unit.** NOVA Copilot's retrieval pipeline
  (`backend/app/copilot_retrieval.py`) loads two sentence-transformers
  models; without these, the underlying `huggingface_hub`/`transformers`
  libraries will still probe the network (e.g. to check for a newer
  cached revision) before falling back to the local cache. Systemd units
  don't inherit whatever's exported in a login shell, so the vars have to
  be set here explicitly - the offline claim in the top-level README needs
  to hold no matter how the service is launched, not just when
  `HF_HUB_OFFLINE` happens to already be set in the launching shell.
- **The `backend.app.main:app` entrypoint the unit's `ExecStart` points at
  exists and works.** `main.py` wires up guardrails, apt-clutter scanning,
  exact/near-duplicate detection, staleness scoring, capacity forecasting,
  and the NOVA Copilot retrieval/answer pipeline behind `/health`,
  `/api/guardrails/check`, `/api/recommendations`, `/api/copilot/search`,
  `/api/apt-clutter/scan`, and `/api/audit-log`(`/verify`) - all covered
  by `backend/tests` (run via `pytest backend/tests`).

Stubbed / not yet done:
- **No `dpkg-deb`/`debuild` build script exists.** There's no `rules`
  file, `changelog`, `compat` file, or `debian/nova.install` listing which
  built files land where - none of the other pieces debhelper needs to
  actually produce a `.deb`. `control` declares
  `debhelper-compat (= 13)` on the assumption we'll build that out later;
  right now nothing here has been run through `dpkg-buildpackage`.
  `postinst`/`prerm` include a `#DEBHELPER#` marker so debhelper can
  inject its own hooks once that's wired up.
- **No `.install`/file-list mapping.** Nothing here specifies how the
  built `backend/` tree and its venv actually get laid out under
  `/opt/nova` inside the package - that's the "copy the venv in" step a
  real build script still needs to do.
- **Dashboard packaging is untouched.** `nova-frontend/` (the React/Vite
  dashboard) isn't referenced anywhere in this packaging - it's not
  built, not copied into the package, and not served by the backend unit.
  The postinst message says the API will be reachable at
  `http://127.0.0.1:8756`; there's no dashboard URL to print yet because
  there's no dashboard build/serve story decided.
- **Fine-grained scan-target read access is not configured.** The unit
  comments say the `nova` user should get read access to whatever it's
  scanning (without broad root access), but the actual mechanism -
  supplementary group membership, ACLs, etc. - isn't decided or scripted
  here. Today, `nova` gets only what a fresh unprivileged system user
  gets by default: nothing outside its own home.
- **Version/changelog/maintainer info in `control` and `postinst`'s
  maintainer email are placeholders** and haven't been checked against
  whatever the project's actual release process ends up being.

## Benchmarking

`backend/scripts/benchmark_scan.py` is a standalone scalability benchmark
for NOVA's core file-processing pipeline - not a pytest test, and not run
as part of `pytest backend/tests`. It exists to get real, reportable
throughput/memory numbers (e.g. for the hackathon presentation), not to
assert pass/fail.

It generates a synthetic file tree (realistic size mix - mostly small
files, some medium, a handful large; ~15% exact duplicates; spread across
a several-levels-deep directory tree) in a temp directory, then times
`scanner.scan_directory()`, `dedup.find_exact_duplicates()`,
`staleness.score_all()`, and the full
`recommendation.generate_recommendations()` end-to-end separately, plus
peak RSS memory. The generated tree (and a throwaway audit log file next
to it) is deleted afterward unless `--keep` is passed.

```sh
# Default: 10,000 files, fresh temp dir, cleaned up afterward.
python -m backend.scripts.benchmark_scan

# A second, larger data point to see how it scales:
python -m backend.scripts.benchmark_scan --file-count 25000

# Keep the generated tree around for manual inspection:
python -m backend.scripts.benchmark_scan --file-count 5000 --keep --tmp-dir /tmp/nova_bench

# Same synthetic tree every time (default seed 42) - pass --seed to compare
# before/after a code change on identical data, or a different --seed for
# a fresh random tree.
python -m backend.scripts.benchmark_scan --file-count 10000 --seed 7
```

Every synthetic file uses an extension outside `near_dedup.py`'s
`IMAGE_EXTENSIONS`/`TEXT_EXTENSIONS`, so this measures scan/dedup/
staleness throughput specifically, not that module's already-documented
O(n²) near-duplicate comparison (see its own module docstring).
