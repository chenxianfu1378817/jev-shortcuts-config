/**
 * CN rest-day API for iOS Shortcuts.
 * Data: 国务院办公厅 国办发明电〔2025〕7号（2026年放假调休安排）
 * Last verified: 2026-10-25
 * Timezone for date omitted: Asia/Shanghai
 */

const SOURCE_2026 = 'https://www.beijing.gov.cn/cs/gncs/zcwj/202603/t20260327_4568275.html';
const YEARS = {
  2026: {
    source: SOURCE_2026,
    holidays: [
      ['2026-01-01', '2026-01-03', '元旦'],
      ['2026-02-15', '2026-02-23', '春节'],
      ['2026-04-04', '2026-04-06', '清明节'],
      ['2026-05-01', '2026-05-05', '劳动节'],
      ['2026-06-19', '2026-06-21', '端午节'],
      ['2026-09-25', '2026-09-27', '中秋节'],
      ['2026-10-01', '2026-10-07', '国庆节']
    ],
    workdays: [
      '2026-01-04', '2026-02-14', '2026-02-28',
      '2026-05-09', '2026-09-20', '2026-10-10'
    ]
  }
};

function todayInChina(now = new Date()) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(now).filter(x => x.type !== 'literal').map(x => [x.type, x.value])
  );
  return p.year + '-' + p.month + '-' + p.day;
}

function validDate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s + 'T00:00:00Z');
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
}

function check(date) {
  const year = Number(date.slice(0, 4));
  const data = YEARS[year];
  if (!data) {
    return {
      date, timezone: 'Asia/Shanghai', known: false,
      isRestDay: null, isWorkday: null, shouldRun: false,
      type: 'unknown', reason: '该年度官方调休安排尚未录入；为安全起见请勿执行任务',
      source: null
    };
  }

  const specialWork = data.workdays.includes(date);
  const holiday = data.holidays.find(item => date >= item[0] && date <= item[1]);
  const day = new Date(date + 'T00:00:00Z').getUTCDay();
  const weekend = day === 0 || day === 6;
  // 补班优先于普通周末，节假日优先于普通工作日。
  const isRestDay = specialWork ? false : Boolean(holiday || weekend);
  const type = specialWork ? 'makeup_workday' :
    holiday ? 'holiday' : weekend ? 'weekend' : 'weekday';
  const reason = specialWork ? '调休补班' :
    holiday ? holiday[2] + '放假' : weekend ? '周末休息' : '普通工作日';
  return {
    date, timezone: 'Asia/Shanghai', known: true,
    isRestDay, isWorkday: !isRestDay, shouldRun: !isRestDay,
    type, reason, source: data.source
  };
}

function response(data, status, plain) {
  const body = plain ? (data.known ? (data.isRestDay ? '1' : '0') : 'UNKNOWN') :
    JSON.stringify(data);
  return new Response(body, {
    status,
    headers: {
      'Content-Type': plain ? 'text/plain; charset=utf-8' : 'application/json; charset=utf-8',
      'Cache-Control': 'no-store, max-age=0',
      'Access-Control-Allow-Origin': '*',
      'X-Content-Type-Options': 'nosniff'
    }
  });
}

export default {
  async fetch(request) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return response({error: 'METHOD_NOT_ALLOWED', known: false}, 405, false);
    }
    const url = new URL(request.url);
    if (url.pathname !== '/' && url.pathname !== '/check') {
      return response({error: 'NOT_FOUND', known: false}, 404, false);
    }
    const plain = ['plain', 'text'].includes(url.searchParams.get('format'));
    const format = url.searchParams.get('format') || 'json';
    if (!['json', 'plain', 'text'].includes(format)) {
      return response({error: 'INVALID_FORMAT', known: false}, 400, false);
    }
    const date = url.searchParams.has('date') ? url.searchParams.get('date') : todayInChina();
    if (!validDate(date)) {
      return response({
        date, known: false, isRestDay: null, shouldRun: false,
        error: 'INVALID_DATE', reason: '日期须使用 YYYY-MM-DD'
      }, 400, plain);
    }
    const value = check(date);
    return response(value, value.known ? 200 : 422, plain);
  }
};
