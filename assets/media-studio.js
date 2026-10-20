(()=>{
const root=document.querySelector('.media-studio');if(!root)return;
const cards=[...root.querySelectorAll('.studio-card')],date=root.querySelector('#media-calendar'),select=root.querySelector('#media-session'),buttons=[...root.querySelectorAll('[data-media-type]')],more=root.querySelector('#media-more'),status=root.querySelector('#media-status'),empty=root.querySelector('#media-empty');
const titles={'2026-10-17':"Saturday's training & welcome friendly",'2026-10-15':'Thursday training','2026-10-13':'Tuesday training','2026-10-10':'Our first training session'};
let selected='2026-10-17',type='all',limit=6;
const longDate=d=>new Date(d+'T12:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'});

let activeVideo=null;
function stopVideo(){if(!activeVideo)return;const {button,frame}=activeVideo;frame.remove();button.hidden=false;activeVideo=null;}
root.addEventListener('click',e=>{
const button=e.target.closest('[data-video-id]');if(!button)return;
const id=button.dataset.videoId;if(!/^[A-Za-z0-9_-]{11}$/.test(id))return;
stopVideo();
const frame=document.createElement('iframe');
frame.className='studio-inline-video';
frame.title=button.closest('.studio-card').querySelector('h3').textContent;
frame.src='https://www.youtube-nocookie.com/embed/'+id+'?autoplay=1&playsinline=1&rel=0';
frame.allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
frame.allowFullscreen=true;frame.referrerPolicy='strict-origin-when-cross-origin';
button.hidden=true;button.after(frame);activeVideo={button,frame};frame.focus();
});
window.addEventListener('hashchange',stopVideo);
document.addEventListener('click',e=>{if(e.target.closest('[data-route]'))stopVideo();});

function render(){if(activeVideo)stopVideo();const found=cards.filter(c=>c.dataset.date===selected&&(type==='all'||c.dataset.kind===type));cards.forEach(c=>c.hidden=true);found.slice(0,limit).forEach(c=>c.hidden=false);more.hidden=found.length<=limit;empty.hidden=found.length>0;date.value=selected;select.value=titles[selected]?selected:'';buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mediaType===type)));root.querySelector('#media-event-title').textContent=titles[selected]||'No collection for this date';root.querySelector('#media-event-date').textContent=longDate(selected);root.querySelector('#media-score').hidden=selected!=='2026-10-17';status.textContent=`Showing ${Math.min(limit,found.length)} of ${found.length} ${type==='all'?'photos and videos':type==='photo'?'photos':'videos'} · ${longDate(selected)}`;}
function updateURL(){const u=new URL(location.href);u.searchParams.set('date',selected);u.searchParams.set('type',type);u.hash='media';history.replaceState(null,'',u);}
date.addEventListener('change',()=>{if(!date.value)return;selected=date.value;limit=6;render();updateURL()});select.addEventListener('change',()=>{if(!select.value)return;selected=select.value;limit=6;render();updateURL()});buttons.forEach(b=>b.addEventListener('click',()=>{type=b.dataset.mediaType;limit=6;render();updateURL()}));more.addEventListener('click',()=>{limit+=6;render()});
function fromURL(){const p=new URLSearchParams(location.search);const h=location.hash.slice(1);selected=/^\d{4}-\d{2}-\d{2}$/.test(p.get('date')||'')?p.get('date'):'2026-10-17';type=['all','photo','video'].includes(p.get('type'))?p.get('type'):'all';const dated=h.match(/(?:photos|video|videos)-(2026-\d{2}-\d{2})/);if(dated){selected=dated[1];type=h.includes('video')?'video':'photo'}else if(h==='photos'||(!h&&document.body.dataset.entry==='photos'))type='photo';else if(h==='videos'||(!h&&document.body.dataset.entry==='videos'))type='video';limit=6;render();}window.addEventListener('hashchange',fromURL);fromURL();
const viewer=document.getElementById('training-photo-viewer'),large=document.getElementById('training-photo-large');let photoLinks=[],current=0;
function show(i){current=(i+photoLinks.length)%photoLinks.length;const a=photoLinks[current];large.src=a.href;large.alt=a.querySelector('img').alt;document.getElementById('training-photo-caption').textContent=a.dataset.caption;document.getElementById('training-photo-counter').textContent=`Photo ${current+1} of ${photoLinks.length} · ${longDate(selected)}`;}
root.addEventListener('click',e=>{const a=e.target.closest('[data-training-photo]');if(!a||e.ctrlKey||e.metaKey||e.shiftKey||typeof viewer.showModal!=='function')return;e.preventDefault();photoLinks=cards.filter(c=>c.dataset.date===selected&&c.dataset.kind==='photo').map(c=>c.querySelector('[data-training-photo]'));show(photoLinks.indexOf(a));viewer.showModal();document.body.classList.add('photo-viewer-open')});document.getElementById('training-photo-close').addEventListener('click',()=>viewer.close());document.getElementById('training-photo-prev').addEventListener('click',()=>show(current-1));document.getElementById('training-photo-next').addEventListener('click',()=>show(current+1));viewer.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'){e.preventDefault();show(current-1)}if(e.key==='ArrowRight'){e.preventDefault();show(current+1)}});viewer.addEventListener('close',()=>document.body.classList.remove('photo-viewer-open'));window.addEventListener('hashchange',()=>{if(viewer.open)viewer.close()});
})();