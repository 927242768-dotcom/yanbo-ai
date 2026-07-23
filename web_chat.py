"""彦博本地网页聊天界面，支持文字和图片题目流式输出。"""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import os
import queue
import re
import shutil
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import psutil

from assistant_engine import AssistantEngine, DISPLAY_NAME
from capability_config import ModeProfile, load_mode_profiles
from console_utils import configure_utf8_console
from image_understanding import ImageRecognitionError, MAX_IMAGE_BYTES, OCRResult
from remote_access_config import load_remote_access_config


MOBILE_DIR = os.path.join(os.path.dirname(__file__), "mobile")
MOBILE_UPDATE_PATH = os.path.join(os.path.dirname(__file__), "mobile_update.json")
RELEASES_DIR = os.path.join(os.path.dirname(__file__), "releases")
HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#2563eb">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="彦博">
<link rel="manifest" href="/mobile/manifest.webmanifest">
<link rel="icon" href="/mobile/icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="/mobile/apple-touch-icon.png">
<title>__DISPLAY_NAME__</title>
<style>
:root{color-scheme:light;--bg:#f4f6f8;--panel:#fff;--line:#e5e7eb;--text:#172033;--muted:#64748b;--primary:#2563eb;--bot:#eef2f7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;color:var(--text)}
main{max-width:920px;margin:0 auto;padding:22px}h1{font-size:26px;margin:0 0 5px}.sub{color:var(--muted);margin-bottom:16px}
#chat{height:62vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 5px 20px rgba(0,0,0,.05)}
.msg{margin:11px 0;display:flex;gap:8px}.msg.user{justify-content:flex-end}.message-box{max-width:82%}.bubble{padding:11px 14px;border-radius:14px;white-space:pre-wrap;line-height:1.62;overflow-wrap:anywhere}
.user .bubble{background:var(--primary);color:#fff;border-bottom-right-radius:4px}.bot .bubble{background:var(--bot);border-bottom-left-radius:4px}
.message-image{display:block;max-width:min(360px,75vw);max-height:280px;object-fit:contain;border-radius:12px;margin:0 0 7px auto;border:1px solid var(--line);background:#fff}
.composer{margin-top:13px;background:#fff;border:1px solid #cbd5e1;border-radius:14px;padding:9px;box-shadow:0 3px 12px rgba(0,0,0,.04)}
#preview{display:none;align-items:center;gap:10px;padding:5px 5px 10px}#preview img{width:72px;height:56px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.preview-info{min-width:0;flex:1}.preview-name{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.preview-hint{font-size:12px;color:var(--muted)}
.mode-row{display:flex;justify-content:flex-start;padding:1px 2px 8px}.mode-select{height:34px;border:1px solid var(--line);border-radius:9px;background:#f8fafc;color:var(--text);padding:0 10px;font:inherit;font-size:13px;outline:none}.input-row{display:flex;gap:8px;align-items:flex-end}textarea{flex:1;resize:none;border:0;outline:0;padding:8px;font:inherit;min-height:48px;max-height:160px}
button{border:0;border-radius:10px;cursor:pointer;font-size:14px}.icon-button{height:44px;background:#e7eefb;font-size:15px;color:#1d4ed8;font-weight:650}.attach-button{min-width:112px;padding:0 14px;white-space:nowrap}.send-button{height:44px;padding:0 21px;background:#111827;color:#fff}.send-button:disabled,.icon-button:disabled{opacity:.5;cursor:not-allowed}
.tools{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:9px;flex-wrap:wrap}.tool-buttons{display:flex;gap:8px;flex-wrap:wrap}.tools button,.tools a{border:0;border-radius:10px;background:#64748b;color:white;padding:8px 13px;text-decoration:none;font-size:14px;cursor:pointer}.tools #installApp{background:#2563eb;display:none}.tools #downloadAndroid{background:#16a34a;display:none}.status{font-size:13px;color:var(--muted)}
.update-banner{display:none;margin:10px 0 0;padding:10px 12px;border-radius:10px;background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af;font-size:13px}.update-banner a{color:#1d4ed8;font-weight:700}
.ocr-details{margin-top:7px;font-size:12px;color:#475569;background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:7px 9px}.ocr-details summary{cursor:pointer}.ocr-details pre{white-space:pre-wrap;margin:7px 0 0;font-family:inherit;line-height:1.5}
.cursor::after{content:"▍";animation:blink .8s infinite}@keyframes blink{50%{opacity:0}}
@media(max-width:640px){main{padding:10px}#chat{height:58vh}.message-box{max-width:92%}.attach-button{min-width:48px;width:48px;padding:0;font-size:0}.attach-button::before{content:"＋";font-size:22px}.send-button{padding:0 15px}}
</style>
</head>
<body><main>
<h1>__DISPLAY_NAME__</h1>
<div class="sub">支持流式聊天、图片文字识别、拍照做题、代码与学习答疑。</div>
<div id="chat"><div class="msg bot"><div class="message-box"><div class="bubble">你好，我是 __DISPLAY_NAME__。你可以直接聊天，也可以上传题目图片让我识别并解答。</div></div></div></div>
<div class="composer">
  <div class="mode-row"><select id="modeSelect" class="mode-select" aria-label="回答模式"><option value="thinking">彦博-思考</option><option value="fast">彦博-快速</option><option value="expert">彦博-专家</option></select></div>
  <div id="preview"><img id="previewImg" alt="图片预览"><div class="preview-info"><div id="previewName" class="preview-name"></div><div class="preview-hint">默认OCR分析；专家视觉启用时同时读取原图</div></div><button id="removeImage" class="icon-button" type="button" title="移除图片">×</button></div>
  <div class="input-row"><button id="attach" class="icon-button attach-button" type="button" title="上传图片" aria-label="上传图片">＋ 上传图片</button><textarea id="input" placeholder="输入消息；点击上传图片，或按 Ctrl+V 粘贴截图……"></textarea><button id="send" class="send-button" type="button">发送</button></div>
  <input id="fileInput" type="file" accept="image/png,image/jpeg,image/webp,image/bmp" hidden>
</div>
<div id="updateBanner" class="update-banner"></div>
<div class="tools"><div class="tool-buttons"><button id="reset" type="button">清空上下文</button><button id="accessKey" type="button">访问令牌</button><button id="installApp" type="button">安装到手机/桌面</button><a id="downloadAndroid" href="#" download>下载Android应用</a></div><span id="status" class="status">__BACKEND_INFO__</span></div>
</main>
<script>
const chat=document.getElementById('chat'),input=document.getElementById('input'),send=document.getElementById('send'),modeSelect=document.getElementById('modeSelect');
const attach=document.getElementById('attach'),fileInput=document.getElementById('fileInput'),preview=document.getElementById('preview');
const previewImg=document.getElementById('previewImg'),previewName=document.getElementById('previewName'),statusEl=document.getElementById('status');
const installApp=document.getElementById('installApp'),downloadAndroid=document.getElementById('downloadAndroid'),updateBanner=document.getElementById('updateBanner'),accessKeyButton=document.getElementById('accessKey');
let selectedFile=null,selectedUrl='',busy=false,deferredInstallPrompt=null,accessToken=localStorage.getItem('yanbo_access_token')||'',authRequired=null;
const fragmentParams=new URLSearchParams(location.hash.slice(1));const fragmentToken=fragmentParams.get('token');if(fragmentToken){accessToken=fragmentToken;localStorage.setItem('yanbo_access_token',accessToken);history.replaceState(null,'',location.pathname+location.search);}
function authHeaders(json=false){const headers={};if(json)headers['Content-Type']='application/json';if(accessToken)headers['X-Yanbo-Token']=accessToken;return headers;}
function securedUrl(url){if(!url||!accessToken)return url;return url+(url.includes('?')?'&':'?')+'token='+encodeURIComponent(accessToken);}
function configureAccessToken(){const value=prompt('请输入电脑端 remote_access.json 中的访问令牌：',accessToken);if(value===null)return false;accessToken=value.trim();if(accessToken)localStorage.setItem('yanbo_access_token',accessToken);else localStorage.removeItem('yanbo_access_token');statusEl.textContent=accessToken?'访问令牌已保存':'访问令牌已清除';return Boolean(accessToken);}
async function checkAccessMode(){try{const response=await fetch('/api/status',{cache:'no-store'});const info=await response.json();authRequired=Boolean(info.auth_required);}catch{authRequired=false;}return authRequired;}
async function ensureAccess(){if(authRequired===null)await checkAccessMode();if(!authRequired)return true;if(accessToken)return true;return configureAccessToken();}
accessKeyButton.addEventListener('click',()=>{if(configureAccessToken())checkUpdates();});

if('serviceWorker' in navigator){
  window.addEventListener('load',()=>navigator.serviceWorker.register('/mobile/service-worker.js').catch(()=>{}));
}
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstallPrompt=event;installApp.style.display='inline-block';});
installApp.addEventListener('click',async()=>{
  if(deferredInstallPrompt){deferredInstallPrompt.prompt();await deferredInstallPrompt.userChoice;deferredInstallPrompt=null;installApp.style.display='none';return;}
  const isIOS=/iphone|ipad|ipod/i.test(navigator.userAgent);
  alert(isIOS?'请点击Safari底部“分享”，再选择“添加到主屏幕”。':'请打开浏览器菜单，选择“安装应用”或“添加到主屏幕”。');
});
async function checkUpdates(){
  try{
    const response=await fetch('/api/version',{cache:'no-store'});if(!response.ok)return;
    const info=await response.json();
    if(info.model_name)statusEl.textContent=`${info.model_name} · 已启用流式输出与图片识别`;
    if(info.android_download_url){downloadAndroid.href=securedUrl(info.android_download_url);downloadAndroid.style.display='inline-block';}
    if(info.force_update&&info.android_download_url){const updateUrl=securedUrl(info.android_download_url);updateBanner.style.display='block';updateBanner.innerHTML=`发现必须更新的应用版本：<a href="${updateUrl}" target="_blank" rel="noopener">立即更新</a>`;}
  }catch{}
}
checkAccessMode();
checkUpdates();
function scrollBottom(){chat.scrollTop=chat.scrollHeight;}
function addMessage(role,text,imageUrl=''){const row=document.createElement('div');row.className='msg '+role;const box=document.createElement('div');box.className='message-box';if(imageUrl){const img=document.createElement('img');img.className='message-image';img.src=imageUrl;box.appendChild(img);}const bubble=document.createElement('div');bubble.className='bubble';bubble.textContent=text;box.appendChild(bubble);row.appendChild(box);chat.appendChild(row);scrollBottom();return {row,box,bubble};}
function clearImage(){selectedFile=null;if(selectedUrl)URL.revokeObjectURL(selectedUrl);selectedUrl='';preview.style.display='none';fileInput.value='';previewImg.removeAttribute('src');}
function selectImage(file){if(!file)return;if(file.size>15*1024*1024){alert('图片不能超过15MB');return;}if(!file.type.startsWith('image/')){alert('请选择图片文件');return;}clearImage();selectedFile=file;selectedUrl=URL.createObjectURL(file);previewImg.src=selectedUrl;previewName.textContent=file.name;preview.style.display='flex';}
function setBusy(value,label=''){busy=value;send.disabled=value;attach.disabled=value;modeSelect.disabled=value;document.getElementById('reset').disabled=value;send.textContent=value?'生成中':'发送';statusEl.textContent=label||'__BACKEND_INFO__';}
function fileToDataUrl(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('读取图片失败'));reader.readAsDataURL(file);});}
async function readJsonResponse(response){const data=await response.json();if(!response.ok)throw new Error(data.error||'请求失败');return data;}
async function consumeStream(response,onEvent){if(!response.ok){let message='请求失败';try{message=(await response.json()).error||message;}catch{}throw new Error(message);}const reader=response.body.getReader(),decoder=new TextDecoder('utf-8');let buffer='';while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let pos;while((pos=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,pos).trim();buffer=buffer.slice(pos+1);if(line)onEvent(JSON.parse(line));}}buffer+=decoder.decode();if(buffer.trim())onEvent(JSON.parse(buffer.trim()));}
async function submit(){if(busy)return;if(!await ensureAccess())return;const text=input.value.trim();if(!text&&!selectedFile)return;const file=selectedFile,mode=modeSelect.value||'thinking';let bot=null;setBusy(true,file?'正在读取图片……':'正在思考……');try{const imageData=file?await fileToDataUrl(file):'';addMessage('user',text||(file?'请识别并解答这张图片。':''),imageData);input.value='';bot=addMessage('bot','');bot.bubble.classList.add('cursor');let endpoint='/chat-stream',payload={message:text,mode};if(file){endpoint='/chat-image-stream';payload={message:text||'请识别并详细解答图片中的题目。',filename:file.name,image:imageData,mode};clearImage();}const response=await fetch(endpoint,{method:'POST',headers:authHeaders(true),body:JSON.stringify(payload)});let received=false;await consumeStream(response,event=>{if(event.type==='stage'){statusEl.textContent=event.text;return;}if(event.type==='ocr'){const details=document.createElement('details');details.className='ocr-details';const summary=document.createElement('summary');summary.textContent=`已识别 ${event.line_count} 行文字，置信度 ${Math.round(event.confidence*100)}%`;const pre=document.createElement('pre');pre.textContent=event.text;details.append(summary,pre);bot.box.appendChild(details);scrollBottom();return;}if(event.type==='delta'){if(!received){bot.bubble.textContent='';received=true;}bot.bubble.textContent+=event.text;scrollBottom();return;}if(event.type==='error')throw new Error(event.error||'生成失败');});if(!received)bot.bubble.textContent='没有生成有效回答。';}catch(error){if(bot)bot.bubble.textContent='处理失败：'+error.message;else addMessage('bot','处理失败：'+error.message);}finally{if(bot)bot.bubble.classList.remove('cursor');setBusy(false,'__BACKEND_INFO__');input.focus();}}
attach.addEventListener('click',()=>fileInput.click());fileInput.addEventListener('change',()=>selectImage(fileInput.files[0]));document.getElementById('removeImage').addEventListener('click',clearImage);send.addEventListener('click',submit);
input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();submit();}});
function handlePaste(event){const items=[...(event.clipboardData?.items||[])];const item=items.find(value=>value.type&&value.type.startsWith('image/'));if(!item)return;const file=item.getAsFile();if(file){selectImage(file);statusEl.textContent='已粘贴图片，点击发送即可识别并解题';event.preventDefault();}}
document.addEventListener('paste',handlePaste,true);
document.getElementById('reset').addEventListener('click',async()=>{if(busy)return;if(!await ensureAccess())return;const response=await fetch('/reset',{method:'POST',headers:authHeaders(true),body:'{}'});await readJsonResponse(response);chat.innerHTML='';addMessage('bot','上下文已清空。你可以继续聊天或上传新的题目图片。');clearImage();input.focus();});
</script></body></html>"""


DATA_URL_PATTERN = re.compile(
    r"^data:image/(png|jpeg|jpg|webp|bmp);base64,(.+)$",
    flags=re.IGNORECASE | re.DOTALL,
)


def stop_stale_web_servers(host: str, port: int) -> None:
    """关闭同一项目遗留的旧网页进程，避免浏览器连接到旧版本。"""
    current_pid = os.getpid()
    stale: list[psutil.Process] = []
    unrelated: list[int] = []

    for connection in psutil.net_connections(kind="tcp"):
        if not connection.laddr or connection.laddr.port != port:
            continue
        if connection.status != psutil.CONN_LISTEN or not connection.pid:
            continue
        if connection.pid == current_pid:
            continue
        try:
            process = psutil.Process(connection.pid)
            command = " ".join(process.cmdline()).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
        if "web_chat.py" in command:
            stale.append(process)
        else:
            unrelated.append(connection.pid)

    for process in stale:
        try:
            print(f"正在关闭旧网页实例 PID={process.pid}……")
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if stale:
        _, alive = psutil.wait_procs(stale, timeout=4)
        for process in alive:
            try:
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(0.4)

    if unrelated:
        raise RuntimeError(f"端口{port}已被其他程序占用，进程号：{sorted(set(unrelated))}")


def get_lan_ip() -> str:
    """获取手机在同一局域网中可访问的电脑地址。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


class ModeEnginePool:
    """按能力模式延迟加载模型，并统一控制本机推理并发。"""

    def __init__(self, server_mode: str = "auto") -> None:
        self.server_mode = server_mode
        self.profiles = load_mode_profiles()
        self._engines: dict[str, AssistantEngine] = {}
        self._engine_guard = threading.Lock()
        # 本机内存约束下统一串行生成；远程专家后端也保持顺序，避免会话状态交叉。
        self._generation_lock = threading.Lock()

    @staticmethod
    def normalize(mode: object) -> str:
        candidate = str(mode).strip().lower()
        return candidate if candidate in {"fast", "thinking", "expert"} else "thinking"

    def profile_for(self, mode: str) -> ModeProfile:
        return self.profiles[self.normalize(mode)]

    def label_for(self, mode: str) -> str:
        return self.profile_for(mode).display_name

    def backend_for(self, mode: str) -> str:
        if self.server_mode == "fallback":
            return "fallback"
        if self.server_mode == "native":
            return "native"
        return self.profile_for(mode).effective_backend

    def lock_for(self, mode: str) -> threading.Lock:
        del mode
        return self._generation_lock

    def get(self, mode: str) -> AssistantEngine:
        normalized = self.normalize(mode)
        engine = self._engines.get(normalized)
        if engine is not None:
            return engine
        with self._engine_guard:
            engine = self._engines.get(normalized)
            if engine is None:
                profile = self.profile_for(normalized)
                engine = AssistantEngine(
                    backend=self.backend_for(normalized),
                    runtime_model=profile.model,
                    num_ctx=profile.num_ctx,
                    remote_api_url=profile.remote_api_url,
                    remote_api_key=profile.remote_api_key,
                    remote_model=profile.remote_model,
                    use_knowledge_base=profile.knowledge_base,
                    direct_vision=profile.direct_vision,
                )
                self._engines[normalized] = engine
        return engine

    def status(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        for mode in ("fast", "thinking", "expert"):
            payload[mode] = (
                self._engines[mode].backend_info if mode in self._engines else "正在准备"
            )
            payload[f"{mode}_ready"] = mode in self._engines
            payload[f"{mode}_name"] = self.label_for(mode)
        return payload


class StrictThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64

    def server_bind(self) -> None:
        super().server_bind()
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass


class ChatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    engine_pool: ModeEnginePool
    html: bytes
    access_token = ""
    session_states: dict[str, dict] = {}
    session_accessed: dict[str, float] = {}
    request_results: dict[str, dict] = {}
    request_accessed: dict[str, float] = {}
    request_jobs: dict[str, dict] = {}
    job_accessed: dict[str, float] = {}
    cache_lock = threading.Lock()
    job_lock = threading.RLock()
    job_condition = threading.Condition(job_lock)
    max_sessions = 120
    max_requests = 160
    max_jobs = 160

    def _authorized(self, allow_query: bool = False) -> bool:
        if not self.access_token:
            return True
        supplied = self.headers.get("X-Yanbo-Token", "").strip()
        if not supplied and allow_query:
            values = parse_qs(urlsplit(self.path).query).get("token", [])
            supplied = values[0].strip() if values else ""
        return bool(supplied) and hmac.compare_digest(supplied, self.access_token)

    def _authorized_payload(self, payload: dict) -> bool:
        if not self.access_token:
            return True
        supplied = str(payload.get("token", "")).strip()
        return bool(supplied) and hmac.compare_digest(supplied, self.access_token)

    @staticmethod
    def _normalize_session_id(raw: object) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._:-]", "-", str(raw or "").strip())[:160]
        return normalized or "default"

    def _session_id(self) -> str:
        return self._normalize_session_id(self.headers.get("X-Yanbo-Session", ""))

    @classmethod
    def _prune_sessions(cls) -> None:
        if len(cls.session_states) <= cls.max_sessions:
            return
        remove_count = len(cls.session_states) - cls.max_sessions
        oldest = sorted(cls.session_accessed.items(), key=lambda item: item[1])[:remove_count]
        for session_id, _ in oldest:
            cls.session_states.pop(session_id, None)
            cls.session_accessed.pop(session_id, None)

    @classmethod
    def _prune_requests(cls) -> None:
        if len(cls.request_results) <= cls.max_requests:
            return
        remove_count = len(cls.request_results) - cls.max_requests
        oldest = sorted(cls.request_accessed.items(), key=lambda item: item[1])[:remove_count]
        for request_key, _ in oldest:
            cls.request_results.pop(request_key, None)
            cls.request_accessed.pop(request_key, None)

    @classmethod
    def _prune_jobs(cls) -> None:
        if len(cls.request_jobs) <= cls.max_jobs:
            return
        removable = [
            (key, cls.job_accessed.get(key, 0.0))
            for key, job in cls.request_jobs.items()
            if job.get("state") in {"done", "error", "cancelled"}
        ]
        for request_key, _ in sorted(removable, key=lambda item: item[1])[: max(0, len(cls.request_jobs) - cls.max_jobs)]:
            cls.request_jobs.pop(request_key, None)
            cls.job_accessed.pop(request_key, None)

    def _load_session(self, engine: AssistantEngine, session_id: str, payload: dict) -> None:
        history = payload.get("history")
        if isinstance(history, list):
            engine.replace_history(history)
        else:
            engine.import_state(self.session_states.get(session_id))
        self.session_accessed[session_id] = time.monotonic()

    def _save_session(self, engine: AssistantEngine, session_id: str) -> None:
        self.session_states[session_id] = engine.export_state()
        self.session_accessed[session_id] = time.monotonic()
        self._prune_sessions()

    @staticmethod
    def _request_id(payload: dict) -> str:
        raw = str(payload.get("request_id", "")).strip()
        normalized = re.sub(r"[^A-Za-z0-9._:-]", "-", raw)[:180]
        return normalized or f"legacy-{time.time_ns()}"

    def _try_event(self, payload: dict) -> bool:
        try:
            self._event(payload)
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return False

    def _send(self, status: int, body: bytes, content_type: str, cache_control: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Yanbo-Token, X-Yanbo-Session")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Connection", "keep-alive")
        self.send_header("Keep-Alive", "timeout=30, max=200")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > 22 * 1024 * 1024:
            raise ValueError("请求内容过大。")
        return json.loads(self.rfile.read(length))

    def _start_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Yanbo-Token, X-Yanbo-Session")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _event(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.wfile.write(line)
        self.wfile.flush()

    def _await_task(self, task, connected: bool, heartbeat_text: str):
        result_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        def worker() -> None:
            try:
                result_queue.put(("result", task()))
            except BaseException as exc:
                result_queue.put(("error", exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while True:
            try:
                kind, value = result_queue.get(timeout=6)
            except queue.Empty:
                if connected:
                    connected = self._try_event(
                        {"type": "heartbeat", "text": heartbeat_text, "time": time.time()}
                    )
                continue
            thread.join()
            if kind == "error":
                raise value
            return value, connected

    def _relay_generation(self, iterator, events: list[dict], connected: bool) -> bool:
        output_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        def worker() -> None:
            try:
                for delta in iterator:
                    output_queue.put(("delta", delta))
                output_queue.put(("done", None))
            except BaseException as exc:
                output_queue.put(("error", exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while True:
            try:
                kind, value = output_queue.get(timeout=6)
            except queue.Empty:
                if connected:
                    connected = self._try_event(
                        {"type": "heartbeat", "text": "保持连接中", "time": time.time()}
                    )
                continue
            if kind == "delta":
                event = {"type": "delta", "text": str(value)}
                events.append(event)
                if connected:
                    connected = self._try_event(event)
                continue
            thread.join()
            if kind == "error":
                raise value
            return connected

    def _cached_result(self, request_key: str) -> dict | None:
        with self.cache_lock:
            result = self.request_results.get(request_key)
            if result is not None:
                self.request_accessed[request_key] = time.monotonic()
            return result

    def _store_result(self, request_key: str, result: dict) -> None:
        with self.cache_lock:
            self.request_results[request_key] = result
            self.request_accessed[request_key] = time.monotonic()
            self._prune_requests()

    @staticmethod
    def _job_payload_locked(job: dict, text_offset: int | None = None) -> dict:
        text = str(job.get("text", ""))
        payload = {
            "request_id": job.get("request_id", ""),
            "state": job.get("state", "queued"),
            "mode": job.get("mode", "thinking"),
            "stage": job.get("stage", ""),
            "ocr": job.get("ocr"),
            "error": job.get("error", ""),
            "revision": int(job.get("revision", 0) or 0),
            "text_length": len(text),
        }
        if text_offset is None:
            payload["text"] = text
        else:
            offset = max(0, int(text_offset))
            reset_text = offset > len(text)
            if reset_text:
                offset = 0
            payload["text_delta"] = text[offset:]
            payload["reset_text"] = reset_text
        return payload

    def _job_snapshot(self, request_key: str, text_offset: int | None = None) -> dict | None:
        with self.job_lock:
            job = self.request_jobs.get(request_key)
            if job is None:
                return None
            self.job_accessed[request_key] = time.monotonic()
            return self._job_payload_locked(job, text_offset=text_offset)

    def _job_wait_snapshot(
        self,
        request_key: str,
        after_revision: int,
        text_offset: int | None,
        wait_seconds: float,
    ) -> dict | None:
        deadline = time.monotonic() + max(0.0, min(wait_seconds, 25.0))
        with self.job_condition:
            while True:
                job = self.request_jobs.get(request_key)
                if job is None:
                    return None
                revision = int(job.get("revision", 0) or 0)
                state = str(job.get("state", "queued"))
                if revision > after_revision or state in {"done", "error", "cancelled"}:
                    self.job_accessed[request_key] = time.monotonic()
                    return self._job_payload_locked(job, text_offset=text_offset)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.job_accessed[request_key] = time.monotonic()
                    return self._job_payload_locked(job, text_offset=text_offset)
                self.job_condition.wait(timeout=remaining)

    def _job_update(self, request_key: str, **changes: object) -> None:
        with self.job_condition:
            job = self.request_jobs.get(request_key)
            if job is None:
                return
            changed = any(job.get(key) != value for key, value in changes.items())
            if not changed:
                return
            job.update(changes)
            job["revision"] = int(job.get("revision", 0) or 0) + 1
            self.job_accessed[request_key] = time.monotonic()
            self.job_condition.notify_all()

    def _job_cancelled(self, request_key: str) -> bool:
        with self.job_lock:
            job = self.request_jobs.get(request_key)
            return job is None or job.get("state") == "cancelled"

    @staticmethod
    def _cached_job_payload(result: dict) -> tuple[str, dict | None]:
        text_parts: list[str] = []
        ocr: dict | None = None
        for event in result.get("events", []):
            if event.get("type") == "delta":
                text_parts.append(str(event.get("text", "")))
            elif event.get("type") == "ocr":
                ocr = {
                    "text": str(event.get("text", "")),
                    "confidence": float(event.get("confidence", 0.0) or 0.0),
                    "line_count": int(event.get("line_count", 0) or 0),
                    "width": int(event.get("width", 0) or 0),
                    "height": int(event.get("height", 0) or 0),
                }
        return "".join(text_parts), ocr

    def _run_generation_job(
        self,
        request_key: str,
        request_id: str,
        session_id: str,
        mode: str,
        payload: dict,
        image_bytes: bytes,
        filename: str,
    ) -> None:
        profile = self.engine_pool.profile_for(mode)
        mode_name = profile.display_name
        mode_lock = self.engine_pool.lock_for(mode)
        acquired = False
        try:
            while not acquired:
                if self._job_cancelled(request_key):
                    return
                acquired = mode_lock.acquire(timeout=2)
                if not acquired:
                    self._job_update(request_key, stage=f"{mode_name}正在处理前一个请求，请稍候……")

            cached = self._cached_result(request_key)
            if cached is not None:
                text, ocr = self._cached_job_payload(cached)
                self._job_update(
                    request_key,
                    state="done",
                    stage="回答已完成",
                    text=text,
                    ocr=ocr,
                    error="",
                )
                return

            self._job_update(request_key, state="running", stage=f"正在加载{mode_name}……")
            engine = self.engine_pool.get(mode)
            if self._job_cancelled(request_key):
                return
            self._load_session(engine, session_id, payload)
            events: list[dict] = []
            ocr_event: dict | None = None

            if image_bytes:
                self._job_update(request_key, stage="正在识别图片文字……")
                result = self._recognize_for_request(engine, image_bytes)
                if result.text:
                    ocr_event = {
                        "type": "ocr",
                        "text": result.text,
                        "confidence": result.confidence,
                        "line_count": len(result.lines),
                        "width": result.width,
                        "height": result.height,
                    }
                    events.append(ocr_event)
                    self._job_update(
                        request_key,
                        stage=f"识别完成，{mode_name}正在分析……",
                        ocr={key: value for key, value in ocr_event.items() if key != "type"},
                    )
                else:
                    self._job_update(
                        request_key,
                        stage=f"未识别到文字，{mode_name}正在直接分析原图……",
                    )
                iterator = engine.stream_image_reply(
                    image_bytes=image_bytes,
                    user_text=str(payload.get("message", "")),
                    filename=filename,
                    max_new_tokens=profile.image_max_tokens,
                    temperature=profile.image_temperature,
                    ocr_result=result,
                    response_mode=mode,
                )
            else:
                self._job_update(request_key, stage=f"{mode_name}正在组织回答……")
                iterator = engine.stream_reply(
                    str(payload.get("message", "")),
                    max_new_tokens=profile.text_max_tokens,
                    temperature=profile.text_temperature,
                    response_mode=mode,
                )

            parts: list[str] = []
            last_publish = 0.0
            for delta in iterator:
                if self._job_cancelled(request_key):
                    close = getattr(iterator, "close", None)
                    if callable(close):
                        close()
                    return
                if not delta:
                    continue
                parts.append(str(delta))
                now = time.monotonic()
                if now - last_publish >= 0.06:
                    self._job_update(
                        request_key,
                        state="running",
                        stage=f"{mode_name}正在回答……",
                        text="".join(parts),
                    )
                    last_publish = now

            answer = "".join(parts).strip()
            if not answer:
                answer = "暂时没有生成有效回答，请再试一次。"
            events.append({"type": "delta", "text": answer})
            self._save_session(engine, session_id)
            self._store_result(request_key, {"events": events, "mode": mode})
            self._job_update(
                request_key,
                state="done",
                stage="回答已完成",
                text=answer,
                error="",
            )
        except BaseException as exc:
            self._job_update(
                request_key,
                state="error",
                stage="回答失败",
                error=str(exc) or exc.__class__.__name__,
            )
        finally:
            if acquired:
                mode_lock.release()
            with self.job_lock:
                self.job_accessed[request_key] = time.monotonic()
                self._prune_jobs()

    def _replay_result(self, result: dict, mode: str) -> None:
        connected = True
        for event in result.get("events", []):
            if connected:
                connected = self._try_event(event)
        if connected:
            self._try_event(
                {"type": "done", "model": DISPLAY_NAME, "mode": mode, "replayed": True}
            )

    @staticmethod
    def _recognize_for_request(
        engine: AssistantEngine,
        image_bytes: bytes,
    ) -> OCRResult:
        try:
            return engine.recognize_image(image_bytes)
        except ImageRecognitionError:
            if engine.direct_vision_ready:
                return OCRResult(text="", lines=[], confidence=0.0, width=0, height=0)
            raise

    @staticmethod
    def _decode_image(data_url: str) -> bytes:
        match = DATA_URL_PATTERN.match(data_url)
        if not match:
            raise ValueError("图片格式无效，请上传JPG、PNG、WEBP或BMP图片。")
        try:
            image_bytes = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("图片数据损坏，无法读取。") from exc
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("图片过大，请上传不超过15MB的图片。")
        return image_bytes

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        request_path = self.path.split("?", 1)[0]
        if request_path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(self.html)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(self.html)
            return

        static_files = {
            "/mobile/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8", "no-cache"),
            "/mobile/service-worker.js": ("service-worker.js", "application/javascript; charset=utf-8", "no-cache"),
            "/mobile/icon-192.png": ("icon-192.png", "image/png", "public, max-age=86400"),
            "/mobile/icon-512.png": ("icon-512.png", "image/png", "public, max-age=86400"),
            "/mobile/apple-touch-icon.png": ("apple-touch-icon.png", "image/png", "public, max-age=86400"),
        }
        if request_path in static_files:
            filename, content_type, cache_control = static_files[request_path]
            path = os.path.join(MOBILE_DIR, filename)
            try:
                with open(path, "rb") as file:
                    body = file.read()
            except OSError:
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            self._send(200, body, content_type, cache_control)
            return

        if request_path.startswith("/downloads/"):
            if not self._authorized(allow_query=True):
                self._json(401, {"error": "下载需要有效访问令牌"})
                return
            filename = request_path.removeprefix("/downloads/")
            safe_name = os.path.basename(filename)
            if not safe_name or safe_name != filename or not safe_name.lower().endswith((".apk", ".aab", ".zip")):
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            path = os.path.join(RELEASES_DIR, safe_name)
            if not os.path.isfile(path):
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            content_type = (
                "application/vnd.android.package-archive"
                if safe_name.lower().endswith(".apk")
                else "application/octet-stream"
            )
            try:
                size = os.path.getsize(path)
                start = 0
                end = size - 1
                status = 200
                range_header = self.headers.get("Range", "").strip()
                if range_header:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                    if not match:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    start_text, end_text = match.groups()
                    if not start_text and not end_text:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if start_text:
                        start = int(start_text)
                        end = int(end_text) if end_text else size - 1
                    else:
                        suffix_length = int(end_text)
                        start = max(0, size - suffix_length)
                        end = size - 1
                    if start >= size or start < 0 or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    end = min(end, size - 1)
                    status = 206

                content_length = end - start + 1
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(content_length))
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                self.send_header("Accept-Ranges", "bytes")
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Cache-Control", "private, max-age=3600")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(path, "rb") as file:
                    file.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk = file.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (OSError, BrokenPipeError, ConnectionResetError, ValueError):
                return
            return

        if request_path == "/api/job-stream":
            if not self._authorized(allow_query=True):
                self._json(401, {"error": "访问令牌无效"})
                return
            query = parse_qs(urlsplit(self.path).query)
            raw_request_id = (query.get("request_id") or [""])[0]
            request_id = re.sub(r"[^A-Za-z0-9._:-]", "-", raw_request_id)[:180]
            session_id = self._normalize_session_id((query.get("session") or [""])[0])
            if not request_id:
                self._json(400, {"error": "缺少request_id"})
                return
            try:
                revision = max(0, int((query.get("after") or ["0"])[0]))
                text_offset = max(0, int((query.get("offset") or ["0"])[0]))
            except (TypeError, ValueError):
                self._json(400, {"error": "任务流参数无效"})
                return

            request_key = f"{session_id}:{request_id}"
            if self._job_snapshot(request_key, text_offset=text_offset) is None:
                self._json(404, {"error": "任务不存在或服务刚刚重启", "state": "missing"})
                return

            self._start_stream()
            try:
                while True:
                    snapshot = self._job_wait_snapshot(
                        request_key,
                        after_revision=revision,
                        text_offset=text_offset,
                        wait_seconds=10.0,
                    )
                    if snapshot is None:
                        self._event(
                            {
                                "type": "missing",
                                "error": "任务不存在或服务刚刚重启",
                                "state": "missing",
                            }
                        )
                        return

                    state = str(snapshot.get("state", "queued"))
                    current_revision = int(snapshot.get("revision", 0) or 0)
                    text_delta = str(snapshot.get("text_delta", ""))
                    changed = (
                        current_revision > revision
                        or bool(text_delta)
                        or bool(snapshot.get("reset_text"))
                        or state in {"done", "error", "cancelled"}
                    )
                    if changed:
                        self._event({"type": "job", "job": snapshot})
                        revision = max(revision, current_revision)
                        text_offset = max(0, int(snapshot.get("text_length", text_offset) or 0))
                    else:
                        self._event({"type": "heartbeat", "time": time.time()})

                    if state in {"done", "error", "cancelled"}:
                        return
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

        if request_path == "/api/job":
            if not self._authorized(allow_query=True):
                self._json(401, {"error": "访问令牌无效"})
                return
            query = parse_qs(urlsplit(self.path).query)
            raw_request_id = (query.get("request_id") or [""])[0]
            request_id = re.sub(r"[^A-Za-z0-9._:-]", "-", raw_request_id)[:180]
            session_id = self._normalize_session_id((query.get("session") or [""])[0])
            if not request_id:
                self._json(400, {"error": "缺少request_id"})
                return
            try:
                after_revision = max(0, int((query.get("after") or ["0"])[0]))
                wait_ms = max(0, min(25_000, int((query.get("wait_ms") or ["0"])[0])))
                text_offset = (
                    max(0, int((query.get("offset") or ["0"])[0]))
                    if "offset" in query
                    else None
                )
            except (TypeError, ValueError):
                self._json(400, {"error": "任务轮询参数无效"})
                return
            request_key = f"{session_id}:{request_id}"
            if wait_ms:
                snapshot = self._job_wait_snapshot(
                    request_key,
                    after_revision=after_revision,
                    text_offset=text_offset,
                    wait_seconds=wait_ms / 1000,
                )
            else:
                snapshot = self._job_snapshot(request_key, text_offset=text_offset)
            if snapshot is None:
                self._json(404, {"error": "任务不存在或服务刚刚重启", "state": "missing"})
                return
            self._json(200, snapshot)
            return

        if request_path == "/api/version":
            payload: dict[str, object] = {
                "app_name": "彦博 AI",
                "app_version": "1.0.0",
                "model_name": DISPLAY_NAME,
                "minimum_app_version": "1.0.0",
                "force_update": False,
                "android_download_url": "",
                "ios_download_url": "",
                "release_notes": [],
            }
            try:
                with open(MOBILE_UPDATE_PATH, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if isinstance(loaded, dict):
                    payload.update(loaded)
            except (OSError, ValueError, TypeError):
                pass
            payload["model_name"] = DISPLAY_NAME
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if request_path == "/api/auth-check":
            if not self._authorized(allow_query=True):
                self._json(401, {"error": "访问令牌无效"})
                return
            self._json(200, {"ok": True})
            return

        if request_path == "/api/status":
            body = json.dumps(
                {
                    "ok": True,
                    "model": DISPLAY_NAME,
                    "backend": self.engine_pool.status(),
                    "modes": {
                        mode: self.engine_pool.label_for(mode)
                        for mode in ("fast", "thinking", "expert")
                    },
                    "auth_required": bool(self.access_token),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        stream_started = False
        try:
            request_path = self.path.split("?", 1)[0]
            payload = self._read_payload()

            if request_path in {"/chat-job", "/chat-image-job"}:
                if not self._authorized_payload(payload):
                    self._json(401, {"error": "访问令牌无效"})
                    return
                session_id = self._normalize_session_id(payload.get("session_id"))
                mode = self.engine_pool.normalize(payload.get("mode"))
                request_id = self._request_id(payload)
                request_key = f"{session_id}:{request_id}"
                image_bytes = b""
                filename = str(payload.get("filename", "图片"))[:180]
                if request_path == "/chat-image-job":
                    image_bytes = self._decode_image(str(payload.get("image", "")))

                job_payload = dict(payload)
                job_payload.pop("token", None)
                job_payload.pop("session_id", None)
                job_payload.pop("image", None)
                created = False
                cached = self._cached_result(request_key)
                with self.job_lock:
                    job = self.request_jobs.get(request_key)
                    if job is None:
                        if cached is not None:
                            text, ocr = self._cached_job_payload(cached)
                            job = {
                                "request_id": request_id,
                                "state": "done",
                                "mode": mode,
                                "stage": "回答已完成",
                                "text": text,
                                "ocr": ocr,
                                "error": "",
                                "revision": 1,
                            }
                        else:
                            job = {
                                "request_id": request_id,
                                "state": "queued",
                                "mode": mode,
                                "stage": "任务已提交，电脑端正在准备……",
                                "text": "",
                                "ocr": None,
                                "error": "",
                                "revision": 1,
                            }
                            created = True
                        self.request_jobs[request_key] = job
                    self.job_accessed[request_key] = time.monotonic()
                    self._prune_jobs()

                if created:
                    threading.Thread(
                        target=self._run_generation_job,
                        args=(
                            request_key,
                            request_id,
                            session_id,
                            mode,
                            job_payload,
                            image_bytes,
                            filename,
                        ),
                        daemon=True,
                        name=f"yanbo-job-{request_id[-24:]}",
                    ).start()
                snapshot = self._job_snapshot(request_key) or {"state": "queued", "request_id": request_id}
                self._json(202 if snapshot.get("state") in {"queued", "running"} else 200, snapshot)
                return

            if request_path == "/api/job-cancel":
                if not self._authorized_payload(payload):
                    self._json(401, {"error": "访问令牌无效"})
                    return
                session_id = self._normalize_session_id(payload.get("session_id"))
                request_id = self._request_id(payload)
                request_key = f"{session_id}:{request_id}"
                self._job_update(
                    request_key,
                    state="cancelled",
                    stage="已停止生成",
                    error="",
                )
                self._json(200, {"ok": True, "state": "cancelled"})
                return

            if request_path == "/reset":
                if not (self._authorized() or self._authorized_payload(payload)):
                    self._json(401, {"error": "访问令牌无效"})
                    return
                session_id = self._normalize_session_id(payload.get("session_id")) if payload.get("session_id") else self._session_id()
                prefix = session_id + ":"
                with self.cache_lock:
                    self.session_states.pop(session_id, None)
                    self.session_accessed.pop(session_id, None)
                    for request_key in [key for key in self.request_results if key.startswith(prefix)]:
                        self.request_results.pop(request_key, None)
                        self.request_accessed.pop(request_key, None)
                with self.job_lock:
                    for request_key in [key for key in self.request_jobs if key.startswith(prefix)]:
                        self.request_jobs.pop(request_key, None)
                        self.job_accessed.pop(request_key, None)
                self._json(200, {"ok": True})
                return

            if request_path not in {"/chat-stream", "/chat-image-stream"}:
                self._json(404, {"error": "Not found"})
                return
            if not self._authorized():
                self._json(401, {"error": "访问令牌无效，请在应用设置中重新保存远程访问配置。"})
                return

            session_id = self._session_id()
            mode = self.engine_pool.normalize(payload.get("mode"))
            request_id = self._request_id(payload)
            request_key = f"{session_id}:{request_id}"
            image_bytes = b""
            filename = "图片"
            message = str(payload.get("message", ""))
            if request_path == "/chat-image-stream":
                image_bytes = self._decode_image(str(payload.get("image", "")))
                filename = str(payload.get("filename", "图片"))[:180]

            self._start_stream()
            stream_started = True
            cached = self._cached_result(request_key)
            if cached is not None:
                self._replay_result(cached, mode)
                return

            profile = self.engine_pool.profile_for(mode)
            mode_name = profile.display_name
            connected = self._try_event(
                {"type": "stage", "text": f"正在连接{mode_name}……", "mode": mode}
            )
            mode_lock = self.engine_pool.lock_for(mode)
            while not mode_lock.acquire(timeout=5):
                if connected:
                    connected = self._try_event(
                        {"type": "heartbeat", "text": f"{mode_name}正在准备回答", "time": time.time()}
                    )

            try:
                cached = self._cached_result(request_key)
                if cached is not None:
                    self._replay_result(cached, mode)
                    return

                engine, connected = self._await_task(
                    lambda: self.engine_pool.get(mode),
                    connected,
                    f"正在加载{mode_name}",
                )
                self._load_session(engine, session_id, payload)
                events: list[dict] = []

                if request_path == "/chat-stream":
                    if connected:
                        connected = self._try_event(
                            {"type": "stage", "text": f"{mode_name}正在组织回答……", "mode": mode}
                        )
                    iterator = engine.stream_reply(
                        message,
                        max_new_tokens=profile.text_max_tokens,
                        temperature=profile.text_temperature,
                        response_mode=mode,
                    )
                    connected = self._relay_generation(iterator, events, connected)
                else:
                    if connected:
                        connected = self._try_event(
                            {"type": "stage", "text": "正在识别图片文字……", "mode": mode}
                        )
                    result, connected = self._await_task(
                        lambda: self._recognize_for_request(engine, image_bytes),
                        connected,
                        "正在识别图片文字",
                    )
                    if result.text:
                        ocr_event = {
                            "type": "ocr",
                            "text": result.text,
                            "confidence": result.confidence,
                            "line_count": len(result.lines),
                            "width": result.width,
                            "height": result.height,
                        }
                        events.append(ocr_event)
                        if connected:
                            connected = self._try_event(ocr_event)
                            connected = self._try_event(
                                {"type": "stage", "text": f"识别完成，{mode_name}正在分析……", "mode": mode}
                            ) and connected
                    elif connected:
                        connected = self._try_event(
                            {"type": "stage", "text": f"未识别到文字，{mode_name}正在直接分析原图……", "mode": mode}
                        )
                    iterator = engine.stream_image_reply(
                        image_bytes=image_bytes,
                        user_text=message,
                        filename=filename,
                        max_new_tokens=profile.image_max_tokens,
                        temperature=profile.image_temperature,
                        ocr_result=result,
                        response_mode=mode,
                    )
                    connected = self._relay_generation(iterator, events, connected)

                self._save_session(engine, session_id)
                self._store_result(request_key, {"events": events, "mode": mode})
                if connected:
                    self._try_event({"type": "done", "model": DISPLAY_NAME, "mode": mode})
            finally:
                mode_lock.release()
        except Exception as exc:
            if stream_started:
                self._try_event({"type": "error", "error": str(exc)})
            else:
                self._json(400, {"error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"启动 {DISPLAY_NAME} 网页聊天")
    parser.add_argument("--mode", choices=["auto", "native", "fallback"], default="auto")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--require-remote-token",
        action="store_true",
        help="要求聊天与重置接口携带remote_access.json中的访问令牌",
    )
    args = parser.parse_args()

    stop_stale_web_servers(args.host, args.port)
    print(f"正在启动 {DISPLAY_NAME}……")
    ChatHandler.engine_pool = ModeEnginePool(server_mode=args.mode)
    thinking_engine = ChatHandler.engine_pool.get("thinking")
    ChatHandler.access_token = (
        load_remote_access_config()["access_token"] if args.require_remote_token else ""
    )
    html = HTML_TEMPLATE.replace("__DISPLAY_NAME__", DISPLAY_NAME).replace(
        "__BACKEND_INFO__", thinking_engine.backend_info
    )
    ChatHandler.html = html.encode("utf-8")
    server = StrictThreadingHTTPServer((args.host, args.port), ChatHandler)
    cache_key = re.sub(r"[^A-Za-z0-9_-]", "-", DISPLAY_NAME)
    timestamp = int(time.time())
    local_url = f"http://127.0.0.1:{args.port}/?version={cache_key}&t={timestamp}"
    if args.host in {"0.0.0.0", "::"}:
        lan_url = f"http://{get_lan_ip()}:{args.port}/?version={cache_key}&t={timestamp}"
        print(f"{DISPLAY_NAME} 手机服务已启动：{lan_url}")
        print("请让手机与电脑连接同一个 Wi-Fi，再用手机浏览器打开上面的地址。")
    else:
        lan_url = local_url
        print(f"{DISPLAY_NAME} 网页聊天已启动：{local_url}")
    print("可以点击＋上传图片，也可以直接把截图粘贴到网页。按 Ctrl+C 停止。")

    # 快速模式首次使用时再创建轻量客户端，不再预加载第二套本地模型。
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open_new_tab(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
