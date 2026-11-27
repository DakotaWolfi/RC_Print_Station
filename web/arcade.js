"use strict";
window.makeArcade = function makeArcade(name, canvas, controls, restart) {
    const ctx=canvas.getContext("2d");
    let paddle,ball,velocity,bricks,snake,heading,pending,food,points,frame,over;
    const where=(x,y,w,h,color)=>{
        ctx.fillStyle=color;ctx.fillRect(x*canvas.width,y*canvas.height,w*canvas.width,h*canvas.height);
    };
    function reset() {
        paddle=.5;ball=[.5,.5];velocity=[.012,.013];
        bricks=new Set(Array.from({length:24},(_,i)=>i));
        snake=[[8,6],[7,6],[6,6]];heading=pending=[1,0];food=[12,6];
        points=frame=0;over=false;draw();
    }
    function stepSnake() {
        if(++frame%5) return;
        heading=pending;
        const head=snake[0].map((v,i)=>v+heading[i]);
        const eating=head[0]===food[0]&&head[1]===food[1];
        if(head[0]<0||head[0]>=16||head[1]<0||head[1]>=12||
                (eating?snake:snake.slice(0,-1)).some(([x,y])=>x===head[0]&&y===head[1])) {over=true;return;}
        snake.unshift(head);
        if(!eating) {snake.pop();return;}
        points++;
        const empty=Array.from({length:192},(_,i)=>[i%16,Math.floor(i/16)])
            .filter(([x,y])=>!snake.some(([a,b])=>x===a&&y===b));
        if(empty.length) food=empty[Math.floor(Math.random()*empty.length)];
        else over=true;
    }
    function stepBall() {
        const [x,y]=ball.map((v,i)=>v+velocity[i]);
        if(x<.05||x>.95) velocity[0]*=-1;
        if(y<.08||name==="Logo"&&y>.92) velocity[1]*=-1;
        if(name==="Breakout"&&y>=.15&&y<.326) {
            const brick=Math.floor(x*8)+Math.floor((y-.15)*17)*8;
            if(bricks.delete(brick)) {velocity[1]*=-1;points++;if(!bricks.size) over=true;}
        }
        if(name!=="Logo"&&velocity[1]>0&&y>.89) {
            if(Math.abs(x-paddle)<.13) {velocity[1]*=-1;if(name==="Pong")points++;}
            else over=true;
        }
        ball=[x,y];
    }
    function draw() {
        where(0,0,1,1,"#182838");
        if(name==="Snake") {
            where(food[0]/16,food[1]/12,1/16,1/12,"#ffb457");
            for(const [x,y] of snake) where(x/16,y/12,1/16,1/12,"#79cbe0");
        } else if(name==="Logo") {
            ctx.fillStyle="#ffb457";ctx.font="bold 28px sans-serif";
            ctx.fillText("FMI",canvas.width*ball[0]-24,canvas.height*ball[1]);
        } else {
            if(name==="Breakout") for(const i of bricks) where(i%8/8,.15+Math.floor(i/8)/17,.115,.047,"#79cbe0");
            where(paddle-.12,.91,.24,.036,"#79cbe0");
            where(ball[0]-.011,ball[1]-.015,.022,.03,"#ffb457");
        }
        if(name!=="Logo") {
            ctx.fillStyle="#edf4f8";ctx.font="20px sans-serif";ctx.fillText(points+(over?" · ■":""),12,23);
        }
    }
    function direction([x,y]) {
        if(name==="Snake"&&(x!==-heading[0]||y!==-heading[1])) pending=[x,y];
        if(name!=="Snake") paddle=Math.max(.1,Math.min(.9,paddle+x*.07));
    }
    const moves={ArrowLeft:[-1,0],ArrowUp:[0,-1],ArrowDown:[0,1],ArrowRight:[1,0]};
    canvas.onkeydown=e=>{if(moves[e.key]){e.preventDefault();direction(moves[e.key]);}};
    const position=e=>{const r=canvas.getBoundingClientRect();paddle=Math.max(.1,Math.min(.9,(e.clientX-r.left)/r.width));};
    canvas.onpointerdown=e=>{canvas.setPointerCapture(e.pointerId);position(e);};
    canvas.onpointermove=e=>{if(canvas.hasPointerCapture(e.pointerId))position(e);};
    for(const [button,vector] of controls) button.onclick=()=>direction(vector);
    restart.onclick=reset;
    reset();
    const timer=setInterval(()=>{
        if(!canvas.isConnected){clearInterval(timer);return;}
        if(document.hidden||over)return;
        if(name==="Snake")stepSnake();else stepBall();
        draw();
    },30);
};
