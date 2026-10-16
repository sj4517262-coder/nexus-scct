const {chromium}=require('@playwright/test');
const {pathToFileURL}=require('url');
const path=require('path');
const fs=require('fs');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const output=path.join(root,'output/pdf/NEXUS_Interview_Handbook.pdf');
  fs.mkdirSync(path.dirname(output),{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage();
  await page.goto(pathToFileURL(path.join(root,'docs/NEXUS_Interview_Handbook.html')).href);
  await page.evaluate(()=>{
    const toc=document.createElement('section'); toc.className='pdf-toc'; toc.id='contents';
    const heading=document.createElement('h2');heading.textContent='Contents';toc.append(heading);
    const intro=document.createElement('p');intro.textContent='Click a chapter title to jump to it. All interview answers are expanded in this edition.';toc.append(intro);
    const list=document.createElement('div');list.className='pdf-toc-links';
    document.querySelectorAll('nav a').forEach(a=>{const copy=a.cloneNode(true);copy.removeAttribute('hidden');list.append(copy)});toc.append(list);
    document.querySelector('.cover').after(toc);
    document.querySelectorAll('.chapter').forEach(ch=>{const a=document.createElement('a');a.href='#contents';a.className='back-to-contents';a.textContent='Back to contents';ch.querySelector('h2').after(a)});
    document.querySelectorAll('details').forEach(d=>d.open=true);
    document.querySelectorAll('main code').forEach(code=>{const value=code.textContent.trim();if(/^https?:\/\/\S+$/.test(value)){const a=document.createElement('a');a.href=value;a.textContent=value;code.replaceWith(a)}});
    document.querySelector('.cover-note').textContent='PDF study edition with clickable contents and links. Read the explanations, practice the exercises, and rehearse the project demonstration. Interactive browser-only controls are available in the HTML edition.';
    const walker=document.createTreeWalker(document.querySelector('main'),NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode())node.textContent=node.textContent.replace(/[\u2010-\u2015]/g,'-');
  });
  await page.addStyleTag({content:`@media print {
    .pdf-toc{break-before:page;break-after:page}.pdf-toc-links a{display:block;font:10pt/1.35 'Segoe UI',sans-serif;padding:3.5pt 0;color:#08756e}
    .back-to-contents{display:block;font:8pt/1.2 'Segoe UI',sans-serif;margin:-9pt 0 18pt;color:#08756e}
    h2{margin-top:0}table{table-layout:auto;width:100%}td,th{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;break-inside:auto}
    details.qa{break-inside:auto}details.qa summary{break-after:avoid}a{color:#08756e}
    [id^="section-12-"],[id^="section-16-"]{font-size:10pt;line-height:1.4}
  }`});
  await page.pdf({path:output,format:'A4',printBackground:true,preferCSSPageSize:true,displayHeaderFooter:true,headerTemplate:'<span></span>',footerTemplate:'<div style="font-family:Arial;font-size:8px;color:#60717b;width:100%;margin:0 16mm;display:flex;justify-content:space-between"><span>NEXUS · Project Interview Handbook</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',tagged:true,outline:true});
  await browser.close();console.log(output);
})().catch(e=>{console.error(e);process.exit(1)});
