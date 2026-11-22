(() => {
 const form=document.getElementById('communication-preferences');if(!form)return;
 const status=document.getElementById('communication-channel-status');
 const notice=document.getElementById('communication-notice');
 const fields=['email_opt_in','telegram_opt_in','whatsapp_opt_in','appointment_reminders','followup_reminders','advice_notifications'];
 const url='/dash/api/communications/preferences';let csrf='';const telegram=document.getElementById('telegram-link');
 function render(data){
  if(telegram)telegram.disabled=!data.telegram_link_available;
  for(const key of fields)form.elements.namedItem(key).checked=!!data.preferences[key];
  status.replaceChildren(...data.channels.map(channel=>{
   const p=document.createElement('p');p.className='hint';
   p.textContent=channel.label+' · '+(channel.enabled?'آمادهٔ ارسال طبق انتخاب شما':!channel.verified?'در انتظار تأیید راه ارتباطی توسط مطب':'فعلاً آمادهٔ ارسال نیست')+' — '+channel.reason;
   return p;
  }));
 }
 async function call(data,path=url){
  if(data&&!csrf){const s=await fetch('/dash/api/portal/session',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json());csrf=s.csrf_token;}
  const r=await fetch(path,{method:data?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:data?{'Content-Type':'application/json','X-CSRFToken':csrf}:{},...(data?{body:JSON.stringify(data)}:{})});
  if(!r.ok)throw Error('تنظیم یادآوری‌ها دریافت یا ذخیره نشد؛ دوباره تلاش کنید.');return r.json();
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{render(await call(Object.fromEntries(fields.map(key=>[key,form.elements.namedItem(key).checked]))));notice.textContent='انتخاب‌های یادآوری ذخیره شد. وضعیت آماده‌بودن کانال‌ها را در بالا ببینید.';}catch(error){notice.textContent=error.message;}finally{button.disabled=false;}
 });
 telegram?.addEventListener('click',async()=>{
  telegram.disabled=true;const result=document.getElementById('telegram-link-result');
  try{const data=await call({},'/dash/api/communications/telegram/link');const link=document.createElement('a');link.href=data.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='باز کردن ربات و زدن Start';result.replaceChildren(link,document.createTextNode(' — پس از Start، وضعیت کانال را با بازکردن دوباره این صفحه ببینید. این پیوند ۱۵ دقیقه معتبر است.'));}catch(error){result.textContent=error.message;}finally{telegram.disabled=false;}
 });
 call().then(render).catch(error=>{notice.textContent=error.message;});
})();
