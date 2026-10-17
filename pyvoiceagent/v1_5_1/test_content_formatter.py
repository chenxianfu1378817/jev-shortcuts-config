import unittest
from content_formatter import reminder_notes, apple_note_body, calendar_notes


class ContentFormatterTests(unittest.TestCase):
    def test_reminder_only_user_text(self):
        self.assertEqual(reminder_notes('测试语音助手自动创建提醒事项'),
                         '测试语音助手自动创建提醒事项')

    def test_reminder_empty(self):
        self.assertEqual(reminder_notes(None), '')

    def test_note_has_single_title(self):
        self.assertEqual(apple_note_body('采购记录', '沥青价格待核实'),
                         '采购记录\n\n沥青价格待核实')

    def test_note_does_not_double_title(self):
        self.assertEqual(apple_note_body('采购记录', '采购记录\n\n沥青价格待核实'),
                         '采购记录\n\n沥青价格待核实')

    def test_no_generated_metadata(self):
        result = apple_note_body('测试', '正文')
        self.assertNotIn('PYVoiceAgent:', result)
        self.assertNotIn('token', result)

    def test_calendar_note_stays_clean(self):
        self.assertEqual(calendar_notes('周会准备'), '周会准备')

    def test_invalid_body_rejected(self):
        with self.assertRaises(ValueError):
            apple_note_body('测试', '')


if __name__ == '__main__':
    unittest.main()
