import assert from 'node:assert/strict';
import {test} from 'node:test';
import worker from './worker.mjs';

const env={ORIGIN_URL:'https://clinic-origin.example',CLINIC_PROXY_KEY:'origin-test-secret-32-characters-long'};
test('only dash paths are proxied, missing config fails closed',async()=>{
  assert.equal((await worker.fetch(new Request('https://drgerami-md.ir/'),env)).status,404);
  assert.equal((await worker.fetch(new Request('https://drgerami-md.ir/dashboard'),env)).status,404);
  assert.equal((await worker.fetch(new Request('https://drgerami-md.ir/dash/'),{})).status,503);
});
test('POST body, cookies and URL are preserved; spoofed proxy headers replaced; redirects not followed',async()=>{
  const realFetch=globalThis.fetch;
  globalThis.fetch=async(request,options)=>{
    assert.equal(request.url,'https://clinic-origin.example/dash/login/manager/?next=%2Fdash%2F');
    assert.equal(request.headers.get('X-Forwarded-Proto'),'https');
    assert.equal(request.headers.get('X-Clinic-Proxy-Key'),env.CLINIC_PROXY_KEY);
    assert.equal(request.headers.get('cookie'),'gerami_session=test-session');
    assert.equal(await request.text(),'username=test-user');
    assert.equal(request.redirect,'manual');
    assert.equal(options.cf.cacheEverything,false);
    return new Response(null,{status:302,headers:{Location:'/dash/','Set-Cookie':'gerami_session=new; Path=/dash/; Secure; HttpOnly'}});
  };
  try{
    const response=await worker.fetch(new Request('https://drgerami-md.ir/dash/login/manager/?next=%2Fdash%2F',{method:'POST',body:'username=test-user',headers:{cookie:'gerami_session=test-session','X-Forwarded-Proto':'http','X-Clinic-Proxy-Key':'spoofed'}}),env);
    assert.equal(response.status,302);
    assert.equal(response.headers.get('Location'),'/dash/');
    assert.match(response.headers.get('Set-Cookie'),/Path=\/dash\//);
    assert.match(response.headers.get('Cache-Control'),/no-store/);
  }finally{globalThis.fetch=realFetch;}
});
test('upstream error does not expose origin configuration',async()=>{
  const realFetch=globalThis.fetch;
  globalThis.fetch=async()=>{throw new Error('sensitive upstream failure');};
  try{
    const response=await worker.fetch(new Request('https://drgerami-md.ir/dash/'),env);
    assert.equal(response.status,502);
    assert.doesNotMatch(await response.text(),/sensitive|clinic-origin/);
  }finally{globalThis.fetch=realFetch;}
});
