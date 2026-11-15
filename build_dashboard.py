#!/usr/bin/env python3
"""
生成 zhuiju-dashboard.html —— 个人追剧源看板（单文件、内嵌最新数据）
数据来源: laoma528/awesome-zhuiju-free (CC BY 4.0)
用法: python build_dashboard.py   （每次运行都会拉取最新数据重建）
"""
import json
import time
import os
import socket
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta

# 容器内 DNS 可能只返回 IPv6（Docker 无 IPv6 出口时会卡死），强制优先 IPv4
_gai = socket.getaddrinfo


def _gai_v4(*a, **k):
    res = _gai(*a, **k)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res


socket.getaddrinfo = _gai_v4

RAW = "https://raw.githubusercontent.com/laoma528/awesome-zhuiju-free/main"
# raw.githubusercontent 在部分网络下极不稳定（连接被重置），按顺序回退到镜像
MIRRORS = [
    (RAW, 8),
    ("https://cdn.jsdelivr.net/gh/laoma528/awesome-zhuiju-free@main", 25),
    ("https://ghfast.top/https://raw.githubusercontent.com/laoma528/awesome-zhuiju-free/main", 25),
]
TZ = timezone(timedelta(hours=8))

def fetch(path):
    last = None
    for base, tmo in MIRRORS:
        for i in range(2):
            try:
                req = urllib.request.Request(base + path, headers={"User-Agent": "zhuiju-dashboard/1.0"})
                with urllib.request.urlopen(req, timeout=tmo) as r:
                    return json.loads(r.read().decode())
            except Exception as e:
                last = e
                print(f"    ! {base.split('/')[2]} 第 {i + 1} 次失败: {type(e).__name__}: {str(e)[:60]}")
                time.sleep(1.5)
        print(f"    → 换下一个镜像")
    raise last

print("[1/3] 拉取 resources.json ...")
res = fetch("/resources/resources.json")
print("[2/3] 拉取 reports/availability.json ...")
av = fetch("/reports/availability.json")

avail = {}
for row in av.get("results", []):
    avail[row["resource_id"]] = row

CATS = [
    ("online_video", "在线影视"), ("video_app", "影视APP"), ("cloud_search", "网盘搜索"),
    ("magnet_search", "磁力&BT"), ("subtitles", "字幕"), ("player", "TVBox空壳"),
    ("tvbox_config", "TVBox配置"), ("subscription", "直播源"), ("open_source", "开源项目"),
]
CAT_NAME = dict(CATS)
AV_META = {
    "reachable": ("🟢 可访问", "#22c55e"),
    "restricted": ("🟡 受限", "#eab308"),
    "unreachable": ("🔴 不可达", "#ef4444"),
}
RISK_COLOR = {"high": "#ef4444", "medium": "#f97316", "low": "#22c55e", "unknown": "#64748b"}
VER_NAME = {"recommended": "✅ 推荐", "caution": "⚠️ 待验证", "pending": "⏳ 新收录", "removed": "🚫 已下架"}

items = []
for r in res["resources"]:
    a = avail.get(r["id"], {})
    scores = r.get("scores", {})
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    avg = round(sum(vals) / len(vals), 1) if vals else 0
    items.append({
        "id": r["id"], "name": r["name"], "url": r["url"],
        "cat": r["category"], "catName": CAT_NAME.get(r["category"], r["category"]),
        "sum": r.get("summary_short") or r.get("summary") or "",
        "tags": r.get("tags", []), "scores": scores, "avg": avg,
        "risks": r.get("risks", {}),
        "ver": r.get("verification", {}).get("status"),
        "verNote": r.get("verification", {}).get("notes") or "",
        "added": (r.get("source") or {}).get("added_at", ""),
        "av": a.get("status"), "http": a.get("http_status"),
        "avAt": (a.get("checked_at") or "")[:10],
        "ms": a.get("response_ms"),
    })

# 自己维护的源：check_availability.py 的产出（没有就留空，看板不显示该区块）
mine, mine_at = [], ""
mine_path = os.environ.get("MINE_REPORT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reports", "availability.json")
try:
    with open(mine_path, encoding="utf-8") as f:
        _m = json.load(f)
    mine_at = (_m.get("generated_at") or "")[:16].replace("T", " ")
    for r in _m.get("results", []):
        mine.append({"name": r.get("name"), "url": r.get("url"), "cat": r.get("category") or "",
                     "st": r.get("status"), "http": r.get("http_status"),
                     "ms": r.get("response_ms"), "err": (r.get("error") or "")[:70]})
    _c = Counter(r["st"] for r in mine)
    print(f"       我的源 {len(mine)} 个：🟢{_c.get('reachable',0)} 🟡{_c.get('restricted',0)} 🔴{_c.get('unreachable',0)}")
except FileNotFoundError:
    print("       未找到本地探活报告，跳过「我的源」区块")
except Exception as e:
    print(f"       ! 读取本地探活报告失败: {type(e).__name__}: {e}")

data = {
    "generated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
    "srcUpdated": res.get("updated_at", ""),
    "avGenerated": (av.get("generated_at") or "")[:16].replace("T", " "),
    "cats": [{"k": k, "n": n} for k, n in CATS],
    "items": items,
    "mine": mine,
    "mineAt": mine_at,
}
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
n_total = len(items)
cnt = Counter(i["av"] for i in items)
n_rec = sum(1 for i in items if i["ver"] == "recommended")
print(f"[3/3] 生成 HTML ... 共 {n_total} 条, 🟢{cnt.get('reachable',0)} 🟡{cnt.get('restricted',0)} 🔴{cnt.get('unreachable',0)}, 推荐 {n_rec}")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>我的追剧源看板</title>
<style>
:root{--bg:#0f1117;--panel:#161a23;--panel2:#1d222e;--line:#2a3040;--fg:#e6e9f0;--fg2:#8b93a7;
--accent:#4f8cff;--green:#22c55e;--yellow:#eab308;--red:#ef4444;--orange:#f97316}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif;padding:24px}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:22px;letter-spacing:.5px}
.sub{color:var(--fg2);font-size:12px;margin-top:4px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;font-size:13px}
.stat b{font-size:17px;margin-right:4px}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 10px}
input[type=text],select{background:var(--panel);border:1px solid var(--line);color:var(--fg);
border-radius:8px;padding:8px 12px;font-size:13px;outline:none}
input[type=text]{flex:1;min-width:220px}
input[type=text]:focus{border-color:var(--accent)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 16px}
.chip{background:var(--panel);border:1px solid var(--line);color:var(--fg2);border-radius:999px;
padding:4px 12px;font-size:12px;cursor:pointer;user-select:none}
.chip.on{background:#223052;border-color:var(--accent);color:#cfe0ff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;
display:flex;flex-direction:column;gap:8px;transition:border-color .15s}
.card:hover{border-color:#3d4666}
.card.off{opacity:.45}
.top{display:flex;align-items:center;gap:8px}
.name{font-weight:600;font-size:15px}
.host{color:var(--fg2);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.sum{color:var(--fg2);font-size:12.5px;min-height:18px}
.badges{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:11px}
.b{border-radius:6px;padding:2px 8px;border:1px solid var(--line);background:var(--panel2)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}
.score{color:var(--yellow)}
.avpill{font-size:11px;padding:2px 8px;border-radius:6px;border:1px solid var(--line)}
.meta{color:var(--fg2);font-size:11px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.actions{display:flex;gap:6px;margin-top:2px}
button{background:var(--panel2);border:1px solid var(--line);color:var(--fg);border-radius:8px;
padding:5px 12px;font-size:12px;cursor:pointer}
button:hover{border-color:var(--accent)}
.note{color:var(--fg2);font-size:11.5px;border-left:2px solid var(--line);padding-left:8px}
footer{margin-top:28px;color:var(--fg2);font-size:11.5px;line-height:1.8;border-top:1px solid var(--line);padding-top:14px}
.empty{color:var(--fg2);text-align:center;padding:40px}
.mine{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;margin:16px 0}
.mine-h{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;
font-size:13px;font-weight:600;margin-bottom:10px}
.mine-h em{color:var(--fg2);font-style:normal;font-weight:400;font-size:11.5px}
.mine-list{display:flex;gap:8px;flex-wrap:wrap}
.msrc{display:flex;align-items:center;gap:6px;background:var(--panel2);border:1px solid var(--line);
border-radius:8px;padding:5px 10px;font-size:12px;cursor:default}
.msrc em{color:var(--fg2);font-style:normal;font-size:11px}
.msrc.bad{border-color:#7f2d2d;background:#241a1a}
</style></head><body><div class="wrap">
<h1>我的追剧源看板</h1>
<div class="sub">数据源：laoma528/awesome-zhuiju-free（CC BY 4.0）· 资源库更新 @@SRC@@ · 探活时间 @@AVG@@ · 本页生成于 @@GEN@@</div>
<div class="stats">
  <div class="stat"><b>@@N@@</b>资源</div>
  <div class="stat"><b style="color:var(--green)">@@GR@@</b>可访问</div>
  <div class="stat"><b style="color:var(--yellow)">@@YE@@</b>受限</div>
  <div class="stat"><b style="color:var(--red)">@@RD@@</b>不可达</div>
  <div class="stat"><b style="color:var(--accent)">@@RC@@</b>官方推荐</div>
</div>
<div id="mine"></div>
<div class="controls">
  <input type="text" id="q" placeholder="搜索名称 / 简介 / 标签 / 域名 …">
  <select id="ver">
    <option value="">全部收录状态</option>
    <option value="recommended">✅ 推荐</option>
    <option value="caution">⚠️ 待验证</option>
    <option value="removed">🚫 已下架</option>
  </select>
  <select id="sort">
    <option value="def">排序：分类默认</option>
    <option value="score">排序：评分高→低</option>
    <option value="av">排序：可用优先</option>
    <option value="name">排序：名称</option>
  </select>
</div>
<div class="chips" id="chips"></div>
<div class="grid" id="grid"></div>
<div class="empty" id="empty" style="display:none">没有匹配的资源</div>
<footer>
风险标记：<span class="dot" style="background:#ef4444"></span>high（高）&nbsp;
<span class="dot" style="background:#f97316"></span>medium（中）&nbsp;
<span class="dot" style="background:#22c55e"></span>low（低）&nbsp;
<span class="dot" style="background:#64748b"></span>unknown<br>
探活只测「首页是否响应」，不代表能出片；TVBox 配置是否可用必须自行导入测试。<br>
本页数据按 CC BY 4.0 引用自 awesome-zhuiju-free 项目，收录站点的版权与安全风险由使用者自行承担。
</footer>
</div>
<script>
const D=@@DATA@@;
const AVC={"reachable":"🟢 可访问","restricted":"🟡 受限","unreachable":"🔴 不可达","": "⚪ 未检测"};
const AVCOL={"reachable":"#22c55e","restricted":"#eab308","unreachable":"#ef4444","":"#64748b"};
const RISKC={"high":"#ef4444","medium":"#f97316","low":"#22c55e","unknown":"#64748b"};
const RISKN={high:"高",medium:"中",low:"低",unknown:"?"};
const VER={"recommended":"✅ 推荐","caution":"⚠️ 待验证","pending":"⏳ 新收录","removed":"🚫 已下架"};
let cat="",q="",ver="",sort="def";
const chipsEl=document.getElementById("chips");
function chip(k,n,label){const c=document.createElement("div");c.className="chip"+(k===cat?" on":"");
c.textContent=label+" "+n;c.onclick=()=>{cat=(cat===k?"":k);renderChips();render()};chipsEl.appendChild(c)}
function renderChips(){chipsEl.innerHTML="";chip("",D.items.length,"全部");
D.cats.forEach(c=>{const n=D.items.filter(i=>i.cat===c.k).length;if(n)chip(c.k,n,c.n)})}
function host(u){try{return new URL(u).hostname}catch(e){return u}}
function stars(v){if(!v)return"";return "★".repeat(Math.round(v))+"☆".repeat(5-Math.round(v))}
function render(){
 const list=D.items.filter(i=>{
  if(cat&&i.cat!==cat)return false;
  if(ver&&i.ver!==ver)return false;
  if(q){const s=(i.name+" "+i.sum+" "+i.tags.join(" ")+" "+i.url+" "+i.id).toLowerCase();
   if(!s.includes(q))return false}
  return true});
 if(sort==="score")list.sort((a,b)=>b.avg-a.avg);
 else if(sort==="av"){const w={reachable:0,restricted:1,unreachable:2,"":3};list.sort((a,b)=>(w[a.av]??3)-(w[b.av]??3)||b.avg-a.avg)}
 else if(sort==="name")list.sort((a,b)=>a.name.localeCompare(b.name,"zh"));
 const g=document.getElementById("grid");g.innerHTML="";
 document.getElementById("empty").style.display=list.length?"none":"block";
 list.forEach(i=>{
  const c=document.createElement("div");c.className="card"+(i.ver==="removed"?" off":"");
  const av=i.av||"";
  const risks=Object.entries(i.risks||{}).map(([k,v])=>
   `<span class="b" title="${k}:${v}"><span class="dot" style="background:${RISKC[v]||'#64748b'}"></span>${k}</span>`).join("");
  c.innerHTML=`
   <div class="top"><span class="name">${i.name}</span><span class="host">${host(i.url)}</span></div>
   <div class="sum">${i.sum||""}</div>
   <div class="badges">
    <span class="b score" title="资源/速度/无广告/稳定/易用">${stars(i.avg)} <b>${i.avg}</b></span>
    <span class="avpill" style="color:${AVCOL[av]};border-color:${AVCOL[av]}55">${AVC[av]||"⚪ 未检测"}</span>
    ${VER[i.ver]?`<span class="b">${VER[i.ver]}</span>`:""}
   </div>
   <div class="badges">${risks}</div>
   ${i.verNote?`<div class="note">${i.verNote.slice(0,90)}${i.verNote.length>90?"…":""}</div>`:""}
   <div class="meta">
    <span>${i.catName}${i.tags.length?" · "+i.tags.slice(0,3).join(" / "):""}</span>
    <span>${i.avAt?("探活 "+i.avAt+(i.http?" · HTTP "+i.http:"")+(i.ms?" · "+i.ms+"ms":"")):""}</span>
   </div>
   <div class="actions">
    <button onclick="window.open('${i.url}','_blank')">打开</button>
    <button onclick="copyUrl('${i.url.replace(/'/g,"\\'")}',this)">复制地址</button>
   </div>`;
  g.appendChild(c)});
}
function copyUrl(u,btn){navigator.clipboard.writeText(u).then(()=>{btn.textContent="已复制 ✓";
setTimeout(()=>btn.textContent="复制地址",1200)})}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function renderMine(){
 const el=document.getElementById("mine");
 if(!D.mine||!D.mine.length){el.style.display="none";return}
 const c={reachable:0,restricted:0,unreachable:0};
 D.mine.forEach(m=>{if(c[m.st]!==undefined)c[m.st]++});
 const col={reachable:"#22c55e",restricted:"#eab308",unreachable:"#ef4444"};
 let h='<div class="mine-h"><span>我的源 · NAS 自测</span><em>共 '+D.mine.length+' 个　🟢'+c.reachable+
   '　🟡'+c.restricted+'　🔴'+c.unreachable+'　· 探活于 '+(D.mineAt||"—")+'</em></div><div class="mine-list">';
 D.mine.forEach(m=>{
  const info=m.http?(m.http+(m.ms?" · "+m.ms+"ms":"")):(m.err||"无响应");
  h+='<div class="msrc'+(m.st==="unreachable"?" bad":"")+'" title="'+esc(m.url)+'&#10;'+esc(m.err||"")+
     '"><span class="dot" style="background:'+(col[m.st]||"#64748b")+'"></span><span>'+esc(m.name)+
     '</span><em>'+esc(info)+'</em></div>';
 });
 el.innerHTML=h+"</div>";
}
document.getElementById("q").oninput=e=>{q=e.target.value.trim().toLowerCase();render()};
document.getElementById("ver").onchange=e=>{ver=e.target.value;render()};
document.getElementById("sort").onchange=e=>{sort=e.target.value;render()};
renderChips();renderMine();render();
</script></body></html>"""

html = (TEMPLATE
        .replace("@@DATA@@", blob)
        .replace("@@N@@", str(n_total))
        .replace("@@GR@@", str(cnt.get("reachable", 0)))
        .replace("@@YE@@", str(cnt.get("restricted", 0)))
        .replace("@@RD@@", str(cnt.get("unreachable", 0)))
        .replace("@@RC@@", str(n_rec))
        .replace("@@GEN@@", data["generated"])
        .replace("@@SRC@@", data["srcUpdated"] or "未知")
        .replace("@@AVG@@", data["avGenerated"] or "未知"))

out = os.environ.get("OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
# 原子写入：先写临时文件再替换，避免 Web 服务读到半个文件
tmp = out + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(html)
os.replace(tmp, out)
print(f"[done] {out}  ({len(html)//1024} KB)")
