"""Test suite for the masive_emails project.

This package contains the regression suite that protects against the two
known bugs:

    A) Outlook COM recycling the subject of a previous dispatch.
    B) Cross-contamination between two consecutive EML loads
       (load A -> send -> load B -> send).

Tests run with ``pytest`` on Linux despite the production code being a
Windows + win32com binary; see README.md for the mocking strategy.
"""
