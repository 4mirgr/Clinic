document.querySelector('.menu-toggle')?.addEventListener('click', event => {
  const expanded = event.currentTarget.getAttribute('aria-expanded') !== 'true';
  event.currentTarget.setAttribute('aria-expanded', String(expanded));
  document.querySelector('.sidebar')?.classList.toggle('is-open', expanded);
});
document.querySelectorAll('[data-preview-form]').forEach(form => {
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (form.classList.contains('theme-form')) {
      const dark = document.documentElement.dataset.theme !== 'dark';
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      document.querySelectorAll('.theme-icon').forEach(icon => icon.textContent = dark ? '☀' : '☾');
      document.querySelectorAll('.theme-label').forEach(label => label.textContent = dark ? 'حالت روز' : 'حالت شب');
    }
  });
});
document.querySelectorAll('[name=q]:not(#advice-search)').forEach(input => {
  input.addEventListener('input', () => {
    const query = input.value.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک');
    document.querySelectorAll('.advice-card,.patient-row').forEach(row => row.hidden = !row.textContent.includes(query));
  });
});
document.querySelector('[data-print]')?.addEventListener('click', async () => {
  await document.fonts.ready;
  window.print();
});

// Entirely local educational demonstration. Never submits patient data or calls an API.
(() => {
 const root=document.querySelector('[data-library]');if(!root)return;
 const normal=s=>s.normalize('NFKC').toLowerCase().replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/[\u064B-\u065F\u0670\u0640]/g,'').replace(/[\u200c\u200f]/g,' ').replace(/\s+/g,' ').trim();
 const query=root.querySelector('[name=q]'),specialty=root.querySelector('[name=specialty]'),cards=[...root.querySelectorAll('[data-advice-card]')],selected=new Map();
 const filter=()=>{const tokens=normal(query.value).split(' ').filter(Boolean);let count=0;cards.forEach(c=>{c.hidden=!!(specialty.value&&c.dataset.specialty!==specialty.value)||!tokens.every(t=>normal(c.dataset.search).includes(t));if(!c.hidden)count++});root.querySelector('[data-no-results]').hidden=count>0;root.querySelector('[data-result-count]').textContent=`${count.toLocaleString('fa-IR')} راهنما`};
 query.addEventListener('input',filter);specialty.addEventListener('change',filter);
 const update=()=>root.querySelector('[data-selection-count]').textContent=`${selected.size.toLocaleString('fa-IR')} توصیه انتخاب شده`;
 root.querySelectorAll('[name=advice_ids]').forEach(input=>input.addEventListener('change',()=>{input.checked?selected.set(input.value,input):selected.delete(input.value);update()}));
 root.querySelector('[data-clear-selection]').addEventListener('click',()=>{selected.forEach(i=>i.checked=false);selected.clear();update()});
 root.querySelector('[data-demo-combine]')?.addEventListener('click',async()=>{
   if(!selected.size){alert('دست‌کم یک توصیه انتخاب کنید.');return}
   document.querySelector('.demo-print-stage')?.remove();
   const stage=document.createElement('main');stage.className='demo-print-stage packet-sheet';stage.append(document.querySelector('#demo-packet-shell').content.cloneNode(true));
   const controls=document.createElement('nav');controls.className='print-toolbar';
   const back=document.createElement('button');back.type='button';back.textContent='بازگشت به انتخاب توصیه‌ها';back.onclick=()=>{stage.remove();document.body.classList.remove('printing-demo');document.querySelector('.workspace').hidden=false};
   const print=document.createElement('button');print.type='button';print.textContent='چاپ / ذخیره PDF';print.onclick=async()=>{await document.fonts.ready;await Promise.all([...stage.querySelectorAll('img')].map(i=>i.decode().catch(()=>{})));window.print()};
   controls.append(back,print);stage.prepend(controls);
   selected.forEach((input,id)=>stage.querySelector('[data-demo-guides]').append(root.querySelector(`[data-guide-template="${id}"]`).content.cloneNode(true)));
   document.body.append(stage);document.body.classList.add('printing-demo');document.querySelector('.workspace').hidden=true;window.scrollTo(0,0);await document.fonts.ready;
 });filter();update();
})();

// Global patient search stays in the finite synthetic export; no patient API.
document.querySelector('.top-search')?.addEventListener('submit',event=>{
 event.preventDefault();location.assign('/clinic/patients/?q='+encodeURIComponent(event.target.elements.q.value));
});
(() => {
 const input=document.querySelector('#patient-search');if(!input)return;
 const normalize=s=>s.normalize('NFKC').toLowerCase().replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/\s+/g,' ').trim();
 const initial=new URLSearchParams(location.search).get('q');if(initial)input.value=initial.slice(0,200);
 const filter=()=>{const query=normalize(input.value);document.querySelectorAll('tbody tr').forEach(row=>row.hidden=!normalize(row.textContent).includes(query));};input.addEventListener('input',filter);filter();
})();
