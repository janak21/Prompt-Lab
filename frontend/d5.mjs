import { chromium } from 'playwright';
const b = await chromium.launch(); const p = await b.newPage();
p.on('response', r => { if(r.status()>=400) console.log(r.status(), r.url()); });
await p.goto('http://localhost:8077/prompts',{waitUntil:'networkidle'});
await b.close();
