// Optional path proxy for an existing Cloudflare-managed website.
// Django still needs its own Python/container host; this Worker is not that host.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/dash' && !url.pathname.startsWith('/dash/')) {
      return new Response('Not found', {status: 404});
    }
    let origin;
    try {
      origin = new URL(env.ORIGIN_URL);
      if (origin.protocol !== 'https:' || origin.origin === url.origin || !env.CLINIC_PROXY_KEY || env.CLINIC_PROXY_KEY.length < 32) throw new Error();
    } catch {
      return new Response('Service not configured', {status: 503, headers: {'Cache-Control': 'no-store'}});
    }
    const target = new URL(url.pathname + url.search, origin.origin);
    const headers = new Headers(request.headers);
    headers.set('Host', target.host);
    headers.set('X-Forwarded-Proto', 'https');
    headers.set('X-Clinic-Proxy-Key', env.CLINIC_PROXY_KEY);
    try {
      const upstreamRequest = new Request(target, {...request, method: request.method, headers, body: ['GET','HEAD'].includes(request.method) ? undefined : request.body, redirect: 'manual', duplex: 'half'});
      const upstream = await fetch(upstreamRequest, {cf: {cacheEverything: false, cacheTtl: 0}});
      const response = new Response(upstream.body, upstream);
      response.headers.set('Cache-Control', 'private, no-store, max-age=0');
      const location = response.headers.get('Location');
      if (location) {
        const destination = new URL(location, target);
        if (destination.origin === origin.origin && /^https?:/.test(location)) {
          response.headers.set('Location', url.origin + destination.pathname + destination.search + destination.hash);
        }
      }
      return response;
    } catch {
      return new Response('Service temporarily unavailable', {status: 502, headers: {'Cache-Control': 'no-store'}});
    }
  }
};
