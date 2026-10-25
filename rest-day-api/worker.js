/**
 * China rest-day checker for iOS Shortcuts.
 * Official schedule data from NateScarlet/holiday-cn (government notices).
 * Automatic Cloudflare Cron refresh + KV persistence + conservative fail-closed behavior.
 *
 * 1 = holiday/weekend, 0 = working day including makeup weekends.
 * UNKNOWN (HTTP 422) = no verified complete holiday calendar.
 */
const DATA_HOSTS = [
  'https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/',
  'https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/'
];
const MIN_YEAR = 2026;
const BEIJING_ZONE = 'Asia/Shanghai';
const SOURCE_2026 = 'https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm';

// Offline bootstrap: 2026 already checked against 国办发明电〔2025〕7号.
// Not used for any later year: unpublished schedules must fail closed.
const BOOTSTRAP_2026 = {
  year: 2026, papers: [SOURCE_2026], from: 'verified-bundled-2026',
  days: [
    ...makeDays(2026,1,1,3,'元旦',true),
    {date:'2026-01-04',name:'元旦',isOffDay:false},
    {date:'2026-02-14',name:'春节',isOffDay:false},
    ...makeDays(2026,2,15,23,'春节',true),
    {date:'2026-02-28',name:'春节',isOffDay:false},
    ...makeDays(2026,4,4,6,'清明节',true),
    ...makeDays(2026,5,1,5,'劳动节',true),
    {date:'2026-05-09',name:'劳动节',isOffDay:false},
    ...makeDays(2026,6,19,21,'端午节',true),
    {date:'2026-09-20',name:'国庆节',isOffDay:false},
    ...makeDays(2026,9,25,27,'中秋节',true),
    ...makeDays(2026,10,1,7,'国庆节',true),
    {date:'2026-10-10',name:'国庆节',isOffDay:false}
  ]
};

function makeDays(year, month, start, end, name, isOffDay) {
  return Array.from({length:end-start+1}, (_,i) => ({
    date:[year,String(month).padStart(2,'0'),String(i+start).padStart(2,'0')].join('-'),
    name,isOffDay
  }));
}

function todayInChina(now = new Date()) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone:BEIJING_ZONE, year:'numeric',month:'2-digit',day:'2-digit'
    }).formatToParts(now).filter(x=>x.type!=='literal').map(x=>[x.type,x.value])
  );
  return parts.year+'-'+parts.month+'-'+parts.day;
}

function validDate(date) {
  if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  const d = new Date(date+'T00:00:00Z');
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0,10)===date;
}

function officialPaper(value) {
  try {
    const u=new URL(value);
    return u.protocol==='https:' && (u.hostname==='gov.cn' || u.hostname.endsWith('.gov.cn'));
  } catch { return false; }
}

function completeCalendar(data, year) {
  if (!data || data.year!==year || !Array.isArray(data.papers) || !Array.isArray(data.days)) return false;
  if (!data.papers.length || !data.papers.every(officialPaper)) return false;
  if (data.days.length<25 || data.days.length>400) return false;
  const unique = new Set();
  let off=0, makeup=0;
  for (const d of data.days) {
    if (!d || !validDate(d.date) || typeof d.name!=='string' ||
        !d.name.trim() || d.name.length>60 || typeof d.isOffDay!=='boolean') return false;
    const itemYear=Number(d.date.slice(0,4));
    if (Math.abs(itemYear-year)>1 || unique.has(d.date)) return false;
    unique.add(d.date);
    if(d.isOffDay) off++; else makeup++;
  }
  // Avoid treating a just-created, empty annual placeholder as a real calendar.
  if (off<20 || makeup<1) return false;
  // Government notices must describe at least New Year's Day, Labour Day and National Day.
  const required=[year+'-01-01',year+'-05-01',year+'-10-01'];
  return required.every(date=>data.days.some(d=>d.date===date && d.isOffDay));
}

async function fetchOfficialCalendar(year) {
  for (const base of DATA_HOSTS) {
    try {
      const res=await fetch(base+year+'.json', {
        headers:{'Accept':'application/json'},
        signal:AbortSignal.timeout(6500),
        cf:{cacheTtl:1800,cacheEverything:false}
      });
      if(!res.ok) continue;
      const data=await res.json();
      if(!completeCalendar(data,year)) continue;
      // Copy only validated fields into KV (ignore arbitrary upstream metadata).
      return {
        year, papers:data.papers,
        days:data.days.map(x=>({date:x.date,name:x.name,isOffDay:x.isOffDay})),
        from:'holiday-cn'
      };
    } catch(e) {
      console.warn('Calendar download failed for '+year+': '+String(e));
    }
  }
  return null;
}

async function safeGet(env, key) {
  if (!env.CN_HOLIDAYS) return null;
  try {return await env.CN_HOLIDAYS.get(key,'json');}
  catch(e) {console.warn('KV get failed: '+String(e)); return null;}
}
async function safePut(env,key,value) {
  if (!env.CN_HOLIDAYS) throw new Error('CN_HOLIDAYS is not bound');
  return env.CN_HOLIDAYS.put(key,JSON.stringify(value));
}

async function syncYear(year,env,now) {
  const startedAt=now.toISOString();
  try {
    const fresh=await fetchOfficialCalendar(year);
    if(!fresh) throw new Error('NO_VERIFIED_OFFICIAL_CALENDAR');
    const old=await safeGet(env,'calendar:'+year);
    if (!completeCalendar(old,year) ||
        JSON.stringify(old.days)!==JSON.stringify(fresh.days) ||
        JSON.stringify(old.papers)!==JSON.stringify(fresh.papers)) {
      await safePut(env,'calendar:'+year,{...fresh,verifiedAt:startedAt});
    }
    await safePut(env,'sync:'+year,{
      year, lastChecked:startedAt,ok:true,
      source:fresh.papers[0],dayEntries:fresh.days.length
    });
    return true;
  } catch(e) {
    console.error('Holiday annual update failed year='+year+': '+String(e));
    try {await safePut(env,'sync:'+year,{
      year,lastChecked:startedAt,ok:false,error:String(e)
    });}catch{}
    return false;
  }
}

async function getCalendar(year,env,now) {
  const cached=await safeGet(env,'calendar:'+year);
  if (completeCalendar(cached,year)) return cached;
  if (year===2026) return BOOTSTRAP_2026;
  const current=Number(todayInChina(now).slice(0,4));
  if (year<MIN_YEAR || year<current-1 || year>current+1) return null;
  // Recovery if scheduled sync has not yet succeeded, e.g. year-end outage.
  const fresh=await fetchOfficialCalendar(year);
  if(!fresh) return null;
  try {await safePut(env,'calendar:'+year,{...fresh,verifiedAt:now.toISOString()});}
  catch(e) {console.warn('KV put failed (live recovery): '+String(e));}
  return fresh;
}

function classify(date,primary,adjacent) {
  const entry=adjacent?.days?.find(x=>x.date===date) ||
              primary.days.find(x=>x.date===date);
  const day=new Date(date+'T00:00:00Z').getUTCDay();
  const weekend=(day===0 || day===6);
  const isRestDay=entry ? entry.isOffDay : weekend;
  const type=entry ? (entry.isOffDay ? 'holiday' : 'makeup_workday') :
    (weekend ? 'weekend' : 'weekday');
  const reason=entry ? (entry.isOffDay ? entry.name+'放假' : '调休补班') :
    (weekend ? '周末休息' : '普通工作日');
  const usedSource=(adjacent?.days?.some(x=>x.date===date)?adjacent:primary);
  return {
    date,timezone:BEIJING_ZONE,known:true,
    isRestDay,isWorkday:!isRestDay,shouldRun:!isRestDay,
    type,reason,source:usedSource.papers[0],
    calendarYear:usedSource.year,
    calendarUpdatedAt:usedSource.verifiedAt || null
  };
}

function unknown(date) {
  return {
    date,timezone:BEIJING_ZONE,known:false,
    isRestDay:null,isWorkday:null,shouldRun:false,
    type:'unknown',reason:'没有完整且可核验的国务院年度节假日安排；为安全起见不执行任务',
    source:null
  };
}

function respond(data,status,plain,head=false) {
  return new Response(head?null:(plain ?
    (data.known ? (data.isRestDay?'1':'0') : 'UNKNOWN') : JSON.stringify(data)),{
      status,headers:{
        'Content-Type':plain?'text/plain; charset=utf-8':'application/json; charset=utf-8',
        'Cache-Control':'no-store, max-age=0','Access-Control-Allow-Origin':'*',
        'X-Content-Type-Options':'nosniff'
      }
    });
}

export default {
  async fetch(request,env) {
    const head=request.method==='HEAD';
    if (request.method!=='GET' && !head)
      return respond({error:'METHOD_NOT_ALLOWED',known:false},405,false);
    const url=new URL(request.url);
    if (url.pathname!=='/' && url.pathname!=='/check' && url.pathname!=='/status')
      return respond({error:'NOT_FOUND',known:false},404,false,head);
    const now=new Date(),date=url.searchParams.get('date')??todayInChina(now);
    if (url.pathname==='/status') {
      const yearArg=url.searchParams.get('year');
      const year=yearArg===null ? Number(todayInChina(now).slice(0,4))+1 : Number(yearArg);
      if (!Number.isInteger(year)||year<MIN_YEAR||year>2100)
        return respond({error:'INVALID_YEAR'},400,false,head);
      const [calendar,sync]=await Promise.all([
        safeGet(env,'calendar:'+year),safeGet(env,'sync:'+year)
      ]);
      return respond({
        year,calendarReady:completeCalendar(calendar,year) || year===2026,
        dataSource:calendar?.papers?.[0] || (year===2026?SOURCE_2026:null),
        lastVerifiedAt:calendar?.verifiedAt || null,
        sync:sync||null,runAt:'01:05 UTC (09:05 Beijing) daily, including December 31'
      },200,false,head);
    }
    const format=url.searchParams.get('format')||'json';
    if(!['json','plain','text'].includes(format))
      return respond({error:'INVALID_FORMAT',known:false},400,false,head);
    const plain=format!=='json';
    if(!validDate(date))
      return respond({date,known:false,isRestDay:null,shouldRun:false,
        error:'INVALID_DATE',reason:'请使用 YYYY-MM-DD 日期'},400,plain,head);
    const year=Number(date.slice(0,4));
    if(year<MIN_YEAR||year>2100) return respond(unknown(date),422,plain,head);
    const primary=await getCalendar(year,env,now);
    if (!primary) return respond(unknown(date),422,plain,head);
    // The following year's notice can modify dates in late December.
    const adjacent=date.slice(5,7)==='12' ?
      await getCalendar(year+1,env,now):null;
    const result=classify(date,primary,adjacent);
    return respond(result,200,plain,head);
  },
  async scheduled(controller,env) {
    const now=new Date(controller.scheduledTime || Date.now());
    const local=todayInChina(now);
    const year=Number(local.slice(0,4));
    const month=Number(local.slice(5,7));
    // Every day checks current year; Sep-Dec also checks upcoming year.
    // This includes Dec 31. Jan retries support late or failed announcements.
    const years=month>=9 ? [year,year+1] : [year];
    for (const y of years) {
      if (y>=MIN_YEAR) await syncYear(y,env,now);
    }
  }
};
