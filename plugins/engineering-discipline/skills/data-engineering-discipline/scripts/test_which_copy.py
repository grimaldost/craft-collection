"""Tests for which_copy. Runnable with pytest or `python test_which_copy.py`."""

from __future__ import annotations

import importlib.metadata as md

from which_copy import classify, distribution_version, main, resolve

SITE = ['/venv/lib/python3.13/site-packages']


def test_a_module_resolved_inside_site_packages_is_the_installed_copy():
    got = classify('lib', '/venv/lib/python3.13/site-packages/lib/__init__.py', '1.2.0', SITE)
    assert got['state'] == 'installed'
    assert got['shadowed'] is False


def test_an_editable_checkout_shadowing_an_installed_distribution_is_flagged():
    # The recorded failure: the source read end-to-end was not the code that ran.
    got = classify('lib', '/w/lib-src/src/lib/__init__.py', '1.2.0', SITE)
    assert got['state'] == 'shadowing'
    assert got['shadowed'] is True


def test_a_local_module_with_no_installed_distribution_is_reported_not_flagged():
    got = classify('lib', '/w/lib-src/src/lib/__init__.py', None, SITE)
    assert got['state'] == 'local-only'
    assert got['shadowed'] is False


def test_a_module_with_no_file_is_named_rather_than_assumed_clean():
    got = classify('sys', None, None, SITE)
    assert got['state'] == 'no-file'
    assert got['shadowed'] is False


def test_a_stdlib_module_is_not_misread_as_a_local_checkout():
    # sysconfig's stdlib roots count as installed roots, or every stdlib import
    # reports as a shadowing checkout and the signal drowns.
    assert resolve('json')['state'] == 'installed'


def test_cli_resolves_a_real_module_and_refuses_one_that_does_not_import():
    assert main(['json']) == 0
    assert main(['definitely_not_a_module_xyz']) == 2
    # nothing to resolve is a usage error, never a clean bill of health
    assert main([]) == 2


def _with_fake_metadata(mapping: dict[str, list[str]], versions: dict[str, str]):
    """Swap importlib.metadata's two lookups for the duration of one assertion.

    The metadata lookup is where the live false negative lived, and every other
    test in this file hands `version` to `classify` by hand -- so `resolve`'s
    lookup was exercised only on `json`, a stdlib module with no distribution.
    A gate that cannot reach the defective line is not a gate.
    """
    real = (md.packages_distributions, md.version)

    def fake_version(dist):
        if dist in versions:
            return versions[dist]
        raise md.PackageNotFoundError(dist)

    md.packages_distributions = lambda: mapping
    md.version = fake_version
    return real


def test_a_distribution_named_differently_from_its_import_name_is_still_found():
    # yaml/PyYAML, sklearn/scikit-learn, PIL/pillow, cv2/opencv-python,
    # bs4/beautifulsoup4, dateutil/python-dateutil. version('yaml') raises, so the
    # version came back None and a shadowing checkout was downgraded to
    # 'local-only' -- WHICH-COPY OK, exit 0, on the exact case the tool exists for.
    real = _with_fake_metadata({'yaml': ['PyYAML']}, {'PyYAML': '6.0.2'})
    try:
        assert distribution_version('yaml') == ('6.0.2', 'PyYAML')
        got = classify('yaml', '/w/checkout/yaml/__init__.py', '6.0.2', SITE, 'PyYAML')
        assert got['state'] == 'shadowing'
        assert got['shadowed'] is True
    finally:
        md.packages_distributions, md.version = real


def test_a_module_with_no_distribution_anywhere_still_reports_none():
    real = _with_fake_metadata({}, {})
    try:
        assert distribution_version('some_local_module') == (None, None)
    finally:
        md.packages_distributions, md.version = real


if __name__ == '__main__':
    test_a_module_resolved_inside_site_packages_is_the_installed_copy()
    test_an_editable_checkout_shadowing_an_installed_distribution_is_flagged()
    test_a_local_module_with_no_installed_distribution_is_reported_not_flagged()
    test_a_module_with_no_file_is_named_rather_than_assumed_clean()
    test_a_stdlib_module_is_not_misread_as_a_local_checkout()
    test_cli_resolves_a_real_module_and_refuses_one_that_does_not_import()
    test_a_distribution_named_differently_from_its_import_name_is_still_found()
    test_a_module_with_no_distribution_anywhere_still_reports_none()
    print('ok: all which_copy tests passed')
