(() => {
 const base='/dash/api/portal/';let csrf='',busy=false,profileDirty=false,profileChangeVersion=0;const $=id=>document.getElementById(id);
 const notice=text=>{$('portal-notice').textContent=text;};
 async function api(path,data){if(data!==undefined&&!csrf){const session=await api('session');csrf=session.csrf_token;}const isFile=data instanceof FormData;const response=await fetch(base+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:data===undefined?{}:{'X-CSRFToken':csrf,...(isFile?{}:{'Content-Type':'application/json'})},...(data===undefined?{}:{body:isFile?data:JSON.stringify(data)})});let value;try{value=await response.json();}catch{throw Error('دریافت اطلاعات انجام نشد.');}if(!response.ok){const error=Error(({csrf_rejected:'نشست فرم تازه شود؛ صفحه را دوباره بارگیری کنید.',invalid_phone:'شمارهٔ همراه معتبر وارد کنید.',profile_incomplete:'ابتدا مشخصات پروفایل را تکمیل کنید.',invalid_file:'فایل معتبر PDF، PNG یا JPG تا ۵ مگابایت انتخاب کنید.',sign_in_required:'دوباره وارد حساب شوید.'})[value.error]||'عملیات انجام نشد. اطلاعات و اتصال را بررسی کنید.');error.rejected=response.status<500;throw error;}if(value.csrf_token)csrf=value.csrf_token;return value;}
 const row=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
 async function load(){const [profile,documents,privacy,history]=await Promise.all([api('profile'),api('documents'),api('privacy'),api('activity')]);const saved=document.querySelector('[data-intake-saved]');if(saved)saved.textContent=profile.intake_saved_at?new Intl.DateTimeFormat('fa-IR-u-ca-persian',{year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(profile.intake_saved_at)):'هنوز ثبت نشده';const reported=Object.entries(profile.profile).filter(([key])=>key.startsWith('reported_'));const filled=reported.filter(([,value])=>String(value).trim()).length;document.querySelector('[data-intake-progress]')?.replaceChildren(document.createTextNode(Math.round(filled*100/Math.max(1,reported.length))+'٪'));for(const [key,value]of Object.entries(profile.profile)){const field=$('portal-profile').elements.namedItem(key);if(field&&!profileDirty)field.value=value;}$('portal-documents').replaceChildren();for(const item of documents.documents){const box=row('div',item.title);box.className='patient-document';const a=row('a',' دریافت فایل');a.href=item.download_url;box.append(a);$('portal-documents').append(box);}if(!documents.documents.length)$('portal-documents').append(row('p','مدرکی ثبت نشده است.'));for(const key of ['track_activity','share_activity'])$('portal-privacy').elements.namedItem(key).checked=privacy.privacy[key];$('portal-activity').replaceChildren(...history.events.map(item=>row('p',(item.kind==='search'?'جست‌وجو: ':'مقالهٔ بازشده: ')+item.value+' · '+item.count+' بار')));document.dispatchEvent(new Event('intake:hydrated'));}
 async function run(action){if(busy)return;busy=true;document.querySelectorAll('button[type=submit]').forEach(button=>button.disabled=true);try{const message=await action();await load();notice(typeof message==='string'?message:'تغییرات در پروندهٔ مشترک ذخیره شدند.');}catch(error){notice(error.message);}finally{busy=false;document.querySelectorAll('button[type=submit]').forEach(button=>button.disabled=false);}}
 $('portal-profile').addEventListener('input',()=>{profileDirty=true;profileChangeVersion++;});
 $('portal-profile').addEventListener('submit',event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.target)),version=profileChangeVersion;delete values.csrfmiddlewaretoken;void run(async()=>{await api('profile',values);if(version===profileChangeVersion)profileDirty=false;return profileDirty?'اطلاعات ارسال‌شده ذخیره شد؛ تغییرات تازه‌تر فرم را هم ذخیره کنید.':'تغییرات در پروندهٔ مشترک ذخیره شدند.';});});

 const upload=$('portal-upload'),results=$('portal-upload-results');let uploadItems=[];
 const inferCategory=name=>/echo|اکو/i.test(name)?'echo':/x[ -]?ray|گرافی/i.test(name)?'xray':/\bct\b|سی.?تی/i.test(name)?'ct':/lab|آزمایش/i.test(name)?'lab':'other';
 const fileTitle=file=>file.name.replace(/\.[^.]+$/,'').replace(/[_-]/g,' ').trim().slice(0,190)||'مدرک پزشکی';
 function showUploads(){results.replaceChildren();uploadItems.forEach(item=>{const li=row('li',item.file.name+' — '+item.status);li.dataset.uploadState=item.state;results.append(li);});}
 for(const input of upload.querySelectorAll('input[type=file]'))input.addEventListener('change',()=>{
  const files=[...upload.elements.file.files,...upload.elements.camera_file.files];
  const existing=new Map(uploadItems.map(item=>[item.file,item]));uploadItems=files.map(file=>existing.get(file)||{file,state:'ready',status:'آماده ارسال'});showUploads();
 });
 upload.addEventListener('submit',event=>{event.preventDefault();void run(async()=>{
  if(!uploadItems.length)throw Error('حداقل یک فایل انتخاب کنید یا از مدرک عکس بگیرید.');
  let sent=0,failed=0,uncertain=0;
  for(const item of uploadItems){
   if(item.state==='sent')continue;if(item.state==='unknown'){uncertain++;continue;}
   if(!/\.(pdf|png|jpe?g)$/i.test(item.file.name)||!item.file.size||item.file.size>5*1024*1024){item.state='failed';item.status='فرمت PDF، PNG یا JPG و حجم حداکثر ۵ مگابایت لازم است.';failed++;showUploads();continue;}
   const data=new FormData();const title=upload.elements.title.value.trim();
   data.set('title',(title?(uploadItems.length>1?title+' — '+fileTitle(item.file):title):fileTitle(item.file)).slice(0,200));
   data.set('category',upload.elements.category.value==='auto'?inferCategory(item.file.name):upload.elements.category.value);data.set('file',item.file);
   item.status='در حال ارسال…';item.state='sending';showUploads();
   try{await api('documents',data);item.state='sent';item.status='ارسال شد';sent++;}
   catch(error){item.state=error.rejected?'failed':'unknown';item.status=error.rejected?error.message:'نتیجه دریافت نشد. فهرست مدارک را بررسی کنید؛ این فایل خودکار دوباره ارسال نمی‌شود.';if(error.rejected)failed++;else uncertain++;}
   showUploads();
  }
  if(!failed&&!uncertain){upload.reset();return sent+' مدرک ارسال شد.';}
  return sent+' مدرک ارسال شد؛ '+failed+' مورد ناموفق و '+uncertain+' مورد با نتیجه نامشخص. وضعیت هر فایل در فهرست نوشته شده است. ارسال دوباره فقط برای موارد ناموفق انجام می‌شود؛ موارد موفق یا نامشخص دوباره فرستاده نمی‌شوند.';
 });});

 $('portal-privacy').addEventListener('submit',event=>{event.preventDefault();void run(()=>api('privacy',Object.fromEntries(['track_activity','share_activity'].map(key=>[key,event.target.elements.namedItem(key).checked]))));});
 $('portal-erase').addEventListener('click',()=>{void run(()=>api('activity',{action:'erase'}));});
 void load().catch(error=>notice(error.message));
})();
