/**
 * Personal Automation API v1
 * Code: GitHub /unified-api; runtime: Cloudflare Workers.
 * No credentials, personal records, or phone actions are stored or executed.
 * CN holidays are checked via a Cloudflare service binding.
 */
const VERSION = "1.0.0";
const ZONE = "Asia/Shanghai";
const ROUTES = Object.freeze([
  { id:"contacts.create_from_text", test:/(?:通讯录|联系人|微信|名片).*(?:录入|新增|保存|添加|姓名|电话|单位)|(?:姓名|电话|单位).*(?:通讯录|保存联系人)/ },
  { id:"contacts.search", test:/(?:查找|搜索|查询|找到).{0,8}(?:通讯录|联系人|电话)/ },
  { id:"calendar.list", test:/(?:查询|查看|看看|有什么|读取|列出).{0,14}(?:日历|日程|行程|会议)|(?:今天|明天|本周).{0,10}(?:日程|日历|会议)/ },
  { id:"calendar.create", test:/(?:创建|新增|添加|安排|记录).{0,18}(?:日历|日程|会议|行程)|(?:开会|会议|预约).{0,25}(?:加入日历|到日历|安排)/ },
  { id:"todo.create", test:/(?:提醒我|提醒事项|待办|记得|别忘了|工作计划)/ },
  { id:"notes.create", test:/(?:备忘录|笔记|记一笔|记录一下|写个便签)/ },
  { id:"maps.open", test:/(?:导航|打开地图|地图上搜索|去往|带我去)/ },
  { id:"clipboard.process", test:/(?:剪贴板|剪切板|复制的内容|刚复制的文本)/ },
  { id:"wechat.scan", test:/(?:微信扫一扫|打开微信扫码|微信扫一下)/ }
]);

function chinaToday() {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: ZONE, year:"numeric", month:"2-digit", day:"2-digit"
    }).formatToParts(new Date())
      .filter(x => x.type !== "literal").map(x => [x.type,x.value])
  );
  return p.year + "-" + p.month + "-" + p.day;
}

function validDate(s) {
  if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s + "T00:00:00.000Z");
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0,10) === s;
}

function respond(body, status=200, type="json", headers={}) {
  const json = type==="json";
  return new Response(json ? JSON.stringify(body) : String(body), {
    status,
    headers:{
      "Content-Type":json?"application/json; charset=utf-8":"text/plain; charset=utf-8",
      "Cache-Control":"no-store",
      "X-Content-Type-Options":"nosniff",
      "X-Personal-Api-Version":VERSION,
      ...headers
    }
  });
}

async function readBody(request) {
  const declared = Number(request.headers.get("content-length") || 0);
  if(declared > 4096) throw new Error("BODY_TOO_LARGE");
  const text = await request.text();
  if(text.length > 4096) throw new Error("BODY_TOO_LARGE");
  try {
    const value=JSON.parse(text);
    if(value && typeof value==="object" && !Array.isArray(value)) return value;
  } catch {}
  throw new Error("INVALID_JSON_OBJECT");
}

async function workday(url,env) {
  // Fail closed: lack of an authoritative answer never becomes "1".
  const date=url.searchParams.get("date") || chinaToday();
  const json=url.searchParams.get("format")==="json";
  if(!validDate(date)) return json?
    respond({ok:false,known:false,date,error:"INVALID_DATE",shouldRun:false},400):
    respond("",200,"text");
  try {
    if(!env.WORKDAY_SERVICE) throw new Error("SERVICE_UNAVAILABLE");
    const upstream="https://cn-restday-shortcuts.cxfoffice.workers.dev/?format=json&date="+encodeURIComponent(date);
    const response=await env.WORKDAY_SERVICE.fetch(new Request(upstream,{method:"GET"}));
    if(!response.ok) throw new Error("UPSTREAM_UNAVAILABLE");
    const result=await response.json();
    if(result.known!==true || typeof result.isWorkday!=="boolean") throw new Error("UNVERIFIED");
    const shouldRun=result.isWorkday === true;
    if(json) return respond({
      ok:true,known:true,date,shouldRun,isWorkday:shouldRun,
      isRestDay:!shouldRun,reason:result.reason || null,
      calendarYear:result.calendarYear || null,source:result.source || null
    });
    return respond(shouldRun?"1":"",200,"text");
  } catch(e) {
    if(json) return respond({ok:false,known:false,date,shouldRun:false,
      error:"CALENDAR_UNAVAILABLE"});
    return respond("",200,"text");
  }
}

function taskRoute(phrase) {
  const input=phrase.trim();
  const match=ROUTES.find(item=>item.test.test(input));
  return {
    ok:true,
    route:match ? match.id : "manual.review",
    recognized:Boolean(match),
    engine:"local-rules-v1",
    requiresReview:!match || match.id==="contacts.create_from_text",
    executed:false,
    input
  };
}

function numericCompare(value,threshold,operator) {
  if(typeof value!=="number" || !Number.isFinite(value) ||
     typeof threshold!=="number" || !Number.isFinite(threshold))
    throw new Error("INVALID_NUMBER");
  const ops = {
    gt:(a,b)=>a>b, gte:(a,b)=>a>=b,
    lt:(a,b)=>a<b, lte:(a,b)=>a<=b,
    eq:(a,b)=>a===b, ne:(a,b)=>a!==b
  };
  if(!Object.hasOwn(ops,operator)) throw new Error("INVALID_OPERATOR");
  return ops[operator](value,threshold);
}

function help() {
  return {
    name:"Personal Automation API",version:VERSION,
    timezone:ZONE,
    prefix:"/api",
    usage:"GET /api?task=workday (1 on verified workdays, blank otherwise)",
    actions:{
      workday:"GET. optional date=YYYY-MM-DD, format=json for diagnostics",
      date:"GET. Beijing-local YYYY-MM-DD",
      health:"GET. Public service health (does not imply upstream is healthy)",
      config:"GET. Read action metadata",
      route:"POST JSON {text:string}. Return local route only; no phone action",
      compare:"POST JSON {value:number,threshold:number,operator:gt|gte|lt|lte|eq|ne}. Return 1/blank"
    },
    availableRouteIds:ROUTES.map(x=>x.id),
    safeguards:["read-only service","no AI inference","no phone writes","workday unknown => blank"]
  };
}

export default {
  async fetch(request,env) {
    const url=new URL(request.url);
    const parts=url.pathname.split("/").filter(Boolean);
    let task;
    if(url.pathname==="/" || url.pathname==="/api") task=url.searchParams.get("task") || "config";
    else if(parts.length===2 && parts[0]==="api") task=parts[1];
    else return respond({ok:false,error:"NOT_FOUND"},404);
    if(!["workday","date","health","config","route","compare"].includes(task))
      return respond({ok:false,error:"UNKNOWN_TASK",available:help().actions},404);
    if(request.method==="OPTIONS") return new Response(null,{status:204,headers:{"Allow":task==="route"||task==="compare"?"POST, OPTIONS":"GET, HEAD, OPTIONS"}});
    const postOnly=task==="route"||task==="compare";
    if(postOnly ? request.method!=="POST":!(request.method==="GET"||request.method==="HEAD"))
      return respond({ok:false,error:"METHOD_NOT_ALLOWED"},405);
    if(task==="workday") return workday(url,env);
    if(task==="date") return respond(chinaToday(),200,"text");
    if(task==="health") return respond({ok:true,version:VERSION,timezone:ZONE,checkedAt:new Date().toISOString()});
    if(task==="config") return respond(help());
    let payload;
    try{payload=await readBody(request)}
    catch(e){return respond({ok:false,error:e.message},400)}
    if(task==="route") {
      if(typeof payload.text!=="string" || !payload.text.trim() || payload.text.length>300)
        return respond({ok:false,error:"TEXT_REQUIRED_MAX_300_CHARS"},400);
      const decision=taskRoute(payload.text);
      return url.searchParams.get("format")==="plain" ?
        respond(decision.recognized?decision.route:"",200,"text"):
        respond(decision);
    }
    if(task==="compare") {
      try {
        const matched=numericCompare(payload.value,payload.threshold,payload.operator);
        return url.searchParams.get("format")==="json" ?
          respond({ok:true,matched,shouldRun:matched}):
          respond(matched?"1":"",200,"text");
      }catch(e){return respond({ok:false,error:e.message},400)}
    }
    return respond({ok:false,error:"UNHANDLED"},500);
  }
};
