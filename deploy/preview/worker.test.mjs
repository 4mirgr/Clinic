import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createPreviewWorker} from './worker.mjs';

const revision='a'.repeat(40);
const manifest={'/clinic/':{path:'deploy/preview/public/dashboard.html',type:'text/html; charset=utf-8'}};

test('preview serves only allowlisted GET/HEAD paths and never forwards submitted data',async()=>{
  const worker=createPreviewWorker(manifest,revision);
  assert.equal((await worker.fetch(new Request('https://drgerami-md.ir/clinic',{method:'POST',body:'private'}),{},{})).status,405);
  for(const path of ['/','/admin/','/clinical','/clinic/api/portal/profile','/clinic/.env']){
    assert.equal((await worker.fetch(new Request('https://drgerami-md.ir'+path),{},{})).status,404);
  }
  const redirect=await worker.fetch(new Request('https://drgerami-md.ir/clinic?v=1'),{},{});
  assert.equal(redirect.headers.get('Location'),'/clinic/?v=1');
});

test('source is pinned to one commit and upstream cookies are never returned',async()=>{
  const worker=createPreviewWorker(manifest,revision);
  const original=globalThis.fetch;
  globalThis.fetch=async request=>{
    assert.equal(request,`https://raw.githubusercontent.com/4mirgr/Clinic/${revision}/deploy/preview/public/dashboard.html`);
    return new Response('<html>synthetic preview</html>',{headers:{'Set-Cookie':'upstream=never-forward'}});
  };
  try{
    const response=await worker.fetch(new Request('https://drgerami-md.ir/clinic/'),{},{});
    assert.equal(response.status,200);
    assert.equal(response.headers.get('Set-Cookie'),null);
    assert.equal(response.headers.get('X-Clinic-Preview'),'read-only');
    assert.match(response.headers.get('Content-Security-Policy'),/connect-src 'none'/);
    assert.match(await response.text(),/synthetic preview/);
  }finally{globalThis.fetch=original;}
});
