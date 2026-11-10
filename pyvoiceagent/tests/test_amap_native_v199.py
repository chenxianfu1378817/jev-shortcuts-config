# -*- coding: utf-8 -*-
"""V1.9.9: iPhone Amap must open via native iosamap scheme, not web.

Mocked unit tests: do not assert that the user's installed Amap App has opened.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

CORE = Path(__file__).resolve().parents[1] / 'agent_core_1_9_9.py'


class AmapNativeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = CORE.read_text('utf-8')
        compile(src, str(CORE), 'exec')
        cls.source = src
        spec = importlib.util.spec_from_file_location('pya_199', str(CORE))
        cls.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.agent)

    @staticmethod
    def choice(route='amap_search', text='民歌湖'):
        return {'tool':'app.navigate','shortcut_id':route,'text':text}

    def test_native_poi_scheme_contains_destination(self):
        label, url = self.agent._app_route_target(self.choice())
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme,'iosamap')
        self.assertEqual(parsed.netloc,'poi')
        self.assertEqual(params['name'],['民歌湖'])
        self.assertEqual(params['sourceApplication'],['PYVoiceAgent'])
        self.assertNotIn('https:',url)
        self.assertIn('高德',label)

    def test_user_navigation_phrase_is_local_routed(self):
        samples=('帮我打开高德导航去民歌湖','高德地图导航到民歌湖',
                 '请用高德地图驾车导航至民歌湖')
        for phrase in samples:
            with self.subTest(phrase=phrase):
                result=self.agent._local_quick_intent(phrase)
                self.assertIsNotNone(result)
                self.assertEqual(result['type'],'LOCAL')
                self.assertEqual(result['shortcut_id'],'amap_search')
                self.assertEqual(result['text'],'民歌湖')

    def test_destination_is_url_encoded_as_data(self):
        _, url=self.agent._app_route_target(self.choice(text='南宁九洲国际停车场入口'))
        self.assertEqual(parse_qs(urlparse(url).query)['name'],['南宁九洲国际停车场入口'])

    def test_amap_does_not_require_old_router(self):
        observed=[]
        shortcut=types.ModuleType('shortcuts')
        shortcut.open_url=lambda url:observed.append(url)
        with patch.dict(sys.modules,{'shortcuts':shortcut}):
            with patch.object(self.agent,'_app_router_enabled',return_value=False):
                result=self.agent._app_route_handoff({},self.choice())
        self.assertEqual(result['status'],'ok')
        self.assertIs(result['verified'],False)
        self.assertEqual(len(observed),1)
        self.assertTrue(observed[0].startswith('iosamap://poi?'))
        self.assertNotIn('shortcuts://',observed[0])
        self.assertIn('选择',result['result'])

    def test_amap_launch_error_does_not_fallback_to_web(self):
        urls=[]
        shortcut=types.ModuleType('shortcuts')
        def broken(url):
            urls.append(url)
            raise RuntimeError('Amap unavailable')
        shortcut.open_url=broken
        with patch.dict(sys.modules,{'shortcuts':shortcut}):
            with patch.object(self.agent,'_app_router_enabled',return_value=False):
                result=self.agent._app_route_handoff({},self.choice())
        self.assertEqual(result['status'],'failed')
        self.assertEqual(len(urls),1)
        self.assertTrue(urls[0].startswith('iosamap://'))

    def test_other_apps_keep_existing_router(self):
        observed=[]
        shortcut=types.ModuleType('shortcuts')
        shortcut.open_url=observed.append
        with patch.dict(sys.modules,{'shortcuts':shortcut}):
            with patch.object(self.agent,'_app_router_enabled',return_value=True):
                result=self.agent._app_route_handoff({},
                    self.choice(route='wechat_scan',text=''))
        self.assertEqual(result['status'],'ok')
        self.assertTrue(observed[0].startswith('shortcuts://run-shortcut?'))

    def test_other_apps_require_router(self):
        with patch.object(self.agent,'_app_router_enabled',return_value=False):
            result=self.agent._app_route_handoff({},
                self.choice(route='wechat_scan',text=''))
        self.assertEqual(result['status'],'unavailable')

    def test_input_hygiene_and_no_arbitrary_scheme(self):
        for bad in ('\n','\r','\x00'):
            with self.assertRaises(ValueError):
                self.agent._app_route_target(self.choice(text='民歌湖'+bad))
        with self.assertRaises(ValueError):
            self.agent._app_route_target(self.choice(route='unsafe_browser',text='https://example.com'))

    def test_ai_tool_available_for_native_map(self):
        with patch.object(self.agent,'_app_router_enabled',return_value=False):
            self.assertIn('app.navigate',self.agent.available_tool_catalog())

    def test_all_existing_tools_still_present(self):
        for token in ('def input_voice(', 'def _manual_voice_record(',
                      'def _bu_capture_and_calendar(', 'def _history_search(',
                      'def immediate_check_and_update(', "if sys.argv[1] == 'bu_close'",
                      "if sys.argv[1] == 'voice'", 'def bridge_callback('):
            self.assertIn(token,self.source)
        self.assertNotIn('https://uri.amap.com/search?callnative=1',self.source)

if __name__=='__main__':
    unittest.main(verbosity=2)
