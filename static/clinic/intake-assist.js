/* Local patient-entered shortcuts. No network, storage, diagnosis or dose suggestions. */
(() => {
 'use strict';
 const normal=value=>value.normalize('NFKC').toLowerCase().replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/[\u064B-\u065F\u0670\u0640]/g,'').replace(/[\u200c\u200f]/g,' ').replace(/\s+/g,' ').trim();
 const diseases=[['دیابت','Diabetes DM قند خون'],['فشار خون بالا','Hypertension HTN'],['چربی خون','Dyslipidemia Hyperlipidemia'],['بیماری عروق قلب','Coronary artery disease CAD'],['نارسایی قلب','Heart failure HF'],['اختلال ضربان قلب','Arrhythmia AF'],['آسم','Asthma'],['بیماری مزمن ریه','COPD'],['رفلاکس معده','GERD Reflux'],['زخم معده','Peptic ulcer'],['کبد چرب','Fatty liver MASLD NAFLD'],['بیماری مزمن کلیه','Chronic kidney disease CKD'],['سنگ کلیه','Kidney stone'],['کم کاری تیروئید','Hypothyroidism'],['پرکاری تیروئید','Hyperthyroidism'],['کم خونی','Anemia'],['پوکی استخوان','Osteoporosis'],['آرتروز','Osteoarthritis'],['بیماری روماتیسمی','Rheumatic disease'],['سکته مغزی','Stroke CVA'],['سرطان','Cancer Malignancy'],['آپنه خواب','Sleep apnea OSA']];
 const catalog={
  reported_current_problem:[['درد شکم','Abdominal pain'],['سوزش سردل','Heartburn Reflux'],['تهوع','Nausea'],['نفخ','Bloating'],['اسهال','Diarrhea'],['یبوست','Constipation'],['سرفه','Cough'],['تنگی نفس','Dyspnea'],['خستگی','Fatigue'],['تب','Fever'],['سرگیجه','Dizziness'],['سردرد','Headache'],['ورم پا','Leg edema'],['تپش قلب','Palpitations'],['پیگیری آزمایش','Lab follow-up'],['پیگیری بیماری قبلی','Follow-up']],
  reported_onset:[['از امروز','Today'],['از دیروز','Yesterday'],['چند روز','Days'],['چند هفته','Weeks'],['چند ماه','Months'],['علائم بهتر شده','Improving'],['علائم بدتر شده','Worsening'],['بدون تغییر','Unchanged'],['گاهی رخ می‌دهد','Intermittent']],
  reported_history:diseases,
  reported_family_history:diseases,
  reported_surgeries:[['آپاندیس','Appendectomy'],['کیسه صفرا','Cholecystectomy'],['جراحی قلب','Cardiac surgery'],['آنژیوپلاستی یا استنت','Angioplasty Stent PCI'],['بستری قبلی','Hospitalization'],['سایر عمل‌ها','Other surgery']],
  reported_medications:[['متفورمین','Metformin'],['انسولین','Insulin'],['لوزارتان','Losartan'],['والسارتان','Valsartan'],['آملودیپین','Amlodipine'],['متوپرولول','Metoprolol'],['بیزوپرولول','Bisoprolol'],['آتورواستاتین','Atorvastatin'],['روزوواستاتین','Rosuvastatin'],['لووتیروکسین','Levothyroxine'],['پنتوپرازول','Pantoprazole'],['امپرازول','Omeprazole'],['آسپرین','Aspirin'],['کلوپیدوگرل','Clopidogrel'],['وارفارین','Warfarin'],['آپیکسابان','Apixaban'],['فوروزماید','Furosemide'],['اسپیرونولاکتون','Spironolactone'],['سالبوتامول','Salbutamol Albuterol']],
  reported_supplements:[['ویتامین D','Vitamin D'],['آهن','Iron'],['ویتامین B12','Vitamin B12'],['کلسیم','Calcium'],['مولتی ویتامین','Multivitamin'],['داروی گیاهی','Herbal supplement'],['مسکن بدون نسخه','OTC pain medicine']],
  reported_allergies:[['پنی سیلین','Penicillin'],['آموکسی سیلین','Amoxicillin'],['سفالوسپورین','Cephalosporin'],['سولفونامید','Sulfonamide'],['آسپرین','Aspirin'],['ایبوپروفن','Ibuprofen NSAID'],['ماده حاجب','Contrast'],['لاتکس','Latex'],['حساسیت غذایی','Food allergy']],
  reported_social_history:[['سیگار می‌کشم','Smoking'],['سیگار را ترک کرده‌ام','Former smoker'],['قلیان مصرف می‌کنم','Hookah'],['دخانیات مصرف نمی‌کنم','Non-smoker'],['الکل مصرف می‌کنم','Alcohol'],['فعالیت بدنی منظم دارم','Exercise'],['فعالیت بدنی کم دارم','Sedentary'],['تماس شغلی مهم دارم','Occupational exposure']]
 };
 const definitions=[];
 document.querySelectorAll('#portal-profile textarea[name]').forEach(field=>{
  const options=catalog[field.name];if(!options)return;
  const wrapper=document.createElement('div');wrapper.className='intake-assist';
  const label=field.closest('label');const heading=label?.querySelector('[data-field-title]')?.textContent.trim()||label?.firstChild?.textContent.trim()||'اطلاعات';
  const search=document.createElement('input');search.type='search';search.className='intake-search';search.placeholder='جست‌وجو به فارسی یا English…';search.autocomplete='off';search.setAttribute('aria-label','جست‌وجوی '+heading+' به فارسی یا انگلیسی');
  const list=document.createElement('div');list.className='intake-options';list.setAttribute('role','group');list.setAttribute('aria-label','انتخاب سریع '+heading);
  const status=document.createElement('p');status.className='intake-assist-status';status.setAttribute('role','status');
  const owned=new Set();const buttons=[];
  const emit=()=>{field.dispatchEvent(new Event('input',{bubbles:true}));};
  const update=()=>{buttons.forEach(({button,line})=>{const selected=field.value.split('\n').includes(line);if(selected)owned.add(line);else owned.delete(line);button.setAttribute('aria-pressed',String(selected));button.disabled=field.disabled;});};
  function add(label,english,preset=false){
   const button=document.createElement('button');button.type='button';button.className='intake-chip';button.textContent=label;button.setAttribute('aria-pressed','false');
   const line=preset?label:label+' ('+english.split(' ').slice(0,2).join(' ')+')';
   const term=normal(label+' '+english);buttons.push({button,line,term});
   button.addEventListener('click',()=>{
    if(field.disabled)return;
    const lines=field.value.split('\n');
    if(owned.has(line)&&lines.includes(line)){
     // Only remove the exact selected catalog line; untouched prose stays intact.
     const index=lines.lastIndexOf(line);lines.splice(index,1);field.value=lines.join('\n');owned.delete(line);status.textContent='این انتخاب برداشته شد؛ متن دیگر شما حفظ شد.';
    }else{
     if(lines.includes(line)){status.textContent='این مورد در متن شما وجود دارد؛ می‌توانید توضیحش را ویرایش کنید.';return;}
     if(preset&&field.value.trim()&&!['ندارم','نمی‌دانم'].includes(field.value.trim())){status.textContent='اطلاعاتی نوشته‌اید. برای انتخاب «ندارم» یا «نمی‌دانم»، ابتدا متن را خودتان بررسی و اصلاح کنید.';return;}
     if(['ندارم','نمی‌دانم'].includes(field.value.trim())){field.value='';owned.clear();}
     const next=field.value+(field.value&&!field.value.endsWith('\n')?'\n':'')+line;
     if(next.length>field.maxLength){status.textContent='ظرفیت این بخش پر شده است؛ متن را کوتاه‌تر کنید.';return;}
     field.value=next;owned.add(line);status.textContent=preset?'ثبت در فرم انجام شد؛ برای نگهداری، دکمه ذخیره را بزنید.':'به متن اضافه شد؛ اگر لازم است زمان، مقدار یا توضیح را بنویسید.';
    }
    update();emit();
   });list.append(button);
  }
  if(!['reported_onset','reported_current_problem'].includes(field.name)){add('ندارم','None',true);add('نمی‌دانم','Unknown',true);}else if(field.name==='reported_onset'){add('نمی‌دانم','Unknown',true);}
  options.forEach(([fa,en])=>add(fa,en));
  let showAll=false;const more=document.createElement('button');more.type='button';more.className='intake-more';more.textContent='نمایش همه گزینه‌ها';
  const filter=()=>{const tokens=normal(search.value).split(' ').filter(Boolean);let count=0;buttons.forEach(({button,term},i)=>{button.hidden=tokens.length?!tokens.every(token=>term.includes(token)):(!showAll&&i>=6);if(!button.hidden)count++;});more.hidden=!!tokens.length||buttons.length<=6;more.textContent=showAll?'نمایش گزینه‌های کمتر':'نمایش همه گزینه‌ها';more.setAttribute('aria-expanded',String(showAll));status.textContent=count?'': 'موردی پیدا نشد؛ نام مورد خود را در کادر توضیح بنویسید.';};more.addEventListener('click',()=>{showAll=!showAll;filter();});
  search.addEventListener('input',filter);search.addEventListener('keydown',event=>{if(event.key==='Enter')event.preventDefault();});field.addEventListener('input',update);
  const title=document.createElement('h3');title.className='intake-assist-heading';title.textContent=heading;wrapper.append(title,search,list,more,status);label.before(wrapper);definitions.push(update);filter();update();
 });
 const progress=()=>document.querySelectorAll('.intake-step').forEach(step=>{const fields=[...step.querySelectorAll('textarea[name]')];const count=fields.filter(field=>field.value.trim()).length;const indicator=step.querySelector('[data-step-count]');if(indicator)indicator.textContent=count+' از '+fields.length+' پاسخ';});
 document.querySelector('#portal-profile')?.addEventListener('input',progress);
 document.addEventListener('intake:hydrated',()=>{definitions.forEach(update=>update());progress();});
 document.querySelectorAll('[data-open-intake]').forEach(button=>button.addEventListener('click',()=>{const next=document.querySelector(button.dataset.openIntake);if(next){next.open=true;next.scrollIntoView({behavior:'smooth',block:'start'});}}));
 document.querySelector('#portal-profile')?.addEventListener('invalid',event=>{for(let node=event.target.parentElement;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;},true);
 progress();
})();
