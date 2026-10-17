import unittest
from legacy_migration import migrate_v143_pending, block_legacy_replay


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.old = {'id': 'abcd', 'status': 'awaiting_callback',
                    'pending': {'tool':'apple_notes.create',
                                'title':'PYVoiceAgent综合测试-备忘录',
                                'marker':'[PYVoiceAgent:abcd:4]', 'token':'tokenA'}}

    def test_migrate_pending(self):
        q, created = migrate_v143_pending(self.old, [])
        self.assertTrue(created)
        self.assertEqual(q[0]['route'], 'apple_notes.create')
        self.assertTrue(q[0]['key'].startswith('legacy:'))

    def test_different_task_not_blocked(self):
        q, _ = migrate_v143_pending(self.old, [])
        self.assertFalse(block_legacy_replay(q, 'calendar.create', '开会'))

    def test_same_title_blocked(self):
        q, _ = migrate_v143_pending(self.old, [])
        self.assertTrue(block_legacy_replay(q, 'apple_notes.create', 'PYVoiceAgent综合测试-备忘录'))

    def test_idempotent(self):
        q, _ = migrate_v143_pending(self.old, [])
        q2, created = migrate_v143_pending(self.old, q)
        self.assertFalse(created)
        self.assertEqual(q, q2)

    def test_finished_task_noop(self):
        state = dict(self.old, status='finished')
        self.assertEqual(migrate_v143_pending(state, []), ([], False))


if __name__ == '__main__':
    unittest.main()
