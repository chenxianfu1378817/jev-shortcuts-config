const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'../webui/index_v210.html'),'utf8');
const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length,2);
class El {
  constructor(tag){this.tag=tag;this.children=[];this.style={setProperty(name,val){this[name]=val}};this.attributes={};this.hidden=false;this.className='';this.textContent='';this.title='';this.value='';this.events={};}
  appendChild(c){this.children.push(c);return c}
  replaceChildren(...c){this.children=c;return c}
  addEventListener(k,fn){this.events[k]=fn;}
  click(){if(this.onclick)this.onclick();if(this.events.click)this.events.click()}
}
const elems={};for(let id of ['notice','content','version','close','nav'])elems[id]=new El('div');
const document={documentElement:new El('html'),createElement:tag=>new El(tag),getElementById:id=>elems[id]};
const window={PYAGENT_BOOT:{version:'2.1.0',nonce:'test',page:'home',modal:false,goal:'今天的日程',status:'finished',result:{title:'任务处理完成',body:'结果文本',copy:'结果文本',items:[]},archives:[{key:'2026-11/task_123456.json',title:'历史测试',created:'2026-11-11'}],appearance:{theme:'典雅紫',mode:'深色模式',custom_color:''},palette:{accent:'#8A62D8'},tools:[['reminder.list','读取提醒']]},location:{href:''},scrollTo:()=>{}};
const sandbox={window,document,setTimeout:()=>{},console};
vm.runInNewContext(scripts[1][1],sandbox);
assert(elems.content.children.length>0);assert.equal(elems.nav.children.length,4);
function texts(e){return [e.textContent,...e.children.flatMap(texts)].join(' ')}
assert(texts(elems.content).includes('语音执行任务'));
elems.nav.children[2].click();assert(texts(elems.content).includes('历史档案'));assert(texts(elems.content).includes('历史测试'));
elems.nav.children[3].click();assert(texts(elems.content).includes('外观与主题'));
window.PYAgentReceive({type:'theme',appearance:{theme:'活力橙'},palette:{accent:'#F07828'}});
assert.equal(document.documentElement.style['--accent'],'#F07828');
elems.nav.children[1].click();assert(texts(elems.content).includes('结果文本'));
assert(elems.nav.children[1].className.includes('active'));
assert(window.location.href.includes('pyagent-ui://dispatch?nonce=test'));
console.log('JS DOM smoke: home/archive/settings/theme/result/offline bridge passed');