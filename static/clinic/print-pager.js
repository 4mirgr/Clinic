// Chromium repeats table headers while reserving their own space.
// Fixed elements at negative offsets can overlap paginated clinical text.
window.addEventListener('beforeprint', () => {
 document.querySelectorAll('.packet-sheet').forEach(sheet => {
   if(sheet.querySelector('.print-pagination'))return;
   const header=sheet.querySelector(':scope > .print-brand');
   if(!header)return;
   const table=document.createElement('table');table.className='print-pagination';
   const head=table.createTHead(),body=table.createTBody();
   head.insertRow().insertCell().append(header);
   const cell=body.insertRow().insertCell();
   [...sheet.childNodes].filter(node=>!(node.nodeType===1&&(node.classList.contains('print-toolbar')||node.classList.contains('pdf-watermark')))).forEach(node=>cell.append(node));
   sheet.append(table);
 });
});
