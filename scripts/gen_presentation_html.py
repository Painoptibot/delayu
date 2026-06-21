"""Generate DelaYu presentation HTML (RU + EN)."""
from pathlib import Path

from presentation_locales import CONTENT, LOCALE_META

ROOT = Path(__file__).resolve().parents[1] / "docs" / "presentation"
HERO = "assets/img/hero"


def feat(icon, title, body):
    return (
        f'<li><span class="ico"><i data-lucide="{icon}"></i></span>'
        f"<div><strong>{title}</strong>{body}</div></li>"
    )


def impl_card(title, code, done, meta):
    tag = (
        f'<span class="tag tag-ok">{meta["tag_ok"]}</span>'
        if done
        else f'<span class="tag tag-plan">{meta["tag_plan"]}</span>'
    )
    return f'<div class="glass impl"><strong>{title}</strong><small>{code}</small>{tag}</div>'


def int_row(name, desc, done=True):
    icon = "circle-check-big" if done else "clock"
    cls = "int-done" if done else "int-plan"
    return (
        f'<li class="{cls} glass"><span class="ico ico-sm">'
        f'<i data-lucide="{icon}"></i></span><div><strong>{name}</strong><span>{desc}</span></div></li>'
    )


def img_hero(name, cls="hero"):
    return f'<img src="{HERO}/{name}" class="{cls}" alt="" loading="lazy" />'


def img_shot(name, cls="shot"):
    return f'<img src="assets/screenshots/{name}" class="{cls}" alt="" loading="lazy" />'


CSS = """
:root {
  --primary:#696cff; --primary-2:#9055fd; --accent:#03c3ec;
  --text:#1a2332; --muted:#4a5c6e;
  --glass:rgba(255,255,255,.88); --glass-border:rgba(210,218,230,.85);
  --shadow:0 20px 50px rgba(38,43,67,.12);
  --slide-bg:rgba(248,250,252,.84);
  --slide-bg-solid:linear-gradient(165deg,#ffffff 0%,#f8f9fc 48%,#f1f4f8 100%);
  --font:'Roboto',-apple-system,BlinkMacSystemFont,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:var(--font);color:var(--text);background:#0b1020;overflow:hidden}
.bg-live{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
#bg-canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.bg-spotlight{position:absolute;width:min(55vw,620px);height:min(55vw,620px);border-radius:50%;left:50%;top:50%;transform:translate(-50%,-50%);background:radial-gradient(circle,rgba(105,108,255,.28) 0%,rgba(144,85,253,.12) 38%,transparent 72%);filter:blur(8px);will-change:left,top}
.bg-aurora{position:absolute;inset:-20%;background:conic-gradient(from 180deg at 50% 50%,rgba(105,108,255,.22),rgba(3,195,236,.16),rgba(144,85,253,.2),rgba(105,108,255,.22));animation:auroraSpin 26s linear infinite;opacity:.85}
@keyframes auroraSpin{to{transform:rotate(360deg)}}
.bg-live .orb{position:absolute;border-radius:50%;filter:blur(70px);opacity:.62;will-change:transform;transition:transform .35s cubic-bezier(.2,.8,.2,1)}
.bg-live .orb-1{width:460px;height:460px;background:#696cff;top:-100px;left:-80px}
.bg-live .orb-2{width:380px;height:380px;background:#9055fd;bottom:-60px;right:8%}
.bg-live .orb-3{width:300px;height:300px;background:#03c3ec;top:38%;right:-90px}
.bg-live .grid-mesh{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.055) 1px,transparent 1px);background-size:44px 44px;mask-image:radial-gradient(ellipse at 50% 45%,black 10%,transparent 78%);animation:meshDrift 24s linear infinite}
@keyframes meshDrift{0%{transform:translate(0,0)}50%{transform:translate(-22px,-22px)}100%{transform:translate(0,0)}}
.deck{position:relative;z-index:1;height:100vh;overflow:hidden}
.slide{position:absolute;inset:0;display:none;padding:36px 52px 78px;overflow:auto;color:var(--text)}
.slide:not(.slide--cover){background:var(--slide-bg);border:1px solid rgba(255,255,255,.5);box-shadow:0 0 0 1px rgba(210,218,230,.3),0 24px 60px rgba(15,18,36,.08)}
.slide.active{display:flex;flex-direction:column}
.slide.active.is-entering{animation:slideIn .4s cubic-bezier(.2,.8,.2,1)}
@keyframes slideIn{from{transform:translateY(14px) scale(.99)}to{transform:none}}
.slide--cover{color:#fff;text-align:center;justify-content:center;align-items:center;background:transparent!important;border:none;box-shadow:none!important}
.slide--cover::before{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(105,108,255,.72),rgba(144,85,253,.68) 50%,rgba(3,195,236,.58));z-index:-1}
.slide--cover>*{position:relative;z-index:1}
.slide--cover h1{font-size:clamp(2.2rem,4.5vw,3.4rem);font-weight:900;margin:14px 0 8px;text-shadow:0 4px 24px rgba(0,0,0,.2);font-family:var(--font)}
.slide--cover p{font-size:1.1rem;opacity:.95;max-width:760px;line-height:1.5;font-weight:400}
.slide--cover .meta{margin-top:18px;font-size:.92rem;opacity:.88}
.logo{height:60px;filter:brightness(0) invert(1)}
.glass{background:var(--glass);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--glass-border);border-radius:16px;box-shadow:var(--shadow)}
.header{margin-bottom:18px;flex-shrink:0;padding:14px 18px}
.header:not(.header--plain){background:var(--glass);border:1px solid var(--glass-border);border-radius:16px;box-shadow:var(--shadow)}
.header h2{font-size:1.6rem;font-weight:900;background:linear-gradient(90deg,var(--primary),var(--primary-2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-family:var(--font)}
.header p{color:var(--muted);font-size:.88rem;margin-top:4px;font-weight:400}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:22px;flex:1;align-items:start}
@media(max-width:1100px){.grid-2{grid-template-columns:1fr}}
.hero,.shot{width:100%;border-radius:18px;box-shadow:var(--shadow);border:1px solid rgba(255,255,255,.35)}
.hero{object-fit:cover;max-height:420px}
.shot{object-fit:cover;object-position:top left}
.shot-sm{max-height:200px;width:100%}
.shot-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}
.shot-row figcaption{font-size:.68rem;color:var(--muted);margin-top:4px;text-align:center;font-weight:500}
ul.features{list-style:none;display:flex;flex-direction:column;gap:9px}
ul.features li{display:flex;gap:12px;padding:12px 14px;font-size:.9rem;line-height:1.4;background:var(--glass);border:1px solid var(--glass-border);border-radius:14px;box-shadow:0 2px 10px rgba(38,43,67,.06)}
.ico,.ico-sm{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;border-radius:14px;background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;box-shadow:0 8px 20px rgba(105,108,255,.35)}
.ico{width:44px;height:44px}
.ico-sm{width:36px;height:36px;border-radius:12px}
.ico svg,.ico-sm svg{width:22px;height:22px;stroke-width:2}
ul.features li strong{display:block;margin-bottom:2px;color:var(--text);font-weight:700}
.impl-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}
@media(max-width:1200px){.impl-grid{grid-template-columns:repeat(2,1fr)}}
.impl{padding:11px;font-size:.8rem;line-height:1.35}
.impl strong{display:block;margin-bottom:3px;font-size:.85rem;font-weight:700}
.impl small{color:var(--muted);display:block;margin-bottom:5px;font-weight:400}
.tag{display:inline-block;border-radius:999px;font-size:.62rem;font-weight:700;padding:3px 9px;margin:2px;font-family:var(--font)}
.tag-ok{background:rgba(113,221,55,.2);color:#3d9e00}
.tag-plan{background:rgba(255,171,0,.2);color:#a67c00}
.tag-chip{background:rgba(105,108,255,.12);color:var(--primary);padding:5px 11px;font-size:.72rem}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0}
.stat{padding:14px 22px;text-align:center;min-width:96px}
.stat b{display:block;font-size:1.6rem;font-weight:900;background:linear-gradient(90deg,var(--primary),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat span{font-size:.72rem;color:var(--muted);font-weight:500}
.int-list{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:.84rem}
.int-list li{display:flex;gap:10px;padding:10px 12px;align-items:flex-start}
.int-list strong{display:block;font-size:.86rem;font-weight:700}
.int-list span{color:var(--muted);font-size:.76rem;font-weight:400}
.int-done .ico-sm{background:linear-gradient(135deg,#71dd37,#49AC00)}
.int-plan .ico-sm{background:linear-gradient(135deg,#ffab00,#ff9f43)}
.tech-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:11px}
.tech{padding:14px}
.tech .ico{width:40px;height:40px;margin-bottom:8px}
.tech h4{font-size:.92rem;margin-bottom:5px;font-weight:700}
.tech p{font-size:.76rem;color:var(--muted);line-height:1.35;font-weight:400}
.devops{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.lead{font-size:.98rem;line-height:1.55;color:var(--muted);margin-bottom:12px;font-weight:400}
.btn-dl{display:inline-flex;align-items:center;gap:10px;margin:10px 8px;padding:14px 28px;border-radius:14px;font-weight:700;font-size:1rem;text-decoration:none;color:#fff;background:linear-gradient(135deg,#fff,rgba(255,255,255,.85));color:var(--primary);box-shadow:0 12px 32px rgba(0,0,0,.2);transition:transform .2s,box-shadow .2s;font-family:var(--font)}
.btn-dl:hover{transform:translateY(-2px);box-shadow:0 16px 40px rgba(0,0,0,.28)}
.btn-dl--ghost{background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.35)}
.btn-dl svg{width:20px;height:20px}
.dl-box{margin-top:24px;padding:20px 28px;border-radius:20px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);backdrop-filter:blur(12px)}
.lang-switch{position:fixed;top:14px;right:18px;z-index:120}
.lang-switch a{display:inline-flex;align-items:center;gap:8px;padding:8px 14px;border-radius:999px;text-decoration:none;font-size:.82rem;font-weight:500;color:#fff;background:rgba(15,18,36,.75);border:1px solid rgba(255,255,255,.15);backdrop-filter:blur(10px);font-family:var(--font)}
.lang-switch a:hover{background:rgba(105,108,255,.85)}
.nav{position:fixed;bottom:0;left:0;right:0;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:10px 20px;background:rgba(15,18,36,.88);color:#fff;backdrop-filter:blur(14px);border-top:1px solid rgba(255,255,255,.08);font-family:var(--font)}
.nav button{background:linear-gradient(135deg,var(--primary),var(--primary-2));border:none;color:#fff;padding:9px 18px;border-radius:10px;cursor:pointer;font-weight:500;font-family:var(--font)}
.nav button:disabled{opacity:.35;cursor:default}
.dots{display:flex;gap:5px;flex-wrap:wrap;justify-content:center;max-width:55%}
.dots button{width:8px;height:8px;border-radius:50%;border:none;background:rgba(255,255,255,.25);cursor:pointer;padding:0;transition:transform .2s,background .2s}
.dots button.active{background:var(--accent);transform:scale(1.35)}
.counter{font-size:.8rem;opacity:.85;min-width:72px;text-align:center;font-weight:400}
body.pdf-export,body.pdf-export html{overflow:visible!important;height:auto!important;background:#fff!important}
body.pdf-export .bg-live,body.pdf-export .nav,body.pdf-export .lang-switch{display:none!important}
body.pdf-export .deck{position:static!important;height:auto!important;overflow:visible!important}
body.pdf-export .slide{position:relative!important;inset:auto!important;top:auto!important;left:auto!important;right:auto!important;bottom:auto!important;display:flex!important;flex-direction:column!important;opacity:1!important;visibility:visible!important;animation:none!important;transform:none!important;page-break-after:always;break-after:page;break-inside:avoid;min-height:100vh;width:100%;padding:28px 40px 32px;box-sizing:border-box;background:var(--slide-bg-solid)!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;border:none!important;box-shadow:none!important}
body.pdf-export .slide--cover::before{display:block}
body.pdf-export .slide:last-child{page-break-after:auto;break-after:auto}
@media print{html,body{overflow:visible!important;height:auto!important;background:#fff!important}.nav,.bg-live,.lang-switch{display:none!important}.deck{position:static!important;height:auto!important;overflow:visible!important}.slide{position:relative!important;inset:auto!important;display:flex!important;flex-direction:column!important;page-break-after:always;break-after:page;break-inside:avoid;min-height:100vh;width:100%;padding:28px 40px 32px;animation:none!important;background:var(--slide-bg-solid)!important;backdrop-filter:none!important}.slide:last-child{page-break-after:auto}}
@media (prefers-reduced-motion:reduce){.bg-aurora,.bg-live .grid-mesh,.bg-live .orb{animation:none!important}}
"""

BG_SCRIPT = """
(function(){
  const canvas=document.getElementById('bg-canvas');
  if(!canvas)return;
  const ctx=canvas.getContext('2d');
  const spotlight=document.querySelector('.bg-spotlight');
  const orbs=[...document.querySelectorAll('.bg-live .orb')];
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w=0,h=0,mx=0,my=0,px=0,py=0,t=0;
  const particles=[];
  const COUNT= reduced ? 36 : 72;
  const LINK= reduced ? 100 : 130;

  function resize(){
    w=canvas.width=window.innerWidth;
    h=canvas.height=window.innerHeight;
    px=mx=w/2; py=my=h/2;
  }

  function seed(){
    particles.length=0;
    for(let i=0;i<COUNT;i++){
      particles.push({
        x:Math.random()*w,
        y:Math.random()*h,
        vx:(Math.random()-.5)*.45,
        vy:(Math.random()-.5)*.45,
        r:Math.random()*1.8+1
      });
    }
  }

  window.addEventListener('resize',()=>{resize();seed();});
  document.addEventListener('mousemove',e=>{mx=e.clientX;my=e.clientY;});
  document.addEventListener('touchmove',e=>{if(e.touches[0]){mx=e.touches[0].clientX;my=e.touches[0].clientY;}},{passive:true});

  function draw(){
    t+=0.008;
    px+=(mx-px)*0.09;
    py+=(my-py)*0.09;
    if(spotlight){
      spotlight.style.left=px+'px';
      spotlight.style.top=py+'px';
    }
    orbs.forEach((orb,i)=>{
      const k=.028+i*.012;
      orb.style.transform='translate('+(px-w/2)*k+'px,'+(py-h/2)*k+'px) scale('+(1+Math.sin(t+i)*.04)+')';
    });

    ctx.clearRect(0,0,w,h);
    for(const p of particles){
      if(!reduced){
        const dx=px-p.x, dy=py-p.y, dist=Math.hypot(dx,dy)||1;
        if(dist<180){ p.vx+=dx/dist*.018; p.vy+=dy/dist*.018; }
        p.vx+=(Math.random()-.5)*.004;
        p.vy+=(Math.random()-.5)*.004;
        p.vx*=.985; p.vy*=.985;
        p.x+=p.vx; p.y+=p.vy;
        if(p.x<0||p.x>w)p.vx*=-1;
        if(p.y<0||p.y>h)p.vy*=-1;
        p.x=Math.max(0,Math.min(w,p.x));
        p.y=Math.max(0,Math.min(h,p.y));
      }
      ctx.beginPath();
      ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle='rgba(105,108,255,.55)';
      ctx.fill();
    }
    for(let i=0;i<particles.length;i++){
      for(let j=i+1;j<particles.length;j++){
        const a=particles[i], b=particles[j];
        const d=Math.hypot(a.x-b.x,a.y-b.y);
        if(d<LINK){
          ctx.strokeStyle='rgba(3,195,236,'+(1-d/LINK)*.28+')';
          ctx.lineWidth=1;
          ctx.beginPath();
          ctx.moveTo(a.x,a.y);
          ctx.lineTo(b.x,b.y);
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }

  resize(); seed(); draw();
})();
"""


def build_html(locale: str) -> str:
    meta = LOCALE_META[locale]
    data = CONTENT[locale]
    slides = data["slides"]
    brand = meta["brand"]

    cover = slides["cover"]
    about = slides["about"]
    pains = slides["pains"]
    solution = slides["solution"]
    gallery = slides["gallery"]
    ai = slides["ai"]
    int_done = slides["int_done"]
    int_road = slides["int_road"]
    uzhv = slides["uzhv"]
    studio = slides["studio"]
    tech = slides["tech"]
    download = slides["download"]

    solution_items = "".join(
        feat(icon, title, body)
        for icon, (title, body) in zip(data["solution_icons"], solution[3])
    )

    html = f'''<!DOCTYPE html>
<html lang="{meta["lang"]}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{meta["doc_title"]}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap" rel="stylesheet" />
  <link rel="icon" href="assets/img/yugit-logo.svg" type="image/svg+xml" />
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
  <style>{CSS}</style>
</head>
<body>
<div class="lang-switch"><a href="{meta["alt_href"]}"><i data-lucide="languages"></i> {meta["alt_label"]}</a></div>
<div class="bg-live" aria-hidden="true">
  <canvas id="bg-canvas"></canvas>
  <div class="bg-aurora"></div>
  <div class="bg-spotlight"></div>
  <div class="grid-mesh"></div>
  <span class="orb orb-1"></span>
  <span class="orb orb-2"></span>
  <span class="orb orb-3"></span>
</div>
<div class="deck" id="deck">
  <section class="slide slide--cover active" data-title="{cover[0]}">
    <img src="assets/img/yugit-logo.svg" alt="{meta["company_alt"]}" class="logo" />
    <h1>{brand}</h1>
    <p>{cover[1]}</p>
    <p class="meta">{cover[2]}</p>
    {img_shot("02-home.png", "shot").replace('class="shot"', 'class="shot" style="max-width:760px;margin-top:18px;border:3px solid rgba(255,255,255,.35)"')}
  </section>
  <section class="slide" data-title="{about[0]}">
    <div class="header"><h2>{about[1]}</h2><p>{about[2]}</p></div>
    <p class="lead glass" style="padding:14px 18px">{about[3]}</p>
    <div class="stats">
      <div class="stat glass"><b>86</b><span>{meta["stat_modules"]}</span></div>
      <div class="stat glass"><b>20</b><span>{meta["stat_scenarios"]}</span></div>
      <div class="stat glass"><b>4</b><span>{meta["stat_configs"]}</span></div>
    </div>
    <div class="impl-grid">{"".join(impl_card(t, c, d, meta) for t, c, d in data["impl"])}</div>
    <div class="shot-row">
      <figure>{img_shot("03-cases.png","shot shot-sm")}<figcaption>{about[4][0]}</figcaption></figure>
      <figure>{img_shot("04-kanban.png","shot shot-sm")}<figcaption>{about[4][1]}</figcaption></figure>
      <figure>{img_hero("hero-solution.png","hero shot-sm")}<figcaption>{about[4][2]}</figcaption></figure>
    </div>
  </section>
  <section class="slide" data-title="{pains[0]}">
    <div class="grid-2">
      <div>
        <div class="header"><h2>{pains[1]}</h2><p>{pains[2]}</p></div>
        <ul class="features">{"".join(feat(i, t, b) for i, t, b in data["pains"])}</ul>
      </div>
      {img_hero("hero-problem.png")}
    </div>
  </section>
  <section class="slide" data-title="{solution[0]}">
    <div class="grid-2">
      {img_hero("hero-solution.png")}
      <div>
        <div class="header"><h2>{solution[1]}</h2><p>{solution[2]}</p></div>
        <ul class="features">{solution_items}</ul>
      </div>
    </div>
  </section>
  <section class="slide" data-title="{gallery[0]}">
    <div class="header"><h2>{gallery[1]}</h2><p>{gallery[2]}</p></div>
    <div class="shot-row" style="grid-template-columns:repeat(4,1fr)">
      {"".join(f'<figure>{img_shot(f,"shot shot-sm")}<figcaption>{c}</figcaption></figure>' for f, c in data["screenshots"][:8])}
    </div>
    <div class="shot-row" style="grid-template-columns:repeat(4,1fr);margin-top:8px">
      {"".join(f'<figure>{img_shot(f,"shot shot-sm")}<figcaption>{c}</figcaption></figure>' for f, c in data["screenshots"][8:])}
    </div>
  </section>
'''

    for title, sub, visual, vtype, items in data["modules"]:
        left = img_hero(visual) if vtype == "hero" else img_shot(visual)
        feats = "".join(feat(i, t, b) for i, t, b in items)
        html += f'''
  <section class="slide" data-title="{title}">
    <div class="grid-2">{left}<div>
      <div class="header"><h2>{title}</h2><p>{sub}</p></div>
      <ul class="features">{feats}</ul>
    </div></div>
  </section>
'''

    html += f'''
  <section class="slide" data-title="{ai[0]}">
    <div class="grid-2">
      <div>
        <div class="header"><h2>{ai[1]}</h2><p>{ai[2]}</p></div>
        <ul class="features">{"".join(feat(i, t, b) for i, t, b in data["ai_feats"])}</ul>
      </div>
      {img_hero("hero-ai.png")}
    </div>
  </section>
  <section class="slide" data-title="{int_done[0]}">
    <div class="header"><h2>{int_done[1]}</h2><p>{int_done[2]}</p></div>
    <div class="grid-2">
      <ul class="int-list">{"".join(int_row(n, d, True) for n, d in data["integrations_done"])}</ul>
      <div>{img_shot("12-integrations.png")}{img_hero("hero-integrations.png","hero shot-sm")}</div>
    </div>
  </section>
  <section class="slide" data-title="{int_road[0]}">
    <div class="grid-2">
      {img_hero("hero-integrations.png")}
      <div>
        <div class="header"><h2>{int_road[1]}</h2><p>{int_road[2]}</p></div>
        <ul class="int-list">{"".join(int_row(n, d, False) for n, d in data["integrations_roadmap"])}</ul>
        <div class="devops" style="margin-top:12px"><span class="tag tag-chip">SMEV</span><span class="tag tag-chip">GIS ZhKKh</span><span class="tag tag-chip">ESIA</span><span class="tag tag-chip">Kafka</span></div>
      </div>
    </div>
  </section>
  <section class="slide" data-title="{uzhv[0]}">
    <div class="grid-2">
      {img_hero("hero-uzhv.png")}
      <div>
        <div class="header"><h2>{uzhv[1]}</h2><p>{uzhv[2]}</p></div>
        <ul class="features">{"".join(feat(i, t, b) for i, t, b in data["uzhv_feats"])}</ul>
      </div>
    </div>
  </section>
  <section class="slide" data-title="{studio[0]}">
    <div class="grid-2">
      {img_shot("11-studio.png")}
      <div>
        <div class="header"><h2>{studio[1]}</h2><p>{studio[2]}</p></div>
        <ul class="features">{"".join(feat(i, t, b) for i, t, b in data["studio_feats"])}</ul>
        {img_hero("hero-security.png","hero shot-sm")}
      </div>
    </div>
  </section>
  <section class="slide" data-title="{tech[0]}">
    <div class="grid-2">
      <div>
        <div class="header"><h2>{tech[1]}</h2><p>{tech[2]}</p></div>
        <div class="tech-grid">{"".join(f'<div class="tech glass"><span class="ico"><i data-lucide="{ic}"></i></span><h4>{n}</h4><p>{d}</p></div>' for n, d, ic in data["tech_stack"])}</div>
        <div class="devops">{"".join(f'<span class="tag tag-chip">{n}: {d}</span>' for n, d in data["devops"])}</div>
        <p class="lead glass" style="padding:12px;margin-top:12px">{tech[3]}</p>
      </div>
      {img_hero("hero-deploy.png")}
    </div>
  </section>
  <section class="slide slide--cover" data-title="{download[0]}">
    <img src="assets/img/yugit-logo.svg" alt="{meta["company_alt"]}" class="logo" style="height:52px" />
    <h1 style="font-size:2rem">{download[1]}</h1>
    <p>{download[2]}</p>
    <div class="dl-box">
      <p style="margin-bottom:14px;opacity:.95">{download[3]}</p>
      <a href="{meta["pdf"]}" class="btn-dl" download="{meta["pdf"]}">
        <i data-lucide="file-down"></i> {meta["dl_pdf"]}
      </a>
      <a href="{meta["html"]}" class="btn-dl btn-dl--ghost">
        <i data-lucide="presentation"></i> {meta["dl_html"]}
      </a>
    </div>
    <p class="meta">{download[4]}</p>
  </section>
</div>
<nav class="nav" aria-label="{meta["nav_aria"]}">
  <button type="button" id="prev">{meta["prev"]}</button>
  <div class="dots" id="dots"></div>
  <span class="counter" id="counter">1 / 1</span>
  <button type="button" id="next">{meta["next"]}</button>
</nav>
<script>
(function(){{
  const slides=[...document.querySelectorAll('.slide')];
  const dotsEl=document.getElementById('dots');
  const counter=document.getElementById('counter');
  const prev=document.getElementById('prev');
  const next=document.getElementById('next');
  const slideWord={meta["slide_word"]!r};
  const brand={brand!r};
  let i=0;
  slides.forEach((_,idx)=>{{const b=document.createElement('button');b.type='button';b.title=slides[idx].dataset.title||(slideWord+' '+(idx+1));b.addEventListener('click',()=>go(idx));dotsEl.appendChild(b);}});
  function syncUi(){{[...dotsEl.children].forEach((d,j)=>d.classList.toggle('active',j===i));counter.textContent=(i+1)+' / '+slides.length;prev.disabled=i===0;next.disabled=i===slides.length-1;document.title=(slides[i].dataset.title||slideWord)+' — '+brand;if(window.lucide)lucide.createIcons();}}
  function go(n,animate){{const next=Math.max(0,Math.min(slides.length-1,n));if(next===i)return;slides[i].classList.remove('active','is-entering');i=next;slides[i].classList.add('active');if(animate!==false){{slides[i].classList.add('is-entering');slides[i].addEventListener('animationend',()=>slides[i].classList.remove('is-entering'),{{once:true}});}}syncUi();}}
  prev.addEventListener('click',()=>go(i-1));next.addEventListener('click',()=>go(i+1));
  document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight'||e.key===' ' ){{e.preventDefault();go(i+1);}}if(e.key==='ArrowLeft'){{e.preventDefault();go(i-1);}}if(e.key==='Home')go(0);if(e.key==='End')go(slides.length-1);}});
  syncUi();
  if(window.lucide)lucide.createIcons();
}})();
{BG_SCRIPT}
</script>
</body>
</html>
'''
    return html


def main():
    for locale in ("ru", "en"):
        out = ROOT / LOCALE_META[locale]["html"]
        html = build_html(locale)
        out.write_text(html, encoding="utf-8")
        print(f"{locale}: slides {html.count('class=\"slide')} -> {out}")


if __name__ == "__main__":
    main()
