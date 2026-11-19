(() => {
 const notice=document.querySelector('#shared-account-notice');
 const message=text=>{if(notice)notice.textContent=text};
 document.querySelectorAll('[data-auth-mode]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelector('#shared-login').hidden=button.dataset.authMode!=='login';
  document.querySelector('#shared-signup').hidden=button.dataset.authMode!=='signup';message('');
 }));
 for(const [id,route] of [['shared-login','login'],['shared-signup','signup']]){
  document.getElementById(id)?.addEventListener('submit',async event=>{
   event.preventDefault();const form=event.target,button=form.querySelector('button[type=submit]');button.disabled=true;
   try{
    const session=await fetch('/dash/api/portal/session',{credentials:'same-origin',cache:'no-store'}).then(r=>r.json());
    const values=Object.fromEntries(new FormData(form));delete values.csrfmiddlewaretoken;
    const response=await fetch('/dash/api/portal/'+route,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRFToken':session.csrf_token},body:JSON.stringify(values)});
    const data=await response.json();
    if(!response.ok)throw Error(data.error==='try_later'?'تلاش‌های زیادی انجام شده؛ کمی بعد دوباره امتحان کنید.':'اطلاعات ورود یا شرایط ثبت‌نام را بررسی کنید. رمز باید دست‌کم ۱۲ نویسه و قابل حدس نباشد.');
    form.reset();const next=new URLSearchParams(location.search).get('next')||'';
    const safe=next.startsWith('/dash/')&&!next.includes('\\')&&!/[\x00-\x1f]/.test(next);
    location.assign(safe?next:(data.user.clinic_role?'/dash/':'/dash/portal/'));
   }catch(error){message(error.message)}finally{button.disabled=false}
  });
 }
})();
