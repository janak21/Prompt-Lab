import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage();
p.on('pageerror',e=>console.log('[PAGEERROR]', String(e.stack||e).slice(0,500)));
await p.goto('http://localhost:5173/prompts',{waitUntil:'networkidle'});
const r = await p.evaluate(async () => {
  const out = {};
  try { const m = await import('/src/App.tsx'); out.App = typeof m.default; } catch(e){ out.AppErr = String(e).slice(0,300); }
  try { const m = await import('/src/components/AppShell.tsx'); out.AppShell = typeof m.AppShell; } catch(e){ out.ShellErr = String(e).slice(0,300); }
  try { const m = await import('/src/lib/api.ts'); out.api = typeof m.api; out.MOCK = m.MOCK_MODE; } catch(e){ out.apiErr = String(e).slice(0,300); }
  try { const m = await import('/src/pages/Prompts.tsx'); out.PromptsPage = typeof m.PromptsPage; } catch(e){ out.pagesErr = String(e).slice(0,300); }
  out.rootKids = document.getElementById('root')?.childElementCount;
  return out;
});
console.log(JSON.stringify(r,null,2));
await b.close();
