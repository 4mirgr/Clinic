(() => {
 const root=document.querySelector('[data-library]'); if(!root)return;
 const normal=s=>s.normalize('NFKC').toLowerCase().replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/[\u064B-\u065F\u0670\u0640]/g,'').replace(/[\u200c\u200f]/g,' ').replace(/\s+/g,' ').trim();
 const query=root.querySelector('[name=q]'),specialty=root.querySelector('[name=specialty]'),cards=[...root.querySelectorAll('[data-advice-card]')],selected=new Map();
 const filter=()=>{const tokens=normal(query.value).split(' ').filter(Boolean);let count=0;cards.forEach(c=>{c.hidden=!!(specialty.value&&c.dataset.specialty!==specialty.value)||!tokens.every(t=>normal(c.dataset.search).includes(t));if(!c.hidden)count++});root.querySelector('[data-no-results]').hidden=count>0;root.querySelector('[data-result-count]').textContent=`${count.toLocaleString('fa-IR')} راهنما`};
 const count=()=>{root.querySelector('[data-selection-count]').textContent=`${selected.size.toLocaleString('fa-IR')} توصیه انتخاب شده`};
 query.addEventListener('input',filter);specialty.addEventListener('change',filter);query.form.addEventListener('submit',e=>{e.preventDefault();filter()});
 root.querySelectorAll('[name=advice_ids]').forEach(input=>input.addEventListener('change',()=>{if(input.checked)selected.set(input.value,input);else selected.delete(input.value);count()}));
 root.querySelector('[data-clear-selection]').addEventListener('click',()=>{selected.forEach(input=>input.checked=false);selected.clear();count()});
 const form=root.querySelector('[data-packet-selection]');
 form.addEventListener('submit',event=>{event.preventDefault();if(!selected.size){alert('دست‌کم یک توصیه انتخاب کنید.');return}const ids=[...selected.keys()];const data=new FormData(form);data.delete('advice_ids');ids.forEach(id=>data.append('advice_ids',id));const submit=document.createElement('form');submit.method='post';submit.action=form.action;for(const [name,value] of data){const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;submit.append(input)}document.body.append(submit);submit.submit()});
 filter();count();
})();
