import re,sys
src,dst=sys.argv[1],sys.argv[2]
s=open(src,encoding="utf-8").read()
i=s.rindex("<script>")+len("<script>"); j=s.rindex("</script>")
body=s[i:j]
out=[];cur=""
for ln in body.split("\n"):
    t=ln.strip()
    if not t or t.startswith("//") or t.startswith("/*") and t.endswith("*/"): continue
    t=re.sub(r"(?<=[;{])\s+//\s.*$","",t)
    assert "//" not in t.replace("://",""), t
    cur=(cur+" "+t).strip()
    if len(cur)>700 and t[-1] in ";{},": out.append("  "+cur); cur=""
if cur: out.append("  "+cur)
s=s[:i]+"\n"+"\n".join(out)+"\n"+s[j:]
open(dst,"w",encoding="utf-8").write(s)
print(len(s.splitlines()),"lines")
