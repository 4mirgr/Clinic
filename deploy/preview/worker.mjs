// This serves a finite, synthetic snapshot. It has no patient API or credentials.
export function createPreviewWorker(manifest, revision) {
  if (!/^[a-f0-9]{40}$/.test(revision)) throw new Error('An exact source commit is required');
  const headersFor = type => ({
    'Content-Type':type, 'Cache-Control':type.startsWith('text/html')?'no-store':'public, max-age=300',
    'X-Clinic-Preview':'read-only', 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY',
    'X-Robots-Tag':'noindex, nofollow', 'Referrer-Policy':'same-origin',
    'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; form-action 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  });
  return {
    async fetch(request, env, ctx) {
      const url = new URL(request.url);
      if (url.pathname !== '/clinic' && !url.pathname.startsWith('/clinic/')) return new Response('Not found',{status:404});
      if (!['GET','HEAD'].includes(request.method)) return new Response('Read-only design preview',{status:405,headers:{Allow:'GET, HEAD','Cache-Control':'no-store'}});
      if (url.pathname === '/clinic') return new Response(null,{status:302,headers:{Location:'/clinic/'+url.search,'Cache-Control':'no-store'}});
      const asset = Object.hasOwn(manifest,url.pathname) ? manifest[url.pathname] : null;
      if (!asset) return new Response('This page is not part of the read-only preview',{status:404,headers:headersFor('text/plain; charset=utf-8')});
      const cache = globalThis.caches?.default;
      const key = new Request(`https://drgerami-md.ir/clinic/__snapshot/${revision}${url.pathname}`);
      let source = await cache?.match(key);
      if (!source) {
        try {
          source = await fetch(`https://raw.githubusercontent.com/4mirgr/Clinic/${revision}/${asset.path}`,{redirect:'manual'});
          if (!source.ok) throw new Error('Snapshot source unavailable');
          source = new Response(source.body,{headers:{'Content-Type':asset.type,'Cache-Control':'public, max-age=86400'}});
          if (cache && ctx.waitUntil) ctx.waitUntil(cache.put(key,source.clone()));
        } catch {
          return new Response('Preview temporarily unavailable',{status:502,headers:{'Cache-Control':'no-store'}});
        }
      }
      return new Response(request.method==='HEAD'?null:source.body,{headers:headersFor(asset.type)});
    },
  };
}
