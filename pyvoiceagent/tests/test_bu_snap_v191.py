import unittest, tempfile, os, json, importlib.util, pathlib
from datetime import datetime, timezone, timedelta
p=str(pathlib.Path(__file__).resolve().parents[1] / 'bu_snapshot_module.py') if pathlib.Path(__file__).resolve().parent.name == 'tests' else str(pathlib.Path(__file__).with_name('bu_snapshot_module.py'))
spec=importlib.util.spec_from_file_location('busnapshot',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.DATA_DIR='/mnt/data'
m.atomic_json=lambda path,data:open(path,'w',encoding='utf-8').write(json.dumps(data,ensure_ascii=False))
TZ=timezone(timedelta(hours=8))
def row(symbol,at='225955',price='3654',volume='15000',position='100'):
    f=['沥青'+symbol,at,'3500','3700','3500','3450','3600','3610',price,'3550','3460','1','2',position,volume]
    return 'var hq_str_nf_{}="{}";'.format(symbol,','.join(f))
def fetch(url):
    return (row('BU2611')+'\n'+row('BU2612',price='3552')).encode('gbk')
class TestBU(unittest.TestCase):
    def test_symbols(self):
        x=m._bu_contract_codes(datetime(2026,11,10,23,4,tzinfo=TZ));self.assertEqual(x[0],'BU2611');self.assertEqual(len(x),28);self.assertEqual(x[-1],'BU2902')
    def test_parse(self):
        x=m._bu_parse_quote_response(row('BU2611'));self.assertEqual(x['BU2611']['last_price'],3654);self.assertEqual(x['BU2611']['quote_clock'],'225955')
    def test_invalid(self):
        self.assertFalse(m._bu_parse_quote_response(row('BU2611',price='0')))
        self.assertFalse(m._bu_parse_quote_response(row('BU2611',at='bad')))
    def test_clock(self):
        self.assertTrue(m._bu_accept_quote_clock('225955','night'))
        self.assertFalse(m._bu_accept_quote_clock('225955','day'))
        self.assertFalse(m._bu_accept_quote_clock('144955','night'))
        self.assertTrue(m._bu_accept_quote_clock('145955','day'))
    def test_night_snapshot(self):
        x=m._bu_build_snapshot('night',datetime(2026,11,10,23,3,tzinfo=TZ),fetch)
        self.assertEqual(x['valid_quote_count'],2);self.assertEqual(x['session_calendar_date_bj'],'2026-11-10')
    def test_weekend(self):
        with self.assertRaises(ValueError):m._bu_build_snapshot('night',datetime(2026,11,14,23,3,tzinfo=TZ),fetch)
    def test_offhour(self):
        with self.assertRaises(ValueError):m._bu_build_snapshot('night',datetime(2026,11,10,15,3,tzinfo=TZ),fetch)
    def test_stale_refusal(self):
        def stale(url):return row('BU2611',at='145955')
        with self.assertRaises(RuntimeError):m._bu_build_snapshot('night',datetime(2026,11,10,23,3,tzinfo=TZ),stale)
    def test_day_snapshot(self):
        def daytime(url):return row('BU2611',at='145959')
        x=m._bu_build_snapshot('day',datetime(2026,11,10,15,3,tzinfo=TZ),daytime);self.assertEqual(x['valid_quote_count'],1)
    def test_persist_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            a=m.bu_capture_run('night',datetime(2026,11,10,23,3,tzinfo=TZ),fetch,d)
            b=m.bu_capture_run('night',datetime(2026,11,10,23,3,tzinfo=TZ),fetch,d)
            self.assertEqual(len(os.listdir(d)),4)
    def test_network_failure(self):
        with self.assertRaises(OSError):m._bu_build_snapshot('night',datetime(2026,11,10,23,3,tzinfo=TZ),lambda u: (_ for _ in ()).throw(OSError('offline')))
if __name__=='__main__':unittest.main(verbosity=2)