# -*- coding: utf-8 -*-
"""UI add-on for V2.2.5; HTML runs entirely inside the local Pythonista WebView."""
_REG_CSS = r"""
#agent-exit{border:1px solid var(--border);border-radius:12px;background:var(--raised);padding:9px 11px;font-size:12px;white-space:nowrap;min-height:38px}
#reg-form .field{margin:7px 0 10px}
#reg-form label{display:block;font-size:12px;color:var(--muted);margin-top:12px}
#reg-form select{width:100%;background:var(--raised);border:1px solid var(--border);border-radius:11px;color:var(--text);padding:12px;font-size:14px}
.reg-item{background:var(--raised);padding:12px;margin-top:10px;border-radius:12px}
.reg-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.reg-actions{display:flex;gap:5px;flex-wrap:wrap;margin-top:9px}
.reg-actions button{padding:8px 9px;min-height:38px;border-radius:9px;background:var(--surface);font-size:12px}
.reg-check{display:flex;align-items:center;gap:8px;color:var(--text);font-size:13px;margin:12px 0}
.reg-check input{width:20px;height:20px;accent-color:var(--accent)}
@media(max-width:410px){.topline .status{display:none}#agent-exit{padding:8px 10px}}
"""
_REG_SECTION = r"""
<div class="section-title">我的快捷指令工具库</div>
<div class="card" id="reg-form">
<div class="title">登记 iPhone 本地快捷指令</div>
<div class="sub">先在苹果“快捷指令”App 中建立或导入指令，再登记准确名称。助手只会运行已启用的白名单指令。</div>
<label for="reg-id">工具 ID（英文小写，如 open_work）</label>
<input class="field" id="reg-id" maxlength="32" placeholder="open_work">
<label for="reg-name">苹果快捷指令名称（必须完全相同）</label>
<input class="field" id="reg-name" maxlength="70" placeholder="打开工作台">
<label for="reg-desc">功能描述（帮助 AI 理解用途）</label>
<input class="field" id="reg-desc" maxlength="160" placeholder="打开我常用的工作页面">
<label for="reg-aliases">自然语言触发说法，多个用逗号隔开</label>
<textarea class="entry" id="reg-aliases" style="width:100%;min-height:64px" placeholder="打开工作台，启动工作台"></textarea>
<label for="reg-mode">执行方式</label>
<select id="reg-mode"><option value="launch">直接运行（一般快捷指令，无回调）</option><option value="bridge">回传模式（需你自己配置回传 token）</option></select>
<label for="reg-input">传入快捷指令的文字</label>
<select id="reg-input"><option value="none">不传参</option><option value="suffix">触发语句后面的文字</option><option value="full">整条原始指令</option></select>
<label class="reg-check"><input type="checkbox" id="reg-confirm" checked>每次启动前确认（建议保持）</label>
<label class="reg-check"><input type="checkbox" id="reg-enabled" checked>启用该工具</label>
<div class="quick"><button class="action" id="reg-save">保存工具</button><button class="action secondary" id="reg-clear">新建／清空</button><button class="action secondary" id="reg-refresh">刷新工具库</button></div>
<div class="sub">普通模式只确认向 iOS 发出运行请求；不能保证执行成功。涉及支付、发送或删除的快捷指令建议开启确认，并由用户在系统界面完成最终核验。</div>
<div id="reg-list"></div>
</div>
"""
_REG_JS = r"""
(function(){
'use strict';
function el(id){return document.getElementById(id)}
var boot=window.PYCHAT_BOOT||{}, items=[];
function call(a,p){if(p===undefined)p='';window.location.href='pyagent-chat://dispatch?nonce='+encodeURIComponent(boot.nonce)+'&action='+encodeURIComponent(a)+'&payload='+encodeURIComponent(String(p))}
function clear(){['id','name','desc','aliases'].forEach(function(n){el('reg-'+n).value=''});el('reg-mode').value='launch';el('reg-input').value='none';el('reg-confirm').checked=true;el('reg-enabled').checked=true;el('reg-id').readOnly=false}
function edit(x){el('reg-id').value=x.id;el('reg-id').readOnly=true;el('reg-name').value=x.name;el('reg-desc').value=x.description;el('reg-aliases').value=(x.aliases||[]).join('，');el('reg-mode').value=x.mode;el('reg-input').value=x.input_mode;el('reg-confirm').checked=x.confirm;el('reg-enabled').checked=x.enabled;document.getElementById('settingsview').scrollTop=0}
function build(){var list=el('reg-list');list.replaceChildren();if(!items.length){list.textContent='尚未登记快捷指令';return}
items.forEach(function(x){var card=document.createElement('div');card.className='reg-item';var title=document.createElement('div');title.className='reg-head';title.textContent=x.name+' · '+x.id;card.appendChild(title);
var description=document.createElement('div');description.className='sub';description.textContent=x.description+'｜'+(x.enabled?'启用':'停用')+'｜'+(x.mode==='bridge'?'需要回传':'直接启动')+'\n触发：'+(x.aliases||[]).join('、');card.appendChild(description);
var row=document.createElement('div');row.className='reg-actions';
function add(label,fn){var b=document.createElement('button');b.textContent=label;b.onclick=fn;row.appendChild(b)}
add('编辑',function(){edit(x)});
add(x.enabled?'停用':'启用',function(){call('reg_toggle',JSON.stringify({id:x.id,enabled:!x.enabled}))});
add('删除',function(){if(window.confirm('确认删除工具「'+x.name+'」的本地登记吗？不会删除苹果快捷指令本身。'))call('reg_delete',JSON.stringify({id:x.id,confirm:true}))});
card.appendChild(row);list.appendChild(card)})}
el('reg-save').onclick=function(){var data={id:el('reg-id').value.trim(),name:el('reg-name').value.trim(),description:el('reg-desc').value.trim(),aliases:el('reg-aliases').value.split(/[，,\n]/).map(function(v){return v.trim()}).filter(Boolean),mode:el('reg-mode').value,input_mode:el('reg-input').value,confirm:el('reg-confirm').checked,enabled:el('reg-enabled').checked};call('reg_save',JSON.stringify(data))};
el('reg-clear').onclick=clear;el('reg-refresh').onclick=function(){call('reg_list','')};
document.querySelector('[data-tab="settings"]').addEventListener('click',function(){setTimeout(function(){call('reg_list','')},80)});
var prior=window.PYChatReceive;
window.PYChatReceive=function(data){if(data&&data.type==='reg_list'){items=data.items||[];build();return}return prior(data)};
el('agent-exit').onclick=function(){if(window.confirm('退出 PYVoiceAgent 助手界面并返回 Pythonista？正在运行的系统快捷指令不会因此撤销。'))call('exit','')};
var oldAdd=document.querySelector('[data-legacy="add_shortcut"]');if(oldAdd)oldAdd.onclick=function(){document.getElementById('reg-form').scrollIntoView({behavior:'smooth',block:'start'})};
})();
"""
CHAT_HTML=CHAT_HTML.replace('</style>','\n'+_REG_CSS+'</style>')
CHAT_HTML=CHAT_HTML.replace('<div id="status" class="status">准备就绪</div></div>',
                             '<div id="status" class="status">准备就绪</div><button id="agent-exit" aria-label="退出助手">退出</button></div>')
CHAT_HTML=CHAT_HTML.replace('<div class="section-title">原有工具与系统设置</div>',
                             _REG_SECTION+'<div class="section-title">原有工具与系统设置</div>')
CHAT_HTML=CHAT_HTML.replace('</script></body></html>',
                             '</script><script>'+_REG_JS+'</script></body></html>')
_REG_HANDLE=_ChatShell._handle_action
def _reg_chat_action(self,action,text):
    return _REG_HANDLE(self,action,text)
_ChatShell._handle_action=_reg_chat_action
_REG_PREV_SHOW=_ChatShell.show
def _reg_show(self):
    return _REG_PREV_SHOW(self)
_ChatShell.show=_reg_show
