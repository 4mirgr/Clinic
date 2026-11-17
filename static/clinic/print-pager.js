// Chromium repeats table headers/footers while reserving their own space.
// Fixed elements at negative offsets can overlap paginated clinical text.
window.addEventListener('beforeprint', () => {
 document.querySelectorAll('.packet-sheet').forEach(sheet => {
   if(sheet.querySelector('.print-pagination'))return;
   const header=sheet.querySelector(':scope > .print-brand:not(.print-footer)'),footer=sheet.querySelector(':scope > .print-footer');
   if(!header||!footer)return;
   const table=document.createElement('table');table.className='print-pagination';
   const head=table.createTHead(),body=table.createTBody(),foot=table.createTFoot();
   head.insertRow().insertCell().append(header);foot.insertRow().insertCell().append(footer);
   const cell=body.insertRow().insertCell();
   [...sheet.childNodes].filter(node=>!(node.nodeType===1&&node.classList.contains('print-toolbar'))).forEach(node=>cell.append(node));
   sheet.append(table);
 });
});
