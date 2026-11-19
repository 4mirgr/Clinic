import assert from 'node:assert/strict';
import {test} from 'node:test';
import {withAccountEntry} from './account-entry.mjs';
const manifest={'/clinic/':{type:'text/html'},'/clinic/portal/':{type:'text/html'},'/clinic/patients/':{type:'text/html'},'/clinic/x.css':{type:'text/css'}};
test('shared preview entrance verifies live roles, never exposes live medical actions or forwards unrelated cookies',async()=>{
 let role='user',outage=false,calls=0;const original=globalThis.fetch;
 const worker=withAccountEntry({fetch:async req=>new Response('synthetic',{status:req.method==='POST'?405:200,headers:{'X-Clinic-Preview':'read-only'}})},manifest);
 const visit=(path,method='GET',token=true)=>worker.fetch(new Request('https://drgerami-md.ir'+path,{method,headers:token?{Cookie:'unrelated=private; __Host-gerami-access=signed.synthetic.token'}:{}}),{},{});
 globalThis.fetch=async(url,options)=>{calls++;assert.equal(url,'https://drgerami-md.ir/api/account/session');assert.equal(options.headers.Cookie,'__Host-gerami-access=signed.synthetic.token');assert.equal(options.redirect,'manual');if(outage)throw Error();return Response.json({authenticated:true,account:{role}});};
 try{
  assert.match((await visit('/clinic/','GET',false)).headers.get('Location'),/pages\/account.html/);assert.equal(calls,0);
  assert.equal((await visit('/clinic/account/')).status,302);assert.equal(calls,0);
  assert.equal((await visit('/clinic/')).headers.get('Location'),'/clinic/portal/');
  assert.equal((await visit('/clinic/patients/')).headers.get('Location'),'/clinic/portal/');
  let result=await visit('/clinic/portal/');assert.equal(result.status,200);assert.equal(result.headers.get('X-Clinic-Preview'),'read-only');assert.equal(result.headers.get('Cache-Control'),'private, no-store');
  for(role of ['admin','secretary']){assert.equal((await visit('/clinic/')).status,200);assert.equal((await visit('/clinic/portal/')).headers.get('Location'),'/clinic/');}
  outage=true;assert.equal((await visit('/clinic/')).status,503);
  const before=calls;assert.equal((await visit('/clinic/x.css')).status,200);assert.equal((await visit('/clinic/','POST')).status,405);assert.equal(calls,before);
 }finally{globalThis.fetch=original;}
});
