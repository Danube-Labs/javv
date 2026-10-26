"""The release this backend belongs to. release-please rewrites the annotated line in every release
PR (`extra-files` in `release-please-config.json`), so dev checkouts, CI and images all report the
last released version with no build step. `tests/test_meta_route.py` holds it equal to
`.release-please-manifest.json`."""

APP_VERSION = "0.8.9"  # x-release-please-version
