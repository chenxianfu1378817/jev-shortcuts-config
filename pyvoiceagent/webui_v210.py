# -*- coding: utf-8 -*-
"""PYVoiceAgent V2.1.0 bundled offline WebView UI."""
import json
WEBUI_HTML = "<!doctype html>\n<html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover\">\n<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'\">\n<title>PYVoiceAgent</title>\n<style>\n:root{--accent:#8a62d8;--bg:#101319;--surface:#1c222c;--raised:#252c38;--text:#f3f5fa;--muted:#abb3c1;--border:#343d4b;--light:#fff;--danger:#f57c85}\n*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}\nhtml,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,\"PingFang SC\",Arial,sans-serif}\nbutton,input,textarea{font:inherit}button{cursor:pointer;border:0}button:disabled{opacity:.55;cursor:default}\n.app{max-width:760px;margin:0 auto;padding: max(62px,env(safe-area-inset-top,0px)) 18px calc(104px + env(safe-area-inset-bottom,0px));min-height:100dvh}\n.header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 0 24px}\n.logo{font-weight:800;font-size:27px;letter-spacing:-.7px;line-height:1.2}.subtitle{font-size:12px;color:var(--muted);margin-top:8px}\n.close{background:var(--raised);color:var(--text);padding:11px 17px;border-radius:14px;font-size:13px}\n.card{background:var(--surface);border-radius:21px;padding:18px}.hero{background:var(--raised);margin-bottom:13px;padding:18px 19px}\n.hero .heading{font-size:19px;font-weight:750}.hero .sub{color:var(--muted);font-size:12px;margin-top:10px}\n.status{color:var(--accent);font-size:12px;margin-top:11px}.status b{font-weight:650}\n.primary{display:block;text-align:left;background:var(--accent);color:var(--light);width:100%;min-height:124px;border-radius:23px;padding:21px 19px;margin-bottom:17px}\n.primary .head{font-size:24px;font-weight:750;display:flex;align-items:center;justify-content:space-between}\n.primary .hint{font-size:13px;opacity:.93;margin-top:15px}.primary .arrow{font-size:27px;font-weight:400}\n.section{display:flex;justify-content:space-between;align-items:center;margin:18px 2px 12px}.section h2{margin:0;font-size:13px;color:var(--muted);font-weight:700}\n.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.tile{min-height:111px;padding:15px 14px;display:flex;flex-direction:column;justify-content:space-between;text-align:left;color:var(--text);min-width:0}\n.tile .ico{color:var(--accent);font-size:21px;line-height:1.1}.tile .title{font-weight:750;font-size:16px;margin-top:5px}.tile .hint{color:var(--muted);font-size:11px;line-height:1.4;margin-top:5px}\n.utility{min-height:83px}.utility .title{font-size:14px}.utility .ico{font-size:19px}.utility .hint{font-size:10px}\n.recent{margin-top:17px;padding:17px 18px}.recent .title{font-size:13px;font-weight:750}.recent .body{font-size:12px;color:var(--muted);line-height:1.6;margin-top:7px;white-space:pre-wrap;word-break:break-word}\n.page-head{display:flex;align-items:center;gap:12px;margin:0 0 20px}.page-head h1{font-size:22px;margin:0;flex:1;min-width:0}.back{color:var(--text);background:var(--raised);border-radius:12px;padding:10px 13px;font-size:13px}\n.field{background:var(--raised);border:1px solid var(--border);border-radius:14px;color:var(--text);width:100%;padding:13px;outline:none;font-size:15px}\n.field:focus{border-color:var(--accent)}textarea.field{min-height:160px;resize:vertical;line-height:1.65}.btn{border-radius:13px;padding:13px 15px;color:var(--text);background:var(--raised);min-height:46px}.btn.emphasis{background:var(--accent);color:var(--light);font-weight:650}\n.btn.full{width:100%;margin-top:13px}.muted{color:var(--muted)}.small{font-size:12px}.note{font-size:12px;line-height:1.7;color:var(--muted);margin:12px 2px}.bodytext{white-space:pre-wrap;word-break:break-word;line-height:1.7;font-size:14px}\n.stack{display:flex;flex-direction:column;gap:11px}.row-actions{display:flex;gap:10px}.row-actions>*{flex:1;min-width:0}\n.record{text-align:left;width:100%;color:var(--text);padding:16px}.record .title{font-size:15px;font-weight:700;line-height:1.45}.record .meta{color:var(--muted);font-size:11px;margin-top:7px}.record .preview{color:var(--muted);font-size:12px;margin-top:8px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}\n.event{padding:16px}.event .title{font-weight:700;font-size:16px}.event .time{margin-top:8px;font-size:13px;color:var(--muted)}\n.nav{position:fixed;z-index:10;bottom:max(12px,env(safe-area-inset-bottom,0px));left:16px;right:16px;max-width:724px;margin:0 auto;background:var(--surface);border:1px solid var(--border);border-radius:21px;display:grid;grid-template-columns:repeat(4,1fr);padding:5px;box-shadow:0 15px 38px rgba(0,0,0,.13)}\n.nav button{border-radius:15px;background:transparent;color:var(--muted);font-size:13px;min-height:51px}.nav button.active{background:var(--accent);color:var(--light);font-weight:750}\n.theme-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.theme-button{display:flex;gap:10px;align-items:center;padding:13px 11px;background:var(--surface);color:var(--text);border-radius:15px;text-align:left;font-size:13px}.swatch{width:20px;height:20px;border-radius:50%;flex-shrink:0;border:1px solid rgba(255,255,255,.15)}.theme-button.active{outline:2px solid var(--accent)}\n.pills{display:flex;gap:8px;flex-wrap:wrap}.pills .btn{min-height:40px;font-size:12px;padding:9px}.pills .active{background:var(--accent);color:var(--light)}\n.notice{position:fixed;z-index:30;left:18px;right:18px;bottom:calc(90px + env(safe-area-inset-bottom,0px));max-width:600px;margin:0 auto;background:var(--raised);color:var(--text);border:1px solid var(--border);border-radius:14px;padding:12px 16px;text-align:center;font-size:12px;box-shadow:0 10px 25px rgba(0,0,0,.2)}\n@media(min-width:640px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}.utility-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.app{padding-left:27px;padding-right:27px}.primary{min-height:138px}}\n@media(max-width:355px){.logo{font-size:23px}.tile .title{font-size:14px}.tile .hint{font-size:10px}.nav button{font-size:12px}.app{padding-left:14px;padding-right:14px}}\n</style>\n<script>/*__BOOTSTRAP__*/</script></head><body><main class=\"app\"><header class=\"header\"><div><div class=\"logo\">PYVoiceAgent</div><div id=\"version\" class=\"subtitle\"></div></div><button class=\"close\" id=\"close\">退出</button></header><div id=\"content\"></div></main><nav class=\"nav\" id=\"nav\"></nav><div id=\"notice\" class=\"notice\" hidden></div>\n<script>\n(function(){'use strict';\nconst D=window.PYAGENT_BOOT, A=['home','result','archive','settings'];\nlet page=D.page||'home', query='', currentArchive=null, archives=D.archives||[], preview=D.result||{}, theme=D.appearance||{}, tools=D.tools||[];\nconst $=id=>document.getElementById(id);\nconst node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e};\nconst child=(parent,...parts)=>{parts.forEach(x=>parent.appendChild(x));return parent};\nfunction btn(label,cls,onClick){const b=node('button',cls,label);b.type='button';b.addEventListener('click',onClick);return b}\nfunction bridge(action,payload){const q='pyagent-ui://dispatch?nonce='+encodeURIComponent(D.nonce)+'&action='+encodeURIComponent(action)+'&payload='+encodeURIComponent(payload===undefined?'':String(payload));window.location.href=q}\nfunction notify(message){const t=$('notice');t.textContent=String(message);t.hidden=false;setTimeout(()=>t.hidden=true,2200)}\nfunction jump(p){page=p;render();window.scrollTo(0,0)}\nfunction heading(title,parent='home'){return child(node('div','page-head'),btn('‹ 返回','back',()=>jump(parent)),node('h1','',title))}\nfunction section(title){return child(node('div','section'),node('h2','',title))}\nfunction tile(icon,title,hint,action,utility=false){const t=node('button','card tile'+(utility?' utility':''));child(t,node('div','ico',icon),node('div','title',title),node('div','hint',hint));t.onclick=action;return t}\nfunction statusName(s){return ({finished:'已完成',awaiting_callback:'等待系统回传',running:'执行中',ready:'准备中',needs_review:'待核验',needs_input:'等待补充',replan_pending:'等待补充',paused:'已暂停',failed:'执行异常'})[s]||'尚无任务'}\nfunction renderHome(){const root=node('div');const h=node('div','card hero');child(h,node('div','heading','你的智能任务助手'),node('div','sub','语音调度  ·  AI 规划  ·  本地执行'),node('div','status','最近任务：'+statusName(D.status)));root.appendChild(h);\n const main=btn('','primary',()=>bridge('voice',''));child(main,child(node('div','head'),node('span','','语音执行任务'),node('span','arrow','›')),node('div','hint','手动录音 · 说完点击「完成」'));root.appendChild(main);\n const quick=node('div','grid');child(quick,tile('✎','文字任务','输入指令，自动规划',()=>jump('input')),tile('▤','处理剪贴板','提取和整理文字',()=>bridge('clipboard','')),tile('✓','执行结果','查看最新任务反馈',()=>jump('result')),tile('◷','历史档案','搜索本机历史记录',()=>jump('archive')));\n child(root,section('常用功能'),quick,section('管理与设置'));\n const utils=node('div','grid utility-grid');child(utils,tile('↻','检查更新','GitHub 安全在线升级',()=>bridge('update',''),true),tile('⚙','设置与工具','主题、模块、诊断',()=>jump('settings'),true));root.appendChild(utils);\n if(D.goal){const recent=node('div','card recent');child(recent,node('div','title','最近一次任务'),node('div','body',D.goal));root.appendChild(recent)}return root}\nfunction renderInput(){const root=node('div');root.appendChild(heading('文字任务'));const t=node('textarea','field');t.id='task-input';t.placeholder='例如：帮我查询本周日程并分析冲突';t.maxLength=2000;root.appendChild(t);root.appendChild(btn('交给 AI 执行','btn emphasis full',()=>{const value=t.value.trim();if(!value)return notify('请先输入任务内容');bridge('input',value)}));root.appendChild(node('p','note','任务由原有 Python 本地工具及 DeepSeek 执行。涉及外部系统操作时仍按原授权规则处理。'));return root}\nfunction renderResult(){const root=node('div');root.appendChild(heading('执行结果'));const model=preview||{};const box=node('div','card');child(box,node('h2','',model.title||'暂无执行结果'),node('div','note',model.subtitle||''));if(Array.isArray(model.items)&&model.items.length){const list=node('div','stack');model.items.forEach(item=>{const e=node('div','card event');child(e,node('div','title',item.title||''),node('div','time',item.time||''));list.appendChild(e)});box.appendChild(list)}if(model.body)box.appendChild(node('div','bodytext',model.body));if(model.notice)box.appendChild(node('div','note',model.notice));root.appendChild(box);const actions=node('div','row-actions');child(actions,btn('复制结果','btn',()=>bridge('copy',model.copy||model.body||'')),btn('完成','btn emphasis',()=>D.modal?bridge('close',''):jump('home')));root.appendChild(actions);return root}\nfunction renderArchive(){const root=node('div');root.appendChild(heading('历史档案'));const input=node('input','field');input.type='search';input.placeholder='搜索历史任务、BU 行情、客户';input.maxLength=100;input.value=query;const bar=node('div','row-actions');input.style.flex='4';child(bar,input,btn('搜索','btn emphasis',()=>{query=input.value.trim();bridge('search',query)}));root.appendChild(bar);root.appendChild(node('p','note','仅在本机历史记录中查询，不上传内容。'));const list=node('div','stack');list.id='archive-list';root.appendChild(list);paintArchive(list);return root}\nfunction paintArchive(list){list.replaceChildren();if(!archives.length){list.appendChild(node('div','card muted','暂无匹配记录'));return}archives.forEach(item=>{const b=node('button','card record');child(b,node('div','title',item.title||'任务记录'),node('div','meta',(item.created||'').slice(0,16)+'  ·  '+(item.quality||'')),node('div','preview',item.preview||''));b.onclick=()=>bridge('detail',item.key||'');list.appendChild(b)})}\nfunction renderDetail(){const root=node('div');root.appendChild(heading('档案详情','archive'));const item=currentArchive||{};const card=node('div','card');child(card,node('h2','',item.title||'历史任务'),node('div','note',item.created||''),node('div','bodytext',item.text||''));root.appendChild(card);const act=node('div','row-actions');child(act,btn('复制全文','btn',()=>bridge('history_copy',item.key||'')),btn('分享／导出','btn emphasis',()=>bridge('history_share',item.key||'')));root.appendChild(act);return root}\nfunction setting(title,description,cb){const b=node('button','card record');child(b,node('div','title',title),node('div','preview',description));b.onclick=cb;return b}\nfunction renderSettings(){const root=node('div');root.appendChild(heading('设置中心'));const stack=node('div','stack');child(stack,setting('外观与主题','8套配色 · 深色／浅色／跟随系统',()=>jump('appearance')),setting('DeepSeek AI 配置','安全管理 API Key',()=>bridge('ai_settings','')),setting('语音隐私与授权','控制发送文本及手动录音',()=>bridge('voice_privacy','')),setting('工具库','搜索已登记的本地工具',()=>jump('tools')),setting('系统模块首次验收','必要时验证快捷指令权限',()=>bridge('module_setup','')),setting('高级与故障排查','任务恢复、回传诊断与安全设置',()=>jump('advanced')));root.appendChild(stack);return root}\nconst themeColors={'活力橙':'#F07828','科技蓝':'#3979E8','翡翠绿':'#159F7B','典雅紫':'#8A62D8','中国红':'#D6434B','玫瑰粉':'#D66D96','深海青':'#168E9A','石墨黑':'#444B59'};\nfunction renderAppearance(){const root=node('div');root.appendChild(heading('外观与主题','settings'));root.appendChild(section('选择颜色'));const grid=node('div','theme-grid');Object.entries(themeColors).forEach(([name,color])=>{const b=node('button','theme-button'+(theme.theme===name&&!theme.custom_color?' active':''));const sw=node('span','swatch');sw.style.background=color;child(b,sw,node('span','',name));b.onclick=()=>bridge('theme',name);grid.appendChild(b)});root.appendChild(grid);root.appendChild(section('显示模式'));const modes=node('div','pills');['跟随系统','浅色模式','深色模式'].forEach(name=>modes.appendChild(btn(name,'btn'+(theme.mode===name?' active':''),()=>bridge('mode',name))));root.appendChild(modes);root.appendChild(section('自定义主题颜色'));const input=node('input','field');input.placeholder='#RRGGBB';input.value=theme.custom_color||'';input.maxLength=7;root.appendChild(input);root.appendChild(btn('应用主题色','btn emphasis full',()=>bridge('color',input.value.trim())));root.appendChild(node('p','note','主题设置存储在本机，在线更新不会覆盖。'));return root}\nfunction renderTools(){const root=node('div');root.appendChild(heading('工具库','settings'));const search=node('input','field');search.placeholder='筛选工具名称';root.appendChild(search);const list=node('div','stack');root.appendChild(list);const paint=()=>{list.replaceChildren();tools.filter(x=>(x[0]+' '+x[1]).toLowerCase().includes(search.value.trim().toLowerCase())).slice(0,100).forEach(x=>list.appendChild(setting(x[0],x[1],()=>{})))};search.oninput=paint;paint();root.appendChild(btn('登记新快捷指令','btn emphasis full',()=>bridge('add_shortcut','')));return root}\nfunction renderAdvanced(){const root=node('div');root.appendChild(heading('高级与故障排查','settings'));const list=node('div','stack');[\n['继续暂停任务','resume'],['核验待处理任务','review'],['复杂任务逐步执行','stepwise'],['测试 DeepSeek 连接','ai_test'],['快捷指令回传自测','hub_echo'],['测试创建备忘录','notes_test'],['测试创建日程','calendar_test'],['清除当前任务状态','clear_state']].forEach(([label,action])=>list.appendChild(setting(label,'仅在用户点击时执行',()=>bridge(action,''))));root.appendChild(list);return root}\nfunction applyPalette(p){const map={accent:'--accent',background:'--bg',surface:'--surface',raised:'--raised',text:'--text',muted:'--muted',border:'--border',light:'--light',negative:'--danger'};Object.entries(map).forEach(([k,name])=>{if(p[k])document.documentElement.style.setProperty(name,p[k])})}\nwindow.PYAgentReceive=function(m){if(!m||typeof m!=='object')return;if(m.type==='theme'){theme=m.appearance||theme;applyPalette(m.palette||{});render();notify('主题已保存')}else if(m.type==='search'){archives=m.archives||[];render();notify('已更新搜索结果')}else if(m.type==='detail'){currentArchive=m.archive;page='detail';render()}else if(m.type==='result'){preview=m.result||{};jump('result')}else if(m.type==='message'){notify(m.message||'操作完成')}};\nfunction render(){const content=$('content');content.replaceChildren();$('version').textContent='V'+D.version+'  ·  DeepSeek Flash';const views={home:renderHome,input:renderInput,result:renderResult,archive:renderArchive,detail:renderDetail,settings:renderSettings,appearance:renderAppearance,tools:renderTools,advanced:renderAdvanced};content.appendChild((views[page]||renderHome)());const nav=$('nav');nav.replaceChildren();[['home','首页'],['result','结果'],['archive','档案'],['settings','设置']].forEach(([p,label])=>nav.appendChild(btn(label, 'nav-item'+(page===p||(p==='settings'&&['appearance','tools','advanced'].includes(page))||(p==='archive'&&page==='detail')?' active':''),()=>jump(p))));if(D.modal){$('close').textContent='完成'}}\n$('close').onclick=()=>bridge('close','');applyPalette(D.palette||{});render();bridge('ready','');\n})();\n</script></body></html>"

def _webui_safe_json(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)
            .replace('<', r'\u003c').replace('>', r'\u003e')
            .replace('&', r'\u0026').replace('\u2028', r'\u2028')
            .replace('\u2029', r'\u2029'))

def _webui_document(boot):
    return WEBUI_HTML.replace('/*__BOOTSTRAP__*/',
                              'window.PYAGENT_BOOT='+_webui_safe_json(boot)+';')

# -*- coding: utf-8 -*-
"""Runtime bindings for the local offline HTML view (bundled in core)."""
from urllib.parse import parse_qs

_WEBUI_NATIVE_SHOW = _card_ui_show
_WEBUI_NATIVE_RESULT = _result_ui_show
_WEBUI_ACTIONS = frozenset((
    'voice', 'input', 'clipboard', 'update', 'ai_settings', 'voice_privacy',
    'module_setup', 'resume', 'review', 'add_shortcut', 'stepwise', 'ai_test',
    'hub_echo', 'notes_test', 'calendar_test', 'clear_state',
    'contact_import', 'check_update_status', 'history_share'))


def _webui_boot(page='home', state=None, modal=False, nonce=''):
    current = state if isinstance(state, dict) else _card_task_snapshot()
    appearance = _card_appearance_load()
    result = _result_card_model(current)
    try:
        archive = _history_search('', 45)
    except (OSError, ValueError):
        archive = []
    try:
        tools = _card_tool_rows('')[:120]
    except Exception:
        tools = []
    return {'version': VERSION.split('-')[0], 'page': page,
            'modal': bool(modal), 'nonce': nonce,
            'appearance': appearance, 'palette': _card_palette(appearance),
            'status': current.get('status', ''),
            'goal': str(current.get('goal') or '')[:210],
            'result': result, 'archives': archive, 'tools': tools}


def _webui_show(page='home', state=None, modal=False):
    """Create the only local WebView; return (action, text) like native UI."""
    import ui
    from urllib.parse import urlsplit
    if not hasattr(ui, 'WebView'):
        raise RuntimeError('当前 Pythonista 缺少 WebView')
    nonce = uuid.uuid4().hex
    boot = _webui_boot(page, state, modal, nonce)
    document = _webui_document(boot)
    width, height = ui.get_screen_size()
    holder = ui.View(frame=(0, 0, width, height))
    holder.name = 'PYVoiceAgent · 本地 WebView'
    holder.background_color = boot['palette']['background']
    holder.flex = 'WH'
    holder.result = ('exit', '')
    holder.ready = False
    holder.failed = False
    web = ui.WebView(frame=holder.bounds)
    web.flex = 'WH'
    web.background_color = holder.background_color
    holder.add_subview(web)

    def response(data):
        payload = 'window.PYAgentReceive('+_webui_safe_json(data)+');'
        def deliver():
            try:
                if holder.on_screen:
                    web.eval_js(payload)
            except Exception as exc:
                print('WebView 页面更新失败：'+str(exc)[:120])
        ui.delay(deliver, 0.05)

    class Bridge:
        def webview_should_start_load(self, view, url, nav_type):
            if url in ('about:blank', 'about:srcdoc') or url.startswith('data:text/html'):
                return True
            if len(url) > 14000:
                return False
            try:
                parsed = urlsplit(url)
                if parsed.scheme != 'pyagent-ui' or parsed.netloc != 'dispatch':
                    return False  # No HTTP/HTTPS navigation from local content.
                args = parse_qs(parsed.query, keep_blank_values=True)
                if len(args) > 3 or any(len(v) != 1 for v in args.values()):
                    return False
                if args.get('nonce') != [nonce]:
                    return False
                action = args.get('action', [''])[0]
                value = args.get('payload', [''])[0]
                if len(value) > 10000 or holder.failed:
                    return False
                if action == 'ready':
                    holder.ready = True
                elif action == 'close':
                    holder.result = ('exit', '')
                    ui.delay(holder.close, 0.01)
                elif action == 'search':
                    response({'type': 'search', 'archives': _history_search(value[:100], 75)})
                elif action == 'detail':
                    record = _history_read(value)
                    response({'type': 'detail', 'archive': {
                        'key': value, 'title': str(record.get('goal') or '')[:180],
                        'created': str(record.get('created') or '')[:50],
                        'text': _history_md(record)[:18000]}})
                elif action in ('theme', 'mode', 'color'):
                    appearance = _card_appearance_load()
                    if action == 'theme' and value in CARD_THEMES:
                        appearance['theme'] = value
                        appearance['custom_color'] = ''
                    elif action == 'mode' and value in DISPLAY_MODES:
                        appearance['mode'] = value
                    elif action == 'color' and _card_hex(value):
                        appearance['custom_color'] = _card_hex(value)
                    else:
                        response({'type': 'message', 'message': '主题参数不合法，未更改设置'})
                        return False
                    appearance = _card_appearance_save(appearance)
                    response({'type': 'theme', 'appearance': appearance,
                              'palette': _card_palette(appearance)})
                elif action == 'copy':
                    import clipboard
                    clipboard.set(value[:10000])
                    response({'type': 'message', 'message': '内容已复制到剪贴板'})
                elif action == 'history_copy':
                    import clipboard
                    clipboard.set(_history_markdown_for_key(value))
                    response({'type': 'message', 'message': '档案全文已复制'})
                elif action in _WEBUI_ACTIONS:
                    if action == 'input' and (not value.strip() or len(value) > 2000):
                        response({'type': 'message', 'message': '任务应为1至2000字'})
                        return False
                    holder.result = (action, value)
                    ui.delay(holder.close, 0.01)
                else:
                    return False
            except Exception as exc:
                response({'type': 'message', 'message': '操作未完成：'+str(exc)[:120]})
            return False

        def webview_did_fail_load(self, view, error_code, error_msg):
            # A cancelled custom-scheme navigation can generate an iOS error;
            # only a page-load failure before the ready message is fatal.
            if not holder.ready and str(error_code) not in ('-999', '-1002'):
                holder.failed = True
                ui.delay(holder.close, 0.02)

    web.delegate = Bridge()
    holder.present('full_screen', hide_title_bar=True)
    web.load_html(document)

    def page_watchdog():
        if not holder.ready and holder.on_screen:
            holder.failed = True
            holder.close()
    ui.delay(page_watchdog, 6.0)
    holder.wait_modal()
    if holder.failed:
        raise RuntimeError('WebView 页面初始化失败，改用原生卡片界面')
    return holder.result


def _card_ui_show():
    try:
        return _webui_show('home')
    except Exception as exc:
        print('本地 WebView 暂不可用：'+str(exc)[:160])
        return _WEBUI_NATIVE_SHOW()


def _result_ui_show(state):
    try:
        _webui_show('result', state, modal=True)
        return _result_card_model(state)
    except Exception as exc:
        print('WebView 结果页暂不可用：'+str(exc)[:160])
        return _WEBUI_NATIVE_RESULT(state)
