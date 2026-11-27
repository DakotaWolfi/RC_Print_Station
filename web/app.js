"use strict";
const $ = id => document.getElementById(id);
const main = $("main"), statusbar = $("status"), dialog = $("dialog");
const tab = [...crypto.getRandomValues(new Uint8Array(16))].map(x => x.toString(16).padStart(2,"0")).join("");
const commandId = () => [...crypto.getRandomValues(new Uint8Array(16))].map(x => x.toString(16).padStart(2,"0")).join("");
const app = {state:null, dictionary:{}, csrf:"", nav:[], view:"work", online:false, note:"", busy:false,
             input:null, loaded:null, report:null, pdf:null, people:[], items:[], slots:0, locale:"de", taps:[]};
const active = () => ["guide","waiting","review"].includes(app.state?.draft?.stage);
const leisure = () => app.state && !app.state.settings.professional && !active();
const lang = () => app.state?.language || app.locale;
const t = (key, values={}) => (lang()==="en" ? app.dictionary[key] || key : key)
    .replace(/\{(\w+)\}/g,(whole,key) => values[key] ?? whole);
const ref = () => ({draft:app.state.draft.id,version:app.state.draft.version});
const node = (tag, cls, text) => {
    const result = document.createElement(tag);
    if (cls) result.className = cls;
    if (text !== undefined) result.textContent = text;
    return result;
};
const replace = (parent,...children) => {
    parent.textContent="";
    parent.append(...children);
};
const action = (title, fn, primary=false) => {
    const button = node("button",primary ? "primary" : "",title);
    button.type = "button";
    button.onclick = fn;
    return button;
};
const B = (key,fn,primary) => action(t(key),fn,primary);
const group = (...items) => {
    const container = node("div","grid");
    container.append(...items);
    return container;
};
const title = key => main.append(node("h1","",t(key)));
const para = (text, cls="") => main.append(node("p",cls,text));
const setStatus = () => {
    statusbar.classList.toggle("stale", !app.online);
    const receiver = app.state?.receiver;
    statusbar.textContent = app.note ? t(app.note) : !app.csrf ? "" : !app.online ?
        t("Verbindung zur Station unterbrochen.") : receiver ?
        "BENNING · " + t(receiver.detail || ({
            waiting:"Verbunden",receiving:"Empfang läuft ...",imported:"Import gespeichert",
            disconnected:"Nicht verbunden",searching:"Suche Tester / USB",simulation:"Simulation",file:"Datei"
        })[receiver.state] || receiver.state) : "";
    $("home").ariaLabel = t("Startseite");
    $("back").ariaLabel = t("Zurück");
    $("settings").ariaLabel = t("Einstellungen");
    $("language").textContent = lang()==="de" ? "DE / EN" : "EN / DE";
    document.documentElement.lang = lang();
    if(app.input?.feedback) {
        const message=app.input.stale ? "Der Entwurf hat sich geändert." :
            !app.online ? "Verbindung zur Station unterbrochen." :
            app.note==="Bitte warten ..." ? "" : app.note;
        app.input.feedback.textContent=message ? t(message) : "";
    }
};
async function http(path, body) {
    const control = new AbortController();
    const timer = setTimeout(() => control.abort(), 4500);
    try {
        const options = {cache:"no-store", credentials:"same-origin", signal:control.signal};
        if (body !== undefined) Object.assign(options,{method:"POST",body:JSON.stringify(body),
            headers:{"Content-Type":"application/json","X-CSRF-Token":app.csrf}});
        const response = await fetch(path,options);
        const data = await response.json();
        if (!response.ok || data.ok===false) {
            const error = new Error(data.error || "Aktion fehlgeschlagen.");
            error.code = response.status;
            throw error;
        }
        return data;
    } finally { clearTimeout(timer); }
}
const query = (op,args={}) => http("/api/command",{op,args,tab}).then(answer => answer.data);
function loginScreen() {
    $("home").hidden=$("back").hidden=$("settings").hidden=true;
    replace(main);
    title("FMI Printstation");
    para(t("Mit dem lokalen Stationspasswort anmelden."));
    const form = node("form","card");
    const input = field(form,"Passwort","",{type:"password",autocomplete:"current-password",required:true,maxLength:128});
    const submit = node("button","primary",t("Anmelden"));
    form.append(submit);
    form.onsubmit=async event => {
        event.preventDefault();
        submit.disabled=true;
        try {
            app.csrf=(await http("/api/login",{password:input.value})).csrf;
            app.note="";
            await poll(true);
        } catch(error) { app.note=error.code ? error.message : "Verbindung zur Station unterbrochen."; setStatus(); }
        finally { input.value=""; submit.disabled=false; }
    };
    main.append(form);
    setStatus();
}
async function poll(force=false) {
    if (!app.csrf || app.polling || app.busy && !force) return;
    app.polling=true;
    try {
        const next = await query("state");
        const changed = !app.state || JSON.stringify(next)!==JSON.stringify(app.state);
        if (app.state && app.state.epoch!==next.epoch) {
            app.note="Die Station wurde neu gestartet.";
            app.loaded=app.pdf=null;
        }
        app.online=true;
        if(app.note==="Verbindung zur Station unterbrochen.") app.note="";
        app.state=next;
        if ((["pet","novelty","play","workshop"].includes(app.view)) && !leisure()) {
            app.view="work"; app.nav=[];
            if (dialog.open) dialog.close();
        }
        if (app.input && app.input.draft.id!==next.draft?.id) {
            app.input.stale=true;
        }
        const editing = main.contains(document.activeElement) &&
            ["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName);
        if (force || (changed && !editing && !app.input && !dialog.open && app.view!=="play")) render();
    } catch(error) {
        app.online=false;
        if (error.code===401) {
            app.csrf=""; app.state=app.input=null;
            if (dialog.open) dialog.close();
            loginScreen();
        }
    } finally { app.polling=false; setStatus(); }
}
async function cmd(op,args={},options={}) {
    if (!app.online || !app.state || app.busy) return false;
    app.busy=true;
    app.note="Bitte warten ..."; setStatus();
    try {
        const data=(await http("/api/command",{op,args,id:commandId(),epoch:app.state.epoch,tab})).data;
        app.note="";
        if (options.done) options.done(data);
        return true;
    } catch(error) {
        app.note=error.code ? error.message : "Verbindung zur Station unterbrochen. Aktion prüfen.";
        if (!error.code || error.code===503) app.online=false;
        return false;
    } finally {
        app.busy=false;
        if (options.poll!==false) await poll(true);
        setStatus();
    }
}
const draft = (op,args={}) => cmd(op,{...(app.confirmedRef || ref()),...args});
function navigate(view,remember=true) {
    if (app.input || dialog.open) return;
    if (remember && view!==app.view) app.nav.push(app.view);
    app.view=view; app.note=""; window.scrollTo(0,0); render();
}
function back() {
    if (app.nav.length) return navigate(app.nav.pop(),false);
    if (app.view!=="work") return navigate("work",false);
    const stage=app.state?.draft?.stage;
    if (stage==="guide") return draft("guide.back");
    if (stage==="review" || stage==="waiting") return draft("review.back");
    navigate("home",false);
}
function confirm(message,fn) {
    if (dialog.open) return;
    const observed=app.state?.draft ? ref() : null;
    replace(dialog,node("h2","",t("Bestätigen")),node("p","",t(message)),
        group(B("Abbrechen",()=>dialog.close()),B("Bestätigen",()=>{dialog.close();app.confirmedRef=observed;try{fn();}finally{app.confirmedRef=null;}},true)));
    dialog.showModal();
}
function help(message) {
    replace(dialog,node("h2","",t("Hilfe")),node("p","",t(message)),B("Schliessen",()=>dialog.close()));
    dialog.showModal();
}
function field(parent,caption,value,props={}) {
    const label=node("label","",t(caption));
    const control=node("input");
    Object.assign(control,props);
    control.value=value ?? "";
    label.append(control); parent.append(label);
    return control;
}
function options(parent,caption,values,index,change,raw=false) {
    const label=node("label","",t(caption)), select=node("select");
    select.append(...values.map((value,i)=>Object.assign(node("option","",raw ? value : t(value)),{value:i})));
    select.selectedIndex=index;
    select.onchange=()=>change(select.selectedIndex);
    label.append(select); parent.append(label);
}
async function changeField(key,title,value,props={}) {
    if (!app.online || app.input || dialog.open) return;
    const d=app.state.draft, current={...ref()};
    const editor={draft:{...d},field:key,stale:false,timer:null};
    app.input=editor;
    const lease=(on)=>cmd("draft.editor",{active:on,draft:d.id,field:key},{poll:false});
    if (!await lease(true)) { app.input=null; return; }
    editor.timer=setInterval(()=>lease(true),5500);
    const form=node("form");
    const input=field(form,title,value,props);
    const feedback=node("p","badge");
    feedback.setAttribute("role","status");
    editor.feedback=feedback;
    form.append(feedback);
    const submit=node("button","primary",t("Übernehmen"));
    form.append(group(B("Abbrechen",()=>dialog.close()),submit));
    form.onsubmit=async event=>{
        event.preventDefault();
        if (editor.stale) { app.note="Der Entwurf hat sich geändert."; setStatus(); return; }
        submit.disabled=true;
        const ok=await cmd("draft.edit",{...current,previous:{[key]:value},changes:{[key]:input.value}},{poll:false});
        submit.disabled=false;
        if(ok) dialog.close();
        else setStatus();
    };
    dialog.onclose=async ()=>{
        clearInterval(editor.timer);
        app.input=null;
        dialog.onclose=null;
        await lease(false);
        await poll(true);
    };
    replace(dialog,form); dialog.showModal(); input.focus(); input.select();
}
const edit = (d,key,value) => draft("draft.edit",{previous:{[key]:d[key]},changes:{[key]:value}});
function home() {
    title("FMI Printstation"); para(t("Prüfprotokolle"),"badge");
    const d=app.state.draft, slogan=app.state.personality?.slogan;
    if (slogan && !active()) para(slogan[lang()==="en"?1:0]);
    const begin = mode => cmd("draft.new",{mode},{done:()=>app.view="work"});
    main.append(d && d.stage!=="report" ?
        group(B("Prüfung fortsetzen",()=>navigate("work"),true)) :
        group(B("Geführte Prüfung",()=>begin("guided"),true),B("Direkt",()=>begin("direct"))),
        group(B("Verlauf",history),B("Einstellungen",()=>navigate("settings"))));
}
function entry(d) {
    title("Prüfung erfassen"); para(t(d.mode==="guided"?"Geführte Prüfung":"Direkt"),"badge");
    const panel=node("section");
    panel.append(group(action(t("Prüfnummer")+" · "+(d.ticket || t("Eingeben")),
        ()=>changeField("ticket","Prüfnummer",d.ticket,{maxLength:32,inputMode:"text"})),
        action(t("Gerätebeschreibung")+" · "+(d.device || t("Eingeben")),
        ()=>changeField("device","Gerätebeschreibung",d.device,{maxLength:64}))),
        group(B("Vorlagen",templates),B("Prüfperson",()=>people("work")),
            action(t("Bericht: {language}",{language:app.state.report_language.toUpperCase()}),
                ()=>draft("language.report",{language:app.state.report_language==="en"?"de":"en"}))));
    options(panel,"Prüfart",["Eingangsprüfung","Zwischenprüfung","Ausgangsprüfung"],d.phase,i=>edit(d,"phase",i));
    main.append(panel,group(B("Prüfung beginnen",()=>draft("exam.start"),true),
        B("Vorhandene Messung",()=>draft("review.find")),
        B("Entwurf verwerfen",()=>confirm("Entwurf verwerfen?",()=>draft("draft.discard",{confirmed:true})))));
}
function art(key) {
    if(!key || key==="lcd") return;
    const image=node("img","guide");
    image.src="/art/g_"+key+(lang()==="en"?"_en":"")+".png";
    image.onerror=()=>{if(image.src.endsWith("_en.png")) image.src="/art/g_"+key+".png";else image.remove();};
    image.alt="BENNING ST 725"; main.append(image);
}
function guide(d,g) {
    title(g.title); para(t("Schritt {step} von 7  ·  BENNING ST 725 CH",{step:g.phase}),"badge");
    art(g.art); para(g.instruction[lang()]);
    if(g.step==="exam") {
        const panel=node("section");
        panel.append(group(action(t("Prüfperson")+(d.examiner && app.people.find(p=>p.id===d.examiner) ?
            " · "+app.people.find(p=>p.id===d.examiner).name : ""),()=>people("work")),
            action(t("Bemerkung")+(d.remarks?" · "+d.remarks:""),()=>changeField("remarks","Bemerkung",d.remarks,{maxLength:64}))));
        const values=["Offen","Ohne Befund","Mangel","Nicht geprüft"];
        options(panel,"Funktion",values,values.indexOf(g.functional),i=>draft("exam.function",{value:values[i]}));
        main.append(panel,group(B(g.stored&&!g.blocked?"Zum Import":"Unvollständig speichern",
            ()=>confirm(g.stored&&!g.blocked?"Zum Import":"Unvollständig speichern",()=>draft("exam.submit")),true)));
    } else {
        main.append(group(...g.choices.map((key,i)=>B(key,()=>draft("guide.choose",{step:g.step,choice:i}),
            i===0&&!["start","running","low_continue","energise","warnings"].includes(g.step)))));
    }
    main.append(group(B("Zurück",()=>draft("guide.back")),B("Hilfe",()=>help(g.help)),
        B("Abbrechen",()=>confirm("Prüfung abbrechen?",()=>draft("guide.cancel",{confirmed:true})))));
}
function importView(review) {
    const s=app.state;
    title(review?"Messung bestätigen":"Messung übertragen");
    if(!review) { art(s.import_art); para(t(s.import_body)); }
    if(s.wait_note) para(t(s.wait_note),"badge");
    if(s.receiver.detail) para(t(s.receiver.detail));
    const selected=s.selected;
    const brief = row => [row.slot,row.date,t(row.verdict),t(row.class || "")].filter(Boolean).join(" · ");
    if(review) {
        if(selected) {
            para(brief(selected),"badge");
            main.append(group(B("Messung bestätigen",()=>confirm("Messung bestätigen",
                ()=>draft("review.confirm",{record:selected.key})),true)));
        }
        const start=Math.min(app.slots, Math.max(0, Math.ceil(s.slots.length/12)-1))*12;
        main.append(group(...s.slots.slice(start,start+12).map(row=>action(brief(row),
            ()=>draft("review.select",{record:row.key})))));
        const pager=[];
        if(start>0) pager.push(B("Zurückblättern",()=>{app.slots--;render();}));
        if(start+12<s.slots.length) pager.push(B("Weitere",()=>{app.slots++;render();}));
        main.append(group(...pager));
    } else main.append(group(B("Vorhandene Messung",()=>draft("review.manual"))));
    main.append(group(B("Zurück",()=>draft("review.back"))));
}
async function read(op,args,done) {
    if(!app.online) return;
    try { done(await query(op,args)); }
    catch(error) { app.note=error.code ? error.message : "Verbindung zur Station unterbrochen."; setStatus(); }
}
function history() { navigate("history"); read("history",{},rows=>{app.history=rows;if(app.view==="history") render();}); }
function templates() { navigate("templates"); read("templates",{},items=>{app.items=items;if(app.view==="templates") render();}); }
function people(returnTo) { app.peopleReturn=returnTo; navigate("people"); refreshPeople(); }
function refreshPeople() { read("people",{},rows=>{app.people=rows;if(app.view==="people" || app.view==="work") render();}); }
function formDialog(caption,value,props,fn) {
    if(dialog.open) return;
    const form=node("form");
    const input=field(form,caption,value,props);
    if(props.type==="password") {
        let shown=false;
        const toggle=B("Anzeigen",()=>{shown=!shown;input.type=shown?"text":"password";toggle.textContent=t(shown?"Verbergen":"Anzeigen");});
        form.append(toggle);
    }
    form.append(group(B("Abbrechen",()=>dialog.close()),node("button","primary",t("Übernehmen"))));
    form.onsubmit=event=>{event.preventDefault();const value=input.value;input.value="";dialog.close();fn(value);};
    replace(dialog,form);dialog.showModal();input.focus();
}
function peopleView() {
    title("Prüfpersonen");
    const add=person=>formDialog("Prüfperson",person?.name,{maxLength:48,required:true},
        name=>cmd("person.save",{name,examiner:person?.id || null},{done:refreshPeople}));
    main.append(group(B("Neu",()=>add(null),true)));
    for(const p of app.people) {
        const card=node("section"), d=app.state.draft;
        card.append(node("strong","",p.name));
        const pick=B("Auswählen",()=>cmd("person.pick",{...ref(),examiner:p.id},{done:()=>app.view="work"}),true);
        pick.disabled=!p.active||!(d?.stage==="entry" || app.state.guide?.step==="exam");
        card.append(group(pick,B("Bearbeiten",()=>add(p)),
            B(p.active?"Deaktivieren":"Aktivieren",()=>confirm("Änderung bestätigen?",()=>
                cmd("person.active",{examiner:p.id,active:!p.active,confirmed:true},{done:refreshPeople})))));
        main.append(card);
    }
}
const verdicts={PASS:"BESTANDEN",FAIL:"NICHT BESTANDEN",unknown:"UNBEKANNT",partial:"UNVOLLSTÄNDIG",simulation:"SIMULATION"};
function showReport(id) {
    title("Prüfprotokoll");
    if (!id) return;
    const cacheKey=id+":"+lang();
    if(app.loaded!==cacheKey) {
        if(app.loading!==cacheKey) {
            app.loading=cacheKey; app.pdf=null;
            read("report.view",{report:id},report=>{app.loaded=cacheKey;app.report=report;render();}).finally(()=>{app.loading=null;});
        }
        return para(t("Bitte warten ..."));
    }
    const r=app.report;
    const kind=r.kind;
    para(t(verdicts[kind] || "UNBEKANNT"),"result "+kind.toLowerCase());
    const fields=node("section");
    for(const [name,value] of r.fields) fields.append(node("p","",t(name)+" · "+value));
    main.append(fields);
    for(const [name,value,limit,result,kind] of r.measurements) {
        para([name,value,limit,result].filter(Boolean).join(" · "),kind.toLowerCase());
    }
    for(const [name,value] of r.checks) para(t(name)+" · "+value);
    main.append(group(B("Beleg drucken",()=>confirm("Beleg jetzt drucken?",()=>cmd("report.print",{report:id,confirmed:true})),true),
        B("PDF / QR-Code",()=>cmd("report.qr",{report:id},{done:qr=>app.pdf=qr}))));
    for (const message of [app.state.print_note]) { if(message) para(t(message)); }
    if(app.pdf && /^https?:\/\//.test(app.pdf.url)) {
        const link=node("a","button",t("PDF öffnen"));
        link.href=app.pdf.url;link.rel="noopener noreferrer";link.target="_blank";main.append(link);
        const n=app.pdf.modules.length, canvas=node("canvas","qr");
        canvas.width=canvas.height=(n+8)*4; canvas.setAttribute("aria-label","PDF QR");
        const ctx=canvas.getContext("2d");
        ctx.fillStyle="#fff";ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.fillStyle="#000";
        app.pdf.modules.forEach((row,y)=>row.forEach((black,x)=>{if(black)ctx.fillRect((x+4)*4,(y+4)*4,4,4);}));
        main.append(canvas);
    }
}
const config = (key,value) => cmd("settings.save",{values:{[key]:value}});
function settings() {
    title("Einstellungen");
    const categories=[["Drucker","printer"],["WLAN","wifi"],["Anzeige","display"],["Prüfgerät","tester"],
        ["Prüfpersonen","people"],["Persönlichkeit","personality"],["System","system"]];
    main.append(group(...categories.map(([text,view])=>{
        const button=B(text,()=>view==="people" ? people("settings") : navigate(view));
        const icon=node("img","category-icon");
        icon.src="/icons/"+view+".svg"; icon.alt="";
        button.prepend(icon);
        button.classList.add("category");
        return button;
    })));
}
function settingsView(view) {
    const s=app.state,c=s.settings;
    function valueField(title,key,type="number",maxLength=15) {
        return action(t(title)+" · "+c[key],()=>formDialog(title,String(c[key]),{type:"text",inputMode:type==="number"?"numeric":"decimal",maxLength,required:true},
            v=>config(key,type==="number"&&/^[0-9]+$/.test(v)?Number(v):v)));
    }
    if(view==="printer") {
        title("Drucker"); main.append(group(valueField("IPv4-Adresse","printer_host","text"),valueField("TCP-Port","printer_port","number",5),
            B("TCP-Verbindung testen",()=>cmd("printer.probe")),
            B("Testbeleg drucken",()=>confirm("Beleg jetzt drucken?",()=>cmd("printer.test",{confirmed:true}))),
            B(c.graphic?"Kopf: Grafik":"Kopf: Text",()=>config("graphic",!c.graphic)),valueField("Papiervorschub","feed_mm","number",3)));
        for(const note of [s.print_note,s.probe_note]) if(note) para(t(note));
    } else if(view==="wifi") {
        title("WLAN"); para([s.wifi.ssid,s.wifi.ip,t(s.wifi.note || "")].filter(Boolean).join(" · "));
        const hotspot=s.wifi.ssid==="FMI-RC-Printstation";
        main.append(group(B("Netzwerke suchen",()=>cmd("wifi.scan"),true),
            B(hotspot?"Hotspot beenden":"FMI Hotspot starten",()=>confirm("Änderung bestätigen?",()=>
                cmd(hotspot?"wifi.stop":"wifi.hotspot",{confirmed:true})))));
        main.append(group(...s.wifi.networks.map(net=>action(net.name+" · "+net.signal+"% · "+t(net.security),
            ()=>{const join=password=>cmd("wifi.connect",{network:net.id,password});
                if(net.saved||net.security==="Offen") confirm("WLAN verbinden?",()=>join(""));
                else formDialog("Passwort","",{type:"password",maxLength:64},join);}))));
    } else if(view==="display") {
        title("Anzeige"); main.append(group(valueField("Helligkeit","brightness","number",3),valueField("Standby","standby","number",4)));
    } else if(view==="tester") {
        title("Prüfgerät"); para("BENNING ST 725 · "+(s.receiver.transport || s.receiver.source || s.receiver.mode));
        if(c.tester_mode) main.append(group(...[["auto","Automatisch"],["usb","USB-CSV"],["rs232","RS232-PRINT"],["file","Datei"],["simulation","Simulation"]]
            .map(([mode,text])=>B(text,()=>confirm("Änderung bestätigen?",()=>config("tester_mode",mode)),mode===c.tester_mode))));
    } else if(view==="personality") {
        title("Persönlichkeit");
        main.append(group(B(c.professional?"Professioneller Modus: Ein":"Professioneller Modus: Aus",
            ()=>config("professional",!c.professional),true)));
        if(leisure()) main.append(group(B("Werkstattwolf",()=>navigate("pet"))));
    } else if(view==="system") {
        title("System");
        main.append(group(B("Engineering-Modus",()=>navigate("info")),
            B("Abmelden",async()=>{try{await http("/api/logout",{});}finally{app.csrf="";app.state=null;loginScreen();}})));
        if(s.power.enabled) main.append(group(
            B("Jetzt neu starten",()=>confirm("Station neu starten?",()=>cmd("power.reboot",{confirmed:true}))),
            B("Jetzt ausschalten",()=>confirm("Station ausschalten?",()=>cmd("power.halt",{confirmed:true})))));
        if(s.power.note) para(t(s.power.note));
    }
}
function pet() {
    title("Werkstattwolf");
    const img=node("img","wolf"); img.alt=t("Werkstattwolf"); img.src="/wolf/idle.webp";
    const nap=setTimeout(()=>{if(img.isConnected) img.src="/wolf/sleep.webp";},18000);
    let origin=null, moved=false, paused=0;
    function motion(state,op) {
        if (Date.now()<paused || !leisure()) return;
        paused=Date.now()+850;
        clearTimeout(nap);
        img.src="/wolf/"+state+".webp";
        img.classList.add("reaction");
        if(op) cmd(op,{}, {poll:false});
        setTimeout(()=>{img.src="/wolf/idle.webp";img.classList.remove("reaction");},760);
    }
    img.draggable=false;
    img.onpointerdown=e=>{origin=[e.clientX,e.clientY];moved=false;img.setPointerCapture(e.pointerId);};
    img.onpointermove=e=>{if(origin&&!moved&&Math.hypot(e.clientX-origin[0],e.clientY-origin[1])>28){moved=true;motion("happy","personality.pet");}};
    img.onpointerup=()=>{if(origin&&!moved)motion("happy","personality.pet");origin=null;};
    img.onpointercancel=()=>{origin=null;};
    main.append(img);
    para(t(app.state.personality.pet_reply || ""));
    para(t("Streicheleinheiten")+": "+(app.state.personality.pets || 0));
    para(t("Fiktive Telemetrie: Werkstattlaune stabil."));
    main.append(group(B("Streicheln",()=>motion("happy","personality.pet")),
        B("Leckerli",()=>motion("treat","personality.treat")),B("Awoo",()=>motion("awoo")),
        B("Spassbeleg",()=>navigate("novelty")),B("Werkstattpause",()=>navigate("workshop"))));
    const counts=app.state.personality.achievements;
    if(counts && Object.keys(counts).length) {
        const panel=node("section");
        panel.append(node("h2","",t("Werkstatt-Meilensteine")));
        for(const [key,name,goal] of [["pets","Streicheleinheiten",10],["treats","Leckerli",5],
          ["prints","Gedruckte Prüfbelege",10],["exams","Dokumentierte Prüfungen",10],["switches","Sprachwechsel",5],
          ["seconds","Betriebsstunden",1],["engineering","Engineering-Aufrufe",3]]) {
            const value=key==="seconds"?Math.floor((counts[key] || 0)/3600):counts[key] || 0;
            panel.append(node("p","",(value>=goal?"✓ ":"")+t(name)+" · "+value+" / "+goal));
        }
        main.append(panel);
    }
}
function workshop() {
    title("Werkstattpause");
    if(!app.workshop) {
        para(t("Bitte warten ..."));
        http("/workshop.json").then(data=>{app.workshop=data;if(app.view==="workshop")render();})
            .catch(()=>{app.note="Verbindung zur Station unterbrochen.";setStatus();});
        return;
    }
    main.append(group(...Object.entries(app.workshop.messages).map(([name,message])=>B(name,()=>help(message))),
        B("FMI BIOS",()=>formDialog("FMI BIOS","help",{maxLength:24},command=>{
            const key=command.trim().toLowerCase();
            const cmds=app.workshop.terminal;
            help(Object.prototype.hasOwnProperty.call(cmds,key)?cmds[key]:"Unbekannter Spielbefehl. help zeigt die Auswahl.");
        })),B("Teetimer",()=>{
            app.tea=Date.now()+180000;
            render();
        })));
    if(app.tea) {
        const label=node("p","badge");
        main.append(label);
        const update=()=>{
            const remaining=Math.max(0,Math.ceil((app.tea-Date.now())/1000));
            label.textContent=t("Teetimer")+" · "+Math.floor(remaining/60)+":"+String(remaining%60).padStart(2,"0");
            if(remaining && label.isConnected) setTimeout(update,500);
        };
        update();
    }
    main.append(group(...["Pong","Snake","Breakout","Logo"].map(name=>B(name,()=>{app.game=name;navigate("play");}))));
}
function play() {
    title(app.game);
    const canvas=node("canvas","game");
    canvas.width=640;canvas.height=320;canvas.tabIndex=0;canvas.ariaLabel=app.game;
    main.append(canvas);
    const buttons=app.game==="Snake" ? [["←",[-1,0]],["↑",[0,-1]],["↓",[0,1]],["→",[1,0]]]
        .map(([symbol,move])=>[action(symbol,()=>{}),move]) : [];
    const restart=B("Neu starten",()=>{});
    main.append(group(...buttons.map(([button])=>button),restart));
    const setup=()=>{if(canvas.isConnected&&leisure())window.makeArcade(app.game,canvas,buttons,restart);};
    if(window.makeArcade) setup();
    else {
        const script=node("script");
        script.src="/arcade.js";script.onload=setup;document.head.append(script);
    }
}
function render() {
    if(!app.state) return;
    $("home").hidden=$("back").hidden=$("settings").hidden=false;
    replace(main);
    const s=app.state, d=s.draft;
    if(app.view==="work") {
        if(d?.stage==="entry") entry(d);
        else if(d?.stage==="guide") guide(d,s.guide);
        else if(d?.stage==="waiting"||d?.stage==="review") importView(d.stage==="review");
        else if(d?.stage==="report") showReport(s.report);
        else home();
    } else if(app.view==="home") home();
    else if(app.view==="settings") settings();
    else if(app.view==="history") {
        title("Verlauf");
        main.append(group(...(app.history || []).map(row=>action([row.ticket,row.device,row.created].filter(Boolean).join(" · "),
            ()=>{app.reportId=row.id;navigate("report");}))));
    } else if(app.view==="report") showReport(app.reportId);
    else if(app.view==="templates") {
        title("Vorlagen");
        main.append(group(...app.items.map(value=>action(value,()=>{edit(d,"device",value);navigate("work");}))));
    } else if(app.view==="people") peopleView();
    else if(app.view==="pet"&&leisure()) pet();
    else if(app.view==="workshop"&&leisure()) workshop();
    else if(app.view==="play"&&leisure()) play();
    else if(app.view==="novelty"&&leisure()) {
        title("Spassbeleg");para(t("SPASSBELEG · OHNE GÜLTIGKEIT"),"badge");
        main.append(group(...Object.entries({awoo:"Awoo Permit",pointless:"Certificate of Pointlessness",jank:"Certified Jank",
            engineer:"Emotional Support Engineer"}).map(([kind,name])=>action(name,()=>confirm("Spassbeleg drucken?",
                ()=>cmd("novelty.print",{kind,confirmed:true}))))));
        if(s.novelty_note) para(t(s.novelty_note));
    } else if(app.view==="info") {
        title("Engineering-Modus");
        main.append(group(B("Aktualisieren",()=>read("system.info",{},data=>{app.details=data;render();}),true)));
        if(app.details) for(const [name,value] of Object.entries(app.details.system || {})) para(name+" · "+value);
    } else settingsView(app.view);
    setStatus();
}
$("home").onclick=()=>{app.nav=[];navigate("home",false);};
$("back").onclick=back;
$("settings").onclick=()=>navigate("settings");
$("language").onclick=()=>{
    const language=lang()==="en"?"de":"en";
    if(app.state) config("language",language); else {app.locale=language;loginScreen();}
};
$("brand").onclick=()=>{
    const now=Date.now();
    app.taps=app.taps.filter(stamp=>now-stamp<3000).concat(now);
    if(app.taps.length>=5 && leisure()) {app.taps=[];navigate("pet");}
};
window.addEventListener("offline",()=>{app.online=false;setStatus();});
window.addEventListener("online",()=>poll(true));
async function start() {
    try { app.dictionary=await http("/locale.json"); } catch {}
    try { app.csrf=(await http("/api/session")).csrf; await poll(true); }
    catch { loginScreen(); }
    if(!app.state) loginScreen();
    setInterval(()=>poll(),1400);
}
start();
