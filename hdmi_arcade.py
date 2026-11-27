"""Lightweight workshop games. The display timer runs only on the game page."""
from random import choice

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget


class Arcade(QWidget):
    def __init__(self,name):
        super().__init__()
        self.name=name
        self.setMinimumHeight(176)
        self.setMaximumHeight(410)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.restart()

    def restart(self):
        self.ball=[.5,.5]
        self.velocity=[.012,.013]
        self.paddle=.5
        self.bricks={(x,y) for x in range(8) for y in range(3)}
        self.snake=[(8,6),(7,6),(6,6)]
        self.heading=self.pending=(1,0)
        self.food=(12,6)
        self.clock=0
        self.score=0
        self.over=False
        self.update()

    def showEvent(self,event):
        self.setFocus()
        self.timer.start(30)
        super().showEvent(event)

    def hideEvent(self,event):
        self.timer.stop()
        super().hideEvent(event)

    def direction(self,direction):
        if direction!=tuple(-n for n in self.heading):
            self.pending=direction

    def keyPressEvent(self,event):
        key=event.key()
        moves={Qt.Key_Left:(-1,0),Qt.Key_Right:(1,0),Qt.Key_Up:(0,-1),Qt.Key_Down:(0,1)}
        if key in moves:
            if self.name=="Snake":
                self.direction(moves[key])
            else:
                self.paddle=max(.1,min(.9,self.paddle+.07*moves[key][0]))
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self,event):
        self.move_paddle(event.pos().x())

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton:
            self.move_paddle(event.pos().x())

    def event(self,event):
        from PyQt5.QtCore import QEvent
        if event.type() in (QEvent.TouchBegin,QEvent.TouchUpdate):
            points=event.touchPoints()
            if points:
                self.move_paddle(points[0].pos().x())
            return True
        return super().event(event)

    def move_paddle(self,x):
        self.paddle=max(.10,min(.90,x/max(1,self.width())))

    def tick(self):
        if self.over:
            return
        self.clock+=1
        if self.name=="Snake":
            if self.clock%5:
                return
            self.heading=self.pending
            head=tuple(a+b for a,b in zip(self.snake[0],self.heading))
            growing=head==self.food
            if not (0<=head[0]<16 and 0<=head[1]<12) or head in (self.snake if growing else self.snake[:-1]):
                self.over=True
            else:
                self.snake.insert(0,head)
                if growing:
                    self.score+=1
                    free=[(x,y) for x in range(16) for y in range(12) if (x,y) not in self.snake]
                    if free:
                        self.food=choice(free)
                    else:
                        self.over=True
                else:
                    self.snake.pop()
        else:
            x,y=(self.ball[axis]+self.velocity[axis] for axis in (0,1))
            if not .05<x<.95:
                self.velocity[0]*=-1
            if y<.08 or self.name=="Logo" and y>.92:
                self.velocity[1]*=-1
            if self.name=="Breakout":
                brick=(int(x*8),int((y-.15)*17))
                if .15<=y<.326 and brick in self.bricks:
                    self.bricks.remove(brick)
                    self.velocity[1]*=-1
                    self.score+=1
                    self.over=not self.bricks
            if self.name in ("Breakout","Pong") and y>.89 and self.velocity[1]>0:
                if abs(x-self.paddle)<.13:
                    self.velocity[1]*=-1
                    if self.name=="Pong":
                        self.score+=1
                else:
                    self.over=True
            self.ball=[x,y]
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor("#182838"))
        w,h=self.width(),self.height()
        def draw(x,y,dx,dy,color):
            p.fillRect(QRectF(x*w,y*h,dx*w,dy*h),QColor(color))
        if self.name=="Snake":
            draw(self.food[0]/16,self.food[1]/12,1/16,1/12,"#ffb457")
            for x,y in self.snake:
                draw(x/16,y/12,1/16,1/12,"#79cbe0")
        elif self.name=="Logo":
            p.setPen(QColor("#ffb457"))
            p.drawText(QRectF((self.ball[0]-.08)*w,(self.ball[1]-.08)*h,.16*w,.16*h),Qt.AlignCenter,"FMI")
        else:
            for x,y in self.bricks if self.name=="Breakout" else ():
                draw(x/8,.15+y/17,.115,.047,"#79cbe0")
            draw(self.paddle-.12,.91,.24,.036,"#79cbe0")
            draw(self.ball[0]-.011,self.ball[1]-.015,.022,.030,"#ffb457")
        if self.name!="Logo":
            p.setPen(QColor("#edf4f8"))
            p.drawText(10,22,str(self.score)+(" · ■" if self.over else ""))
