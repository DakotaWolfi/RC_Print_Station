"""Optional, separately scheduled slogan cache replenishment."""
import argparse
from itertools import product
import json
import logging
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener

from station_config import load as station_settings
from slogan_store import CACHE, LIMIT, OFFLINE, SloganStore, utc_day

LOG = logging.getLogger(__name__)
URL = "https://api.openai.com/v1/responses"
MAX_OUTPUT = 2400
MAX_BODY = 262_144
BATCH = 50

# Models select pairings of vetted bilingual clauses. Free-form model output
# can never reach the display, even if the provider disregards the prompt.
STARTS = (
    ("Gute Dinge bleiben länger", "Good things last longer"),
    ("Die Werkbank hat Geduld", "The workbench has patience"),
    ("Alte Technik hat Charakter", "Old technology has character"),
    ("Gute Ideen bleiben nützlich", "Good ideas stay useful"),
    ("Ein Comeback hat Charme", "A comeback has charm"),
    ("Die Werkstatt denkt weiter", "The workshop thinks ahead"),
    ("Die Zukunft mag Reparaturen", "The future likes repairs"),
    ("Neugier gehört zur Werkstatt", "Curiosity belongs in the workshop"),
    ("Kleine Reparaturen zählen", "Small repairs count"),
    ("Technik darf Geschichte haben", "Technology can have a history"),
    ("Die Werkbank bleibt neugierig", "The workbench stays curious"),
    ("Auch morgen zählt Sorgfalt", "Care still matters tomorrow"),
    ("Ein zweites Leben zählt", "Second lives count"),
    ("Wiederverwenden lohnt sich", "Reuse pays off"),
    ("Ein Kratzer erzählt Geschichte", "A scratch tells a story"),
    ("Die zweite Runde hat Stil", "Second chances have style"),
    ("Ein Gerät kann lange bleiben", "An appliance can stay for years"),
    ("Der Alltag mag Vertrautes", "Daily life likes familiar things"),
    ("Heute ist Platz für Ideen", "Today has room for ideas"),
    ("Die Werkbank mag Klassiker", "The workbench likes classics"),
)
ENDS = (
    ("der Schrott kann warten.", "scrap can wait."),
    ("das spart gute Rohstoffe.", "that saves materials."),
    ("ein zweites Leben lohnt sich.", "a second life is worth it."),
    ("die Geschichte geht weiter.", "the story goes on."),
    ("der Kaffee läuft schon.", "the coffee is already brewing."),
    ("Ressourcen haben Zukunft.", "materials have a future."),
    ("Vertrautes kommt zurück.", "familiar things return."),
    ("mehr Zeit, weniger Abfall.", "more time, less waste."),
    ("das Comeback zählt.", "the comeback counts."),
    ("die Ideen bleiben im Kreis.", "ideas stay in circulation."),
    ("das nächste Kapitel wartet.", "the next chapter awaits."),
    ("weniger muss ersetzt werden.", "fewer things need replacing."),
    ("gute Technik bleibt im Spiel.", "good tech stays in play."),
    ("mehr bleibt im Gebrauch.", "more stays in use."),
    ("die Werkbank ist bereit.", "the workbench is ready."),
    ("Geduld hat ihren Platz.", "patience has a place here."),
    ("Platz für eine zweite Runde.", "room for another round."),
    ("ein paar Jahre mehr zählen.", "a few more years matter."),
    ("auch Patina hat Charme.", "even patina has charm."),
    ("Langlebigkeit hat Stil.", "longevity has style."),
)
SCHEMA = {"type":"object","properties":{"pairs":{"type":"array","items":{
    "type":"object","properties":{"first":{"type":"integer"},"last":{"type":"integer"}},
    "required":["first","last"],"additionalProperties":False}}},
    "required":["pairs"],"additionalProperties":False}
SAFE_PAIRS = {(a,b):tuple(f"{first} – {last}" for first,last in zip(STARTS[a],ENDS[b]))
              for a,b in product(range(len(STARTS)),range(len(ENDS)))}
# Latin-9 does not have an en dash. Emit a short separator that renders cleanly.
SAFE_PAIRS = {indices:tuple(s.replace(" – "," · ") for s in texts)
              for indices,texts in SAFE_PAIRS.items()
              if all(len(s)<=LIMIT for s in texts) and texts not in OFFLINE}


def prompt(count):
    # Random clause order and a small unrelated nonce encourage varied pairings.
    ids = [list(enumerate(clauses)) for clauses in (STARTS,ENDS)]
    for group in ids:
        random.SystemRandom().shuffle(group)
    return (f"Return exactly {count} different repair-cafe slogan pairings in a JSON object. "
            'Use {"pairs":[{"first":0,"last":1}]} with integer IDs only. Match complementary '
            "opening and ending clauses from the two lists. Avoid awkward repetition. "
            "Creative seed "+os.urandom(5).hex()+". Clauses: "+json.dumps(ids,ensure_ascii=False))


def validate(content, count):
    doc = json.loads(content)
    if not isinstance(doc,dict) or set(doc)!={"pairs"} or not isinstance(doc["pairs"],list):
        raise ValueError("Invalid slogan schema")
    if len(doc["pairs"])!=count:
        raise ValueError("Incomplete slogan batch")
    seen=set()
    accepted=[]
    for row in doc["pairs"]:
        if not isinstance(row,dict) or set(row)!={"first","last"}:
            continue
        key=(row["first"],row["last"])
        if any(type(index) is not int for index in key) or key not in SAFE_PAIRS or key in seen:
            continue
        seen.add(key)
        accepted.append(SAFE_PAIRS[key])
    return accepted


class RefuseRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def openai(store, key, model, day_requests, day_tokens, *, request=build_opener(RefuseRedirect()).open):
    body=json.dumps({"model":model,"input":prompt(BATCH),"store":False,
                     "max_output_tokens":MAX_OUTPUT,
                     "text":{"format":{"name":"repair_slogan_pairs","type":"json_schema",
                                       "strict":True,"schema":SCHEMA}}}).encode()
    # Conservative reserve including maximum completion, UTF-8 request bytes
    # and framing margin. A timed-out request keeps its reserve for the day.
    estimate=len(body)+MAX_OUTPUT+256
    day=utc_day()
    if not store.reserve(day,day_requests,day_tokens,estimate):
        return []
    req=Request(URL,data=body,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    with request(req,timeout=15) as response:
        raw=response.read(MAX_BODY+1)
    if len(raw)>MAX_BODY:
        raise ValueError("Slogan response too large")
    reply=json.loads(raw)
    used=(reply.get("usage") or {}).get("total_tokens")
    if type(used) is int and 0<=used<=1_000_000:
        store.settle(day,estimate,used)
    if reply.get("status")!="completed":
        raise ValueError("Incomplete model response")
    texts=[part["text"] for item in reply.get("output",[]) if item.get("type")=="message"
           for part in item.get("content",[]) if part.get("type")=="output_text"]
    if len(texts)!=1:
        raise ValueError("Missing slogan batch")
    return validate(texts[0],BATCH)


def local(executable, weights, timeout, *, runner=subprocess.run):
    """Limit one CPU thread; the separate unit provides the RSS and CPU cap."""
    ids=" | ".join(json.dumps(str(i)) for i in range(len(STARTS)))
    grammar=(
        'root ::= "{" ws "\\"pairs\\"" ws ":" ws "[" ws item (ws "," ws item)* ws "]" ws "}"\n'
        'item ::= "{" ws "\\"first\\"" ws ":" ws idx ws "," ws "\\"last\\"" ws ":" ws idx ws "}"\n'
        f'idx ::= {ids}\nws ::= [ \\t\\n]*'
    )
    text=prompt(8)
    with tempfile.TemporaryFile() as output:
        runner(["nice","-n","15","prlimit","--as=1610612736","--",executable,"--model",weights,"--threads","1",
                "--threads-batch","1","--ctx-size","2048","--n-predict","320",
                "--temp","0.7","--no-display-prompt","--simple-io","--single-turn",
                "--no-warmup","--grammar",grammar,"--prompt",text],
               stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.DEVNULL,timeout=timeout,
               check=True,env={"PATH":os.defpath,"HOME":str(Path.home()),"LC_ALL":"C.UTF-8"})
        output.seek(0)
        data=output.read(MAX_BODY+1).decode()
    # Runtime status lines can appear before or after the grammar output.
    if len(data)>MAX_BODY or "{" not in data or "}" not in data:
        raise ValueError("Incomplete local generation")
    return validate(data[data.index("{"):data.rindex("}")+1],8)


def bounded(env, name, default, lo, hi):
    return max(lo,min(hi,int(env.get(name,default))))


def replenish(store, env):
    provider=env.get("FMI_SLOGAN_PROVIDER","off").lower()
    if provider=="off" or station_settings()["professional"]:
        return
    if provider not in ("openai","local"):
        raise ValueError("Unknown slogan provider")
    key=env.get("OPENAI_API_KEY","")
    if provider=="openai" and not key:
        return
    interval=bounded(env,"FMI_SLOGAN_INTERVAL",1800,300,86400)
    if store.remaining()>=12 or not store.schedule(provider,interval,int(time.time())):
        return
    if provider=="openai":
        pairs=openai(store,key,env.get("FMI_OPENAI_MODEL","gpt-5.4-mini"),
                     bounded(env,"FMI_OPENAI_DAILY_REQUESTS",4,0,48),
                     bounded(env,"FMI_OPENAI_DAILY_TOKENS",40000,0,250000))
    else:
        weights=env.get("FMI_LLAMA_MODEL","")
        if not weights or not Path(weights).is_file():
            raise ValueError("Local model file missing")
        pairs=local(env.get("FMI_LLAMA_CLI","/usr/local/bin/llama-cli"),weights,
                    bounded(env,"FMI_LLAMA_TIMEOUT",90,10,110))
    store.add(pairs,provider)
    LOG.info("Slogan provider %s accepted %d safe pairings",provider,len(pairs))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",type=Path,default=CACHE)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        replenish(SloganStore(args.cache),os.environ)
    except Exception as exc:
        # Do not print HTTP bodies, commands, model output or exception messages.
        LOG.warning("Slogan replenishment deferred (%s). Offline catalogue remains available.",type(exc).__name__)


if __name__=="__main__":
    main()
