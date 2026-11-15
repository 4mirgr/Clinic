import {toJalaali,toGregorian,jalaaliMonthLength,isValidJalaaliDate} from './vendor/jalaali.js';

const months=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
const fa=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
const ascii=s=>s.replace(/[۰-۹٠-٩]/g,c=>String('۰۱۲۳۴۵۶۷۸۹'.includes(c)?'۰۱۲۳۴۵۶۷۸۹'.indexOf(c):'٠١٢٣٤٥٦٧٨٩'.indexOf(c)));
const formatted=(y,m,d)=>fa(`${y}/${String(m).padStart(2,'0')}/${String(d).padStart(2,'0')}`);

document.querySelectorAll('[data-jalali-picker]').forEach(wrapper=>{
  const input=wrapper.querySelector('input'),toggle=wrapper.querySelector('.jalali-open'),popup=wrapper.querySelector('.jalali-popup');
  let today;
  try {
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const get=key=>Number(parts.find(p=>p.type===key).value);
    today=toJalaali(get('year'),get('month'),get('day'));
  } catch {
    const [y,m,d]=wrapper.dataset.today.split('-').map(Number);today=toJalaali(y,m,d);
  }
  if(!input.value) input.value=formatted(today.jy,today.jm,today.jd);
  let year=today.jy,month=today.jm;
  const read=()=>{
    const match=ascii(input.value).match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
    if(!match)return null;
    const [y,m,d]=match.slice(1).map(Number);return isValidJalaaliDate(y,m,d)?{y,m,d}:null;
  };
  const close=returnFocus=>{popup.hidden=true;toggle.setAttribute('aria-expanded','false');if(returnFocus)toggle.focus();};
  const choose=(y,m,d)=>{input.value=formatted(y,m,d);input.dispatchEvent(new Event('change',{bubbles:true}));close(true);};
  const button=(label,text,action,cls='')=>{
    const element=document.createElement('button');element.type='button';element.textContent=text;element.setAttribute('aria-label',label);element.className=cls;element.addEventListener('click',action);return element;
  };
  const changeMonth=delta=>{month+=delta;if(month<1){month=12;year--;}if(month>12){month=1;year++;}render();};
  function render(){
    popup.replaceChildren();
    const head=document.createElement('div');head.className='jalali-head';
    head.append(button('ماه قبل','→',()=>changeMonth(-1)));
    const title=document.createElement('strong');title.textContent=`${months[month-1]} ${fa(year)}`;title.setAttribute('aria-live','polite');head.append(title,button('ماه بعد','←',()=>changeMonth(1)));
    popup.append(head);
    const days=document.createElement('div');days.className='jalali-weekdays';['ش','ی','د','س','چ','پ','ج'].forEach(day=>{const item=document.createElement('span');item.textContent=day;days.append(item);});popup.append(days);
    const grid=document.createElement('div');grid.className='jalali-grid';grid.setAttribute('role','group');grid.setAttribute('aria-label','روزهای ماه');
    const first=toGregorian(year,month,1);const offset=(new Date(Date.UTC(first.gy,first.gm-1,first.gd,12)).getUTCDay()+1)%7;
    for(let i=0;i<offset;i++){const blank=document.createElement('span');grid.append(blank);}
    const selected=read();
    for(let day=1;day<=jalaaliMonthLength(year,month);day++){
      const item=button(`${fa(day)} ${months[month-1]} ${fa(year)}`,fa(day),()=>choose(year,month,day),'jalali-day');
      item.dataset.day=String(day);
      if(selected&&selected.y===year&&selected.m===month&&selected.d===day){item.classList.add('selected');item.setAttribute('aria-pressed','true');}
      if(year===today.jy&&month===today.jm&&day===today.jd){item.classList.add('today');item.setAttribute('aria-current','date');}
      item.addEventListener('keydown',event=>{
        const delta={ArrowLeft:1,ArrowRight:-1,ArrowUp:-7,ArrowDown:7}[event.key];if(!delta)return;event.preventDefault();
        const next=day+delta;if(next>=1&&next<=jalaaliMonthLength(year,month))grid.querySelector(`[data-day="${next}"]`)?.focus();
      });
      grid.append(item);
    }
    popup.append(grid);
    const footer=document.createElement('div');footer.className='jalali-footer';footer.append(button(`انتخاب امروز ${formatted(today.jy,today.jm,today.jd)}`,'امروز',()=>choose(today.jy,today.jm,today.jd)),button('بستن تقویم','بستن',()=>close(true)));popup.append(footer);
  }
  toggle.addEventListener('click',()=>{
    if(!popup.hidden){close(false);return;}
    const value=read();year=value?.y||today.jy;month=value?.m||today.jm;render();popup.hidden=false;toggle.setAttribute('aria-expanded','true');
    popup.querySelector('.selected,.today,.jalali-day')?.focus();
  });
  wrapper.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close(true);}});
  document.addEventListener('pointerdown',event=>{if(!wrapper.contains(event.target))close(false);});
});
