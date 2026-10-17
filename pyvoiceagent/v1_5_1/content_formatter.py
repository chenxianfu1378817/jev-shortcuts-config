# -*- coding: utf-8 -*-
"""Prepare user-visible iOS content without exposing internal task metadata."""


def reminder_notes(notes):
    """Do not append an internal transaction marker to reminder notes."""
    if notes is None:
        return ''
    if not isinstance(notes, str):
        raise TypeError('Notes must be text')
    return notes.strip()[:1400]


def apple_note_body(title, text):
    """Apple Notes uses its first line as a title; keep one title, then body."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Note title is required')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Note body is required')
    heading = title.strip()
    body = text.strip()
    first, _, rest = body.partition('\n')
    if first.strip() == heading:
        body = rest.strip()
    return heading + ('\n\n' + body if body else '')


def calendar_notes(notes):
    """Store calendar notes verbatim, with no tracking markers."""
    return reminder_notes(notes)
