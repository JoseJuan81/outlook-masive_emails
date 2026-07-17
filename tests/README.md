# Test suite — masive_emails

Regression tests for the mass-email sender. Targets two specific bugs:

- **A) Subject recycling**: Outlook COM was inheriting the subject from
  the previous inspector / dispatch, instead of the one we wrote into
  staging. Fixed in `send_from_staging.py:160-188` (PR_SUBJECT via
  MAPI + `mail.Save()` before `mail.Send()`).
- **B) Cross-contamination**: loading EML B after dispatching EML A left
  A's subject or A's images in the session. Fixed in `web/app.py:295-299`
  (write + flush + fsync on the staging file) and in
  `import_email_template.save_images` (clears the images dir before
  writing the new set).

## Running

```
uv run pytest tests/
```

or, to also run the pre-existing `test/` suite:

```
uv run pytest
```

Expected output: **34 tests passing** in under 2 seconds on Linux.

## Layout

```
tests/
  conftest.py                       # fixtures (clean_state autouse, client, tmp_eml_factory)
  strategies.py                     # MockOutlook + mirror of send_from_staging.main()
  test_upload_eml.py                # 5 tests — FIX 2 surface
  test_send_payload.py              # 7 tests — FIX 1 surface (fsync) + payload contract
  test_outlook_com_order.py         # 6 dispatch order tests + 9 mirror-anchor watchdogs
  test_regression_cross_contamination.py
                                    # 3 tests — the original repro A -> B -> A -> B
  test_diagnostic_log.py            # 4 tests — the staging diag line format/source anchor
```

Total: **34 tests, ~1.4 seconds**.

## Strategy: mirroring `send_from_staging.py`

`send_from_staging.py` is invoked via `subprocess.Popen` from
`web/app.py:312-316` using **Windows Python** (because of
`win32com.client`). We cannot simply `import` it from a Linux test.

Instead of mocking `win32com` and `outlook` at the import level (fragile
and requires complex `sys.modules` patching), we chose **Option A from the
brief — a documented mirror of the dispatch loop** living in
`tests/strategies.py`. The mirror is intentionally short and lists
anchors like:

```
# M3: mail.PropertyAccessor.SetProperty(... PROPTAG_SUBJECT ...)
```

Those anchors are kept in sync with `send_from_staging.py` by a
parameterised test (`test_strategies_mirror_anchors_match_production`)
that asserts specific line numbers in production still contain the
expected fragments.

If you reorganise `send_from_staging.py`, that test fails and tells
you to also update `tests/strategies.py`. This is the **only kind of
edit** the suite asks for; everything else is read-only.

### Why not just mock the COM layer?

We considered the alternative (patching `sys.modules['win32com']`,
`sys.modules['win32com.client']`, and `outlook.application`). It would
allow `import send_from_staging` to "just work" in tests. We rejected it
because:

1. It would require modifying `send_from_staging.py` to make `main()`
   importable (move the `import win32com.client as win32` statement
   inside the function, expose `STAGING_FILE` etc. via an env variable).
   That's production-code churn for test reasons.
2. The mock would still need to re-emit the exact same property writes
   the production code performs, otherwise we couldn't tell whether
   the fix is in or not.

The mirror approach is **invasive in the test code only** — production
remains untouched, and the team's review surface stays minimal.

## FIX 1 (fsync) coverage

`test_api_send_flushes_and_fsyncs_staging_file` instruments
`os.fsync` and verifies it was called with the staging file's fileno
in the same transaction as the `write()`. This is the regression
guard for `web/app.py:295-299`.

## FIX 2 (no contamination) coverage

- `test_upload_eml_replaces_session_on_second_upload` asserts that
  `_session["subject"]` reflects the second upload.
- `test_upload_eml_save_images_wipes_directory_on_each_load` asserts
  that `html/images/body/` never accumulates files between loads.
- `test_save_images_avoids_orphan_files_across_cycles` documents the
  edge case where a 0-image load intentionally does NOT wipe the dir.

## FIX 3 (MAPI subject) coverage

`test_outlook_com_order.py`:

- `test_outlook_dispatch_calls_create_item_with_zero` — `CreateItem(0)`.
- `test_outlook_dispatch_assigns_send_using_account` —
  `mail.SendUsingAccount`.
- `test_outlook_dispatch_sets_subject_via_mapi_first` — the load-bearing
  test: the property log entry with `PROPTAG_SUBJECT` must exist and
  carry the staging subject.
- `test_outlook_dispatch_sets_to_field` — `mail.To`.
- `test_outlook_dispatch_adds_one_attachment_per_image` — N attachments,
  each with `cid=image_N` and `hidden=True`.
- `test_outlook_dispatch_calls_save_before_send` — `Save()` comes
  before `Send()`.

## End-to-end regression

`test_two_consecutive_emls_do_not_contaminate_each_other` reproduces the
exact scenario the user reported:

1. Upload EML A (subject "Caso A", 2 images).
2. Call `/api/send` with `test_email`. Verify staging subject is "Caso A".
3. Run the mock dispatch — verify `mail.Subject == "Caso A"` and 2 attachments.
4. Upload EML B (subject "Caso B", 3 images).
5. Call `/api/send` again.
6. Run the mock dispatch — **the key assertion**: `mail.Subject == "Caso B"`
   (NOT recycled) and 3 attachments (NOT 5 mixed up).

## Dependencies

The suite uses only stdlib + `pytest`, `fastapi`, `httpx`. The
`TestClient` from `fastapi.testclient` is the only test-grade HTTP
client — no live servers, no port allocations.

## How to extend

When adding new coverage, prefer:

- A new test in one of the existing `test_*.py` files if it fits the
  theme; a new file if not.
- Reuse fixtures from `conftest.py` (don't redefine `clean_state`).
- For new dispatch-related tests, extend the mocks in `strategies.py`
  first and add the matching anchor watchdog in
  `test_outlook_com_order.py::test_strategies_mirror_anchors_match_production`.

## Coverage estimate (approximate)

The suite touches (and exercises) most of `web/app.py`. Specifically:

- `web/app.py:80-119` (`/api/upload-eml`)  — exercised.
- `web/app.py:122-134` (`/api/preview`)   — `web_app._session` read.
- `web/app.py:241-318` (`/api/send` + helpers) — exercised (the staging write
  path; `_PROGRESS_FILE.unlink` path; `_STAGING_FILE` parent mkdir).
- `web/app.py:137-194` (sources / views) — touched via the `_build_repository`
  patch only; no full repo round-trip.

For `send_from_staging.py`:

- `send_from_staging.py:36-42` (`get_images`)   — mirrored.
- `send_from_staging.py:86-101` (load + diag)   — `get_images` is mirrored;
  the print statement's *content* is asserted in `test_diagnostic_log.py`.
- `send_from_staging.py:132-237` (dispatch loop) — mirrored line-by-line.
- `send_from_staging.py:238-273` (final write_progress + tracking) — NOT
  covered (no behavior contract worth protecting yet; we cover the
  bug surface, not the progress bookkeeping).

End-to-end coverage target: ~75% of `web/app.py` and ~55% of
`send_from_staging.py`. The remaining ~45% of `send_from_staging.py`
is progress-file writes, namespace/sync calls and the `wait_for_sent`
polling loop, which are not in scope for the reported bugs.
