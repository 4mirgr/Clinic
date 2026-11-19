// Real website identity; synthetic read-only clinic content. No medical backend.
const SITE='https://drgerami-md.ir';
const cookieValue=(request,name)=>request.headers.get('Cookie')?.split(';').map(v=>v.trim()).find(v=>v.startsWith(name+'='))?.slice(name.length+1)||'';
const redirect=location=>new Response(null,{status:302,headers:{Location:location,'Cache-Control':'private, no-store',Vary:'Cookie','Referrer-Policy':'same-origin'}});
export function withAccountEntry(preview,manifest){
 return {async fetch(request,env,ctx){
  const path=new URL(request.url).pathname;
  if(!['GET','HEAD'].includes(request.method)||!(path==='/clinic'||path.startsWith('/clinic/')))return preview.fetch(request,env,ctx);
  const login=SITE+'/pages/account.html?next='+encodeURIComponent(path.startsWith('/clinic/portal/')?'/clinic/portal/':'/clinic/');
  if(/^\/clinic\/(?:account|login)(?:\/|$)/.test(path))return redirect(new URL(request.url).searchParams.has('manage')?SITE+'/pages/account.html':login);
  const asset=manifest[path];
  // Shared static images/PDFs are synthetic, and continue through the pinned
  // public allowlist. Every HTML route gets a fresh server-side role check.
  if(path!=='/clinic'&&!asset?.type?.startsWith('text/html'))return preview.fetch(request,env,ctx);
  const token=cookieValue(request,'__Host-gerami-access');
  if(!token||token.length>3800||!/^[A-Za-z0-9_.-]+$/.test(token))return redirect(login);
  let response,value;
  try{
   response=await fetch(SITE+'/api/account/session',{headers:{Cookie:'__Host-gerami-access='+token,Accept:'application/json','Cache-Control':'no-store'},redirect:'manual',signal:AbortSignal.timeout(10000)});
   if(response.status===401)return redirect(login);
   if(!response.ok)throw Error('identity unavailable');
   const raw=await response.text();if(raw.length>16384)throw Error('invalid identity');value=JSON.parse(raw);
  }catch{return new Response('ورود موقتاً در دسترس نیست؛ صفحه را دوباره باز کنید. / Sign-in is temporarily unavailable. Please retry.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'private, no-store',Vary:'Cookie'}});}
  if(value.authenticated!==true||!['admin','secretary','user'].includes(value.account?.role))return redirect(login);
  const staff=value.account.role==='admin'||value.account.role==='secretary';
  if(!staff&&!path.startsWith('/clinic/portal/'))return redirect('/clinic/portal/');
  if(staff&&path.startsWith('/clinic/portal/'))return redirect('/clinic/');
  const result=await preview.fetch(request,env,ctx),headers=new Headers(result.headers);
  headers.set('Cache-Control','private, no-store');headers.set('Vary','Cookie');headers.set('X-Clinic-Identity','shared');
  return new Response(result.body,{status:result.status,headers});
 }};
}
