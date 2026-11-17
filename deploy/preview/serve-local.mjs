// Local-only rehearsal of the exact Worker, using allowlisted files from disk.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve,sep} from 'node:path';
import {createPreviewWorker} from './worker.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const manifest=JSON.parse(await readFile(new URL('./public/manifest.json',import.meta.url),'utf8'));
const revision='0'.repeat(40);
const worker=createPreviewWorker(manifest,revision);
globalThis.fetch=async url=>{
  const expected=`https://raw.githubusercontent.com/4mirgr/Clinic/${revision}/`;
  if(!url.startsWith(expected)) throw new Error('Unexpected preview source');
  const path=resolve(root,url.slice(expected.length));
  if(!path.startsWith(resolve(root)+sep)) throw new Error('Unexpected source path');
  return new Response(await readFile(path));
};
const server=createServer(async(req,res)=>{
  try{
    const request=new Request('https://drgerami-md.ir'+req.url,{method:req.method});
    const response=await worker.fetch(request,{},{});
    res.writeHead(response.status,Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  }catch{res.writeHead(500);res.end('Preview rehearsal failed');}
});
server.listen(Number(process.argv[2]||8766),'127.0.0.1',()=>console.log('Preview rehearsal listening'));
