import importlib.util, unittest, tempfile, pathlib, json, os
from datetime import datetime, timezone, timedelta
TZ = timezone(timedelta(hours=8))
p = pathlib.Path(__file__).resolve().parents[1] / 'bu_snapshot_module.py'
spec = importlib.util.spec_from_file_location('bu192', p)
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.DATA_DIR = '/tmp'
m.atomic_json=lambda path, data: pathlib.Path(path).write_text(json.dumps(data,ensure_ascii=False), encoding='utf-8')

def row(symbol,at='113000',price='5010',volume='470',position='100'):
    fields=['石油沥青'+symbol,at,'3500','3700','3500','3450','3600','3610',price,'3550','3460','1','2',position,volume]
    return 'var hq_str_nf_{}="{}";'.format(symbol,','.join(fields))

class TestQuality(unittest.TestCase):
    def test_screenshot_midday_future_timestamp_separated(self):
        def fetch(url):return '\n'.join([row('BU2611'),row('BU2612',price='4509'),row('BU2710',at='150000',price='3977')])
        snap=m._bu_build_snapshot('test',datetime(2026,11,10,12,51,53,tzinfo=TZ),fetch)
        self.assertEqual(snap['valid_quote_count'],2)
        self.assertEqual(snap['suspect_quote_count'],1)
        self.assertEqual(snap['received_quote_count'],3)
        self.assertEqual(snap['suspect_records'][0]['contract'],'BU2710')
        self.assertEqual(snap['suspect_records'][0]['last_price'],3977.0)
        self.assertIn('时刻可疑',m._bu_report(snap))
        self.assertIn('BU2710',m._bu_report(snap))

    def test_not_auto_delete_suspect_quote(self):
        snap=m._bu_build_snapshot('test',datetime(2026,11,10,12,51,53,tzinfo=TZ),lambda url:row('BU2710',at='150000'))
        self.assertEqual(snap['valid_quote_count'],0)
        self.assertEqual(snap['suspect_quote_count'],1)
        self.assertIn('BU2710',m._bu_report(snap))

    def test_in_session_night_records_retained(self):
        snap=m._bu_build_snapshot('night',datetime(2026,11,10,23,3,tzinfo=TZ),lambda url: row('BU2611',at='225955'))
        self.assertEqual(snap['valid_quote_count'],1)
        self.assertEqual(snap['suspect_quote_count'],0)
        self.assertEqual(snap['records'][0]['quality'],'clock_only_unverified_date')

    def test_in_session_day_records_retained(self):
        snap=m._bu_build_snapshot('day',datetime(2026,11,10,15,3,tzinfo=TZ),lambda url:row('BU2710',at='150000'))
        self.assertEqual(snap['valid_quote_count'],1)
        self.assertIn('日期仍未核验',m._bu_report(snap))

    def test_after_early_offhour_not_assume_close(self):
        with self.assertRaises(RuntimeError):
            m._bu_build_snapshot('day',datetime(2026,11,10,15,3,tzinfo=TZ),lambda url:row('BU2611',at='113000'))

    def test_persist_suspicious_record_in_json_and_text(self):
        with tempfile.TemporaryDirectory() as path:
            snap=m.bu_capture_run('test',datetime(2026,11,10,12,51,53,tzinfo=TZ),lambda url:row('BU2710',at='150000'),path)
            files=list(pathlib.Path(path).iterdir())
            self.assertEqual(len(files),2)
            raw=json.loads(next(f for f in files if f.suffix=='.json').read_text(encoding='utf-8'))
            self.assertEqual(raw['suspect_quote_count'],1)
            text=next(f for f in files if f.suffix=='.txt').read_text(encoding='utf-8')
            self.assertIn('[时刻可疑]',text)

if __name__=='__main__':unittest.main(verbosity=2)