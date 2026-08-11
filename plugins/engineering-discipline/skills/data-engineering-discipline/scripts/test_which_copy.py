"""Tests for which_copy. Runnable with pytest or `python test_which_copy.py`."""

from __future__ import annotations

from which_copy import classify, main, resolve

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


if __name__ == '__main__':
    test_a_module_resolved_inside_site_packages_is_the_installed_copy()
    test_an_editable_checkout_shadowing_an_installed_distribution_is_flagged()
    test_a_local_module_with_no_installed_distribution_is_reported_not_flagged()
    test_a_module_with_no_file_is_named_rather_than_assumed_clean()
    test_a_stdlib_module_is_not_misread_as_a_local_checkout()
    test_cli_resolves_a_real_module_and_refuses_one_that_does_not_import()
    print('ok: all which_copy tests passed')
