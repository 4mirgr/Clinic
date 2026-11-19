document.querySelectorAll('[data-prescription-window]').forEach(link=>link.addEventListener('click',event=>{
 event.preventDefault();
 const allowed=new Set(['https://panel.drnext.ir/','https://ep.tamin.ir/','https://eservices.ihio.gov.ir/ihioerx/']);
 if(!allowed.has(link.href))return;
 window.open(link.href,'_blank','popup,width=1000,height=850,noopener,noreferrer');
}));
