import unittest
from task_recovery import (operation_key, preflight_disposition,
    callback_disposition, defer_uncertain, is_duplicate_blocked, mark_resolved)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.key = operation_key('apple_notes.create', '测试备忘录', text='正文')
        self.entry = dict(key=self.key, route='apple_notes.create', title='测试备忘录', token='abc')

    def test_same_intent_stable(self):
        self.assertEqual(self.key, operation_key('apple_notes.create', '测试备忘录', text='正文'))
        self.assertNotEqual(self.key, operation_key('apple_notes.create', '测试备忘录', text='另一段正文'))

    def test_unknown_route_rejected(self):
        with self.assertRaises(ValueError):
            operation_key('shell.exec', 'abc')

    def test_missing_module_never_waits_for_callback(self):
        d = preflight_disposition('apple_notes.create', False)
        self.assertEqual(d['status'], 'unavailable')
        self.assertFalse(d['dispatched'])
        self.assertFalse(d['manual_required'])

    def test_callback_ok_is_only_report(self):
        self.assertEqual(callback_disposition(True, 'ok')['status'], 'reported_ok')

    def test_timeout_never_auto_retries(self):
        d = callback_disposition(True, 'expired')
        self.assertEqual(d['status'], 'write_unknown')
        self.assertTrue(d['archive'])
        self.assertFalse(d['retry'])

    def test_unrelated_task_can_continue(self):
        q, created = defer_uncertain([], self.entry, '无回调', now='2026-10-17T12:30')
        self.assertTrue(created)
        self.assertTrue(is_duplicate_blocked(q, self.key))
        another = operation_key('calendar.create', '不同任务')
        self.assertFalse(is_duplicate_blocked(q, another))

    def test_pending_archive_is_idempotent(self):
        q, _ = defer_uncertain([], self.entry, '无回调')
        q2, created = defer_uncertain(q, self.entry, '仍无回调')
        self.assertFalse(created)
        self.assertEqual(q, q2)
        self.assertEqual(len(q2), 1)

    def test_explicit_resolution_only(self):
        q, _ = defer_uncertain([], self.entry, '无法确定')
        with self.assertRaises(ValueError):
            mark_resolved(q, self.key, 'not sure')
        done, changed = mark_resolved(q, self.key, False)
        self.assertTrue(changed)
        self.assertFalse(is_duplicate_blocked(done, self.key))

    def test_corrupt_queue_fails_closed(self):
        with self.assertRaises(ValueError):
            defer_uncertain(None, self.entry, '无法确定')
        with self.assertRaises(ValueError):
            is_duplicate_blocked(None, self.key)

    def test_callback_without_dispatch(self):
        d = callback_disposition(False, 'ok')
        self.assertEqual(d['status'], 'not_dispatched')
        self.assertFalse(d['archive'])


if __name__ == '__main__':
    unittest.main()
