let prefs={zone:'local',digits:'fa',week:6,display:'persian'};
export function configureDates(config){prefs=config;}
export function selectedZone(){return prefs.zone==='local'?Intl.DateTimeFormat().resolvedOptions().timeZone:prefs.zone;}
export function locale(){return 'fa-IR-u-ca-'+prefs.display+'-nu-'+(prefs.digits==='fa'?'arabext':'latn');}
const DAY = 86400000;
const fmt = new Intl.DateTimeFormat('en-US-u-ca-persian', {year:'numeric',month:'numeric',day:'numeric',timeZone:'UTC'});
export const fa = n => new Intl.NumberFormat(locale(),{useGrouping:false}).format(n);
export const months = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
export function persian(iso) {
  const values = Object.fromEntries(fmt.formatToParts(new Date(iso+'T12:00:00Z')).map(x=>[x.type,x.value]));
  return {year:+values.year,month:+values.month,day:+values.day};
}
export function todayISO(now=new Date()) {
  const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:selectedZone(),year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now).map(x=>[x.type,x.value]));
  return `${p.year}-${p.month}-${p.day}`;
}
export function addDays(iso, n) {return new Date(new Date(iso+'T12:00:00Z').getTime()+n*DAY).toISOString().slice(0,10);}
export function dateLabel(iso) {if(!iso)return ''; if(prefs.display==='gregory')return new Intl.DateTimeFormat(locale(),{timeZone:'UTC',dateStyle:'medium'}).format(new Date(iso+'T12:00:00Z'));const p=persian(iso);return `${fa(p.day)} ${months[p.month-1]} ${fa(p.year)}`;}
const cache = new Map();
export function monthDates(year, month) {
  const key=`${year}-${month}`;
  if(cache.has(key))return cache.get(key);
  if(year<1390||year>1450||month<1||month>12)throw new Error('تاریخ بیرون از بازهٔ نمونه است.');
  const start=Date.UTC(year+621,2,18,12);const dates=[];
  for(let i=0;i<370;i++) {
    const iso=new Date(start+i*DAY).toISOString().slice(0,10), p=persian(iso);
    if(p.year===year&&p.month===month)dates.push(iso);
    if(dates.length&&p.month!==month)break;
  }
  cache.set(key,dates);return dates;
}
// Resolve wall clock in Tehran using the browser's timezone database, including historical DST.
export function tehranInstant(iso, hour, minute) {
  if(!Number.isInteger(hour)||hour<0||hour>23||!Number.isInteger(minute)||minute<0||minute>59)throw new Error('ساعت بین ۰ تا ۲۳ و دقیقه بین ۰ تا ۵۹ باشد.');
  const target=Date.parse(`${iso}T${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}:00Z`);
  let guess=target;
  const tf=new Intl.DateTimeFormat('en-US',{timeZone:selectedZone(),year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  for(let n=0;n<4;n++) {
    const p=Object.fromEntries(tf.formatToParts(new Date(guess)).map(x=>[x.type,x.value]));
    const actual=Date.parse(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}Z`);
    if(actual===target)return new Date(guess).toISOString();
    guess += target-actual;
  }
  throw new Error('این ساعت در تغییر ساعت رسمی وجود ندارد؛ ساعت دیگری انتخاب کنید.');
}
export function timeLabel(instant) {return instant?new Intl.DateTimeFormat(locale(),{dateStyle:'medium',timeStyle:'short',timeZone:selectedZone()}).format(new Date(instant)):'';}

export class Calendar {
  constructor() {
    this.el=document.getElementById('calendar');this.$=id=>document.getElementById(id);
    this.$('calendarMonth').replaceChildren(...months.map((m,i)=>new Option(m,i+1)));
    this.$('calendarYear').replaceChildren(...Array.from({length:61},(_,i)=>new Option(fa(1390+i),1390+i)));
    this.$('calendarMonth').onchange=()=>this.changeMonth(+this.$('calendarYear').value,+this.$('calendarMonth').value);
    this.$('calendarYear').onchange=this.$('calendarMonth').onchange;
    this.$('previousMonth').onclick=()=>this.shift(-1);this.$('nextMonth').onclick=()=>this.shift(1);
    this.$('calendarToday').onclick=()=>{this.selected=todayISO();this.render(true);};
    this.$('calendarClose').onclick=()=>this.el.close();
    this.el.addEventListener('close',()=>this.opener?.focus());
    this.$('calendarApply').onclick=()=>{
      try{
        const value=this.withTime?tehranInstant(this.selected,Number(this.$('hour').value),Number(this.$('minute').value)):this.selected;
        this.onSelect(value);this.el.close();
      }catch(e){this.$('calendarError').textContent=e.message;this.$('calendarError').hidden=false;}
    };
  }
  open(value, withTime, opener, callback) {
    this.withTime=withTime;this.onSelect=callback;this.opener=opener;
    this.selected=value?(withTime?todayISO(new Date(value)):value):todayISO();
    if(withTime&&value){const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:selectedZone(),hour:'numeric',minute:'numeric',hourCycle:'h23'}).formatToParts(new Date(value)).map(x=>[x.type,x.value]));this.$('hour').value=p.hour;this.$('minute').value=p.minute;}
    this.$('calendarTime').hidden=!withTime;this.$('calendarTitle').textContent=withTime?'انتخاب تاریخ و ساعت شمسی':'انتخاب تاریخ شمسی';this.$('calendarError').hidden=true;
    this.render();this.el.showModal();this.$('calendarDays').querySelector('.selected')?.focus();
  }
  changeMonth(y,m){const old=persian(this.selected),days=monthDates(y,m);this.selected=days[Math.min(old.day,days.length)-1];this.render();}
  shift(delta){const p=persian(this.selected);let m=p.month+delta,y=p.year;if(m<1){y--;m=12;}if(m>12){y++;m=1;}if(y<1390||y>1450)return;this.changeMonth(y,m);}
  render(focus=false) {
    const p=persian(this.selected),dates=monthDates(p.year,p.month),container=this.$('calendarDays');
    this.$('calendarMonth').value=p.month;this.$('calendarYear').value=p.year;container.replaceChildren();
    const offset=(new Date(dates[0]+'T12:00:00Z').getUTCDay()-prefs.week+7)%7;
    const weekdays=['ی','د','س','چ','پ','ج','ش'];this.el.querySelector('.weekdays').replaceChildren(...Array.from({length:7},(_,i)=>{const span=document.createElement('span');span.textContent=weekdays[(prefs.week+i)%7];return span;}));
    for(const o of this.$('calendarYear').options)o.textContent=fa(Number(o.value));
    for(let i=0;i<offset;i++){const blank=document.createElement('span');blank.setAttribute('aria-hidden','true');container.append(blank);}
    for(const iso of dates){
      const b=document.createElement('button');b.type='button';b.textContent=fa(persian(iso).day);b.dataset.iso=iso;b.setAttribute('aria-label',dateLabel(iso));
      b.tabIndex=iso===this.selected?0:-1;b.classList.toggle('selected',iso===this.selected);b.classList.toggle('today',iso===todayISO());b.setAttribute('aria-pressed',String(iso===this.selected));
      b.onclick=()=>{this.selected=iso;this.render(true);};
      b.onkeydown=e=>{let delta={ArrowRight:-1,ArrowLeft:1,ArrowUp:-7,ArrowDown:7}[e.key];if(e.key==='Home')delta=1-persian(iso).day;if(e.key==='End')delta=dates.length-persian(iso).day;if(delta!==undefined){e.preventDefault();const next=addDays(iso,delta),q=persian(next);if(q.year>=1390&&q.year<=1450){this.selected=next;this.render(true);}}};
      container.append(b);
    }
    this.$('calendarSelection').textContent='انتخاب شده: '+dateLabel(this.selected);
    this.$('previousMonth').disabled=p.year===1390&&p.month===1;this.$('nextMonth').disabled=p.year===1450&&p.month===12;
    if(focus)container.querySelector('.selected')?.focus();
  }
}
