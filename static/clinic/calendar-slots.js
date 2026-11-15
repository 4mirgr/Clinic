document.querySelectorAll('[data-slot-form]').forEach(form=>{
  const day=form.querySelector('[name=day]'),selected=form.querySelector('[name=slot_start]');
  const box=form.querySelector('[data-slot-options]'),message=form.querySelector('[data-slots-message]'),submit=form.querySelector('[data-book-submit]');
  let controller;
  async function load(){
    controller?.abort();controller=new AbortController();selected.value='';submit.disabled=true;box.replaceChildren();message.textContent='در حال بررسی ساعت‌های آزاد…';
    const url=new URL(form.dataset.slotsUrl,location.origin);url.searchParams.set('day',day.value);
    if(form.dataset.appointment)url.searchParams.set('appointment',form.dataset.appointment);
    try{
      const response=await fetch(url,{credentials:'same-origin',signal:controller.signal,headers:{Accept:'application/json'}});
      const data=await response.json();
      if(!response.ok){message.textContent=data.error||'بررسی وقت‌ها کامل نشد؛ دوباره امتحان کنید.';return;}
      message.textContent=data.slots.length?'یکی از ساعت‌های آزاد به وقت تهران را انتخاب کنید.':'در این روز ساعت آزادی پیدا نشد؛ روز دیگری انتخاب کنید.';
      data.slots.forEach(slot=>{
        const label=document.createElement('label');label.className='slot-choice';const radio=document.createElement('input');radio.type='radio';radio.name='slot-choice';radio.value=slot.start;
        const text=document.createElement('span');text.textContent=slot.label;label.append(radio,text);
        radio.addEventListener('change',()=>{selected.value=radio.value;submit.disabled=false;});box.append(label);
      });
    }catch(error){if(error.name!=='AbortError')message.textContent='ارتباط برقرار نشد؛ هیچ وقتی تأیید نشده است.';}
  }
  form.querySelector('[data-load-slots]').addEventListener('click',load);day.addEventListener('change',load);
  form.addEventListener('submit',()=>{submit.disabled=true;submit.textContent='در حال ثبت و بررسی…';});
});
