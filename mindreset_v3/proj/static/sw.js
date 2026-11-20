const CACHE='mindreset-v3';
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/','/static/icon.svg','/manifest.webmanifest'])))});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
// Red primero; la caché solo sirve la interfaz sin conexión. Nunca se guardan respuestas de /api (datos sensibles).
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.pathname.startsWith('/api/')||u.pathname==='/health')return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});
