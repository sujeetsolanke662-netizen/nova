# NOVA packaging

Skeleton systemd + Debian packaging for NOVA. This is not wired up to a
build yet - see "What's stubbed" below before assuming any of this runs
end-to-end.

## What each file is for

- `systemd/nova.service` - the systemd unit that runs the FastAPI backend
  (`uvicorn app.main:app`) as the unprivileged `nova` system user, restarts
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

Stubbed / not yet done:
- **There is no `app.main:app` yet.** `backend/app/` currently has no
  `main.py` or FastAPI app object - `guardrails.py`, `apt_clutter.py`, and
  `audit_log.py` exist, but nothing exposes them over HTTP yet. The unit
  file assumes this entrypoint will exist at that module path; update
  `ExecStart` if the real entrypoint ends up somewhere else.
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
