(async () => {
    const sleep = ms => new Promise(done => setTimeout(done,ms));
    async function wait(test, desc) {
        for(let i=0;i<250;i++) {
            if (test()) return;
            await sleep(40);
        }
        throw new Error(desc+"; screen: "+main.innerText+"; status: "+statusbar.innerText);
    }
    const all = () => [...document.querySelectorAll('button')].filter(x=>x.offsetHeight && !x.disabled);
    async function click(text, parent=document) {
        const matching=()=>all().find(x=>parent.contains(x) && x.textContent.trim().startsWith(text));
        await wait(matching,text);
        matching().scrollIntoView();
        matching().click();
        await sleep(100);
        await wait(()=>!app.busy&&!app.polling,"busy");
    }
    function check(test, message) { if(!test) throw new Error(message); }
    async function enter(caption, value) {
        await click(caption);
        await wait(()=>dialog.open,"editor did not open");
        const input=dialog.querySelector('input');
        check(document.activeElement===input,"editor missing keyboard focus");
        input.value=value;
        input.dispatchEvent(new Event('input',{bubbles:true}));
        await click("Übernehmen",dialog);
    }
    const heading=()=>main.querySelector("h1")?.textContent;
    await wait(()=>app.state&&app.online,"initial state");
    check(!app.admin&&!document.querySelector('input[type=password]'),"operator login shown");
    await click("Geführte Prüfung");
    await wait(()=>heading()==="Prüfung erfassen","entry");
    await enter("Prüfnummer","WEB082-01");
    await enter("Gerätebeschreibung","Browser fixture kettle");
    check(app.state.draft.ticket==="WEB082-01","ticket edit lost");
    const phase=main.querySelector('select');
    phase.value="2";
    phase.dispatchEvent(new Event('change',{bubbles:true}));
    await wait(()=>app.state.draft.phase===2,"phase select");
    await click("Prüfung beginnen");
    await click("Ohne Befund");
    await wait(()=>app.state.guide?.step==="kind","visual callback not accepted");
    await click("Schutzklasse I");
    await click("Netz + 500 V geprüft");
    await wait(()=>app.state.guide?.step==="start","start step");
    check(document.querySelectorAll('.guide-row').length===3,"Class I instruction rows missing");
    await click("Hilfe");
    check(dialog.open,"Help overlay did not open");
    await click("Schliessen",dialog);
    await click("Lo LOAD");
    await click("Geringe Last bestätigt");
    await click("I LEAK blinkt");
    await click("Sicherheit bestätigt");
    await click("PASS");
    await click("STORE + Slot gesehen");
    await click("Prüfperson");
    await click("Auswählen");
    await wait(()=>app.state.draft.examiner===1,"examiner selection");
    const functionSelect=main.querySelector('select');
    functionSelect.value="1";
    functionSelect.dispatchEvent(new Event('change',{bubbles:true}));
    await wait(()=>app.state.guide.functional==="Ohne Befund","Function selection");
    await click("Zum Import");
    await click("Bestätigen",dialog);
    await wait(()=>app.state.draft.stage==="waiting","import state");
    await fetch("/__test/import");
    await wait(()=>app.state.batch&&app.state.batch.source==="rs232","stored RS232 frame");
    if(app.state.draft.stage==="waiting") await click("Vorhandene Messung");
    if(!app.state.selected) await click("012");
    await click("Messung bestätigen");
    await click("Bestätigen",dialog);
    await wait(()=>app.state.draft.stage==="report"&&app.loaded,"report");
    await click("PDF / QR-Code");
    await wait(()=>app.pdf&&document.querySelector(".qr"),"PDF QR");
    check(main.querySelector("a").href===app.pdf.url,"PDF download points to the token URL");
    check(!main.innerText.includes("RISO"),"QR page repeated measurements");
    await click("Zurück");
    await click("Beleg drucken");
    await click("Bestätigen",dialog);
    await wait(()=>app.state.print_note.includes("gesendet"),"print completion");
    check((await (await fetch("/__test/prints")).json()).count===1,"print count");
    document.getElementById("settings").click();
    await wait(()=>document.querySelector('input[type=password]'),"admin auth required");
    const input=main.querySelector('input[type=password]');
    input.value="local-admin-fixture";
    main.querySelector("form").dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));
    await wait(()=>app.admin && heading()==="Einstellungen","admin authentication");
    await click("Abmelden");
    await wait(()=>!app.admin,"operator mode restored");
    await wait(()=>!app.polling,"admin logout refresh");
    document.getElementById("home").click();
    check(!main.querySelector('input[type=password]'),"operator interrupted after logout");
    await wait(()=>main.querySelector(".mascot"),"wolf visible");
    const key=main.querySelector(".mascot");
    key.click();
    check(key.querySelector(".wolf").src.endsWith("happy.webp"),"tap needs emoji feedback");
    key.click();
    await wait(()=>heading()==="Werkstattwolf","double tap");
    await click("Werkstatt-Meilensteine");
    await wait(()=>heading()==="Werkstatt-Meilensteine","achievement route");
    await wait(()=>app.state.personality.achievements.pets===1,"pet count persists");
    return {ok:true,report:app.state.report,printed:1,verifiedAnonymous:true,view:heading()};
})().then(result=>window.v082Result=JSON.stringify(result),
          error=>window.v082Result=JSON.stringify({ok:false,error:String(error)}))
