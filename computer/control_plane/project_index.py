from __future__ import annotations
import re,hashlib,ast,os
from pathlib import Path
from coding import ROOT, safe_path
from .store import load_json,save_json,now

SKIP_DIRS = {'.git', '.venv', '__pycache__', '.cache', '.ai', '.pytest_cache', 'node_modules', 'logs'}
MAX_INDEX_FILE_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_BYTES = 1024 * 1024


def _runtime_file(path):
    return (any(part in SKIP_DIRS for part in path.parts)
            or path.name in {'.mcp_token', '.env'}
            or (path.name.startswith('.env.') and path.name != '.env.example'))


def _source_files(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS and not (base / name).is_symlink())
        for name in sorted(files):
            yield base / name


class ProjectIndex:
    def __init__(self):
        self.state=load_json("project-index.json", {"version":2,"files":{},"symbols":{},"dependencies":{},"updated_at":None})
        self.state.setdefault('dependencies', {})
    def refresh(self, paths=None):
        targets=[]
        if paths:
            for x in paths:
                p=safe_path(x, missing=True)
                if p.is_file(): targets.append(p)
                elif p.is_dir(): targets.extend(_source_files(p))
        else: targets=_source_files(ROOT)
        seen=set()
        for p in targets:
            try:
                rel=str(p.resolve().relative_to(ROOT.resolve()))
                if p.is_symlink() or _runtime_file(Path(rel)): continue
                stat=p.stat()
                prev=self.state['files'].get(rel)
                if stat.st_size > MAX_INDEX_FILE_BYTES: continue
                if prev and prev.get('mtime_ns')==stat.st_mtime_ns and prev.get('bytes')==stat.st_size:
                    seen.add(rel)
                    continue
                with p.open('rb') as stream:
                    prefix=stream.read(8192)
                    if b'\0' in prefix: continue
                    raw=prefix+stream.read(MAX_INDEX_FILE_BYTES+1-len(prefix))
                if len(raw)>MAX_INDEX_FILE_BYTES: continue
                data=raw.decode('utf-8',errors='replace')
                seen.add(rel)
            except Exception:
                continue
            sha=hashlib.sha256(data.encode()).hexdigest()
            if prev and prev.get('sha256')==sha:
                prev.update({'mtime_ns': stat.st_mtime_ns, 'bytes': stat.st_size, 'updated_at': now()})
                continue
            self.state['files'][rel]={"sha256":sha,"bytes":stat.st_size,"mtime_ns":stat.st_mtime_ns,"updated_at":now()}
            if p.suffix == '.py':
                try:
                    tree_ast=ast.parse(data)
                    imports=[n.names[0].name for n in ast.walk(tree_ast) if isinstance(n, ast.Import) and n.names] + [n.module for n in ast.walk(tree_ast) if isinstance(n, ast.ImportFrom) and n.module]
                except Exception:
                    imports=[]
            else: imports=[]
            syms=re.findall(r'^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)',data,re.M)
            self.state['symbols'][rel]=syms
            self.state.setdefault('dependencies', {})[rel]=sorted({x for x in imports if x})
        if not paths:
            for rel in set(self.state['files'])-seen:
                for key in ('files','symbols','dependencies'): self.state[key].pop(rel,None)
        self.state['updated_at']=now(); save_json('project-index.json',self.state); return self.summary()
    def search(self,q,limit=50):
        q=q.casefold(); out=[]
        for path,syms in self.state['symbols'].items():
            for s in syms:
                if q in s.casefold() or q in path.casefold(): out.append({"path":path,"symbol":s})
                if len(out)>=limit: return out
        return out
    def context_pack(self, query: str, limit_files: int = 12, max_bytes: int = 120000):
        q=str(query).casefold().strip(); scored=[]
        for path, meta in self.state.get('files',{}).items():
            symbols=self.state.get('symbols',{}).get(path,[])
            hay=(path+' '+' '.join(symbols)).casefold()
            score=sum(2 for tok in q.split() if tok and tok in path.casefold()) + sum(1 for tok in q.split() if tok and tok in hay)
            if score: scored.append((score,path))
        scored.sort(key=lambda x:(-x[0],x[1])); selected=[p for _,p in scored[:max(1,int(limit_files))]]
        budget=min(MAX_CONTEXT_BYTES,max(0,int(max_bytes)))
        snippets=[]; total=0
        for rel in selected:
            if total>=budget: break
            p=ROOT/rel
            try:
                p.resolve().relative_to(ROOT.resolve())
                if p.is_symlink() or _runtime_file(Path(rel)): continue
                with p.open('rb') as stream: raw=stream.read(budget-total)
                text=raw.decode('utf-8',errors='replace')
                text=text.encode('utf-8')[:budget-total].decode('utf-8',errors='ignore')
            except Exception: continue
            snippets.append({'path':rel,'score':next((s for s,r in scored if r==rel),0),'content':text}); total += len(text.encode())
            if total>=budget: break
        return {'query':query,'files':snippets,'bytes':total,'truncated':total>=budget}

    def summary(self): return {"files":len(self.state['files']),"symbol_files":len(self.state['symbols']),"dependency_files":len(self.state.get('dependencies',{})),"updated_at":self.state['updated_at']}
