import zmq
import time
import os
import math

import casadi as C

import kiteproto
import freemodel
import joy

#tc0 = 2*389.970797939731

x0 = C.DMatrix( [ 1.154244772411
                , -0.103540608242
                , -0.347959211327
                , 1
                , 0
                , 0
                , 0
                , 1
                , 0
                , 0
                , 0
                , 1
                , 20.0
                , 0.0
                , 0.0
                , 0.137035790811
                , 3.664945343102
                , -1.249768772258
#                , 0.000000000000
#                , 3.874600000000
                ])

ts=0.02
simState = {}
simState['slowMoFactor'] = 4
tsSimStep = ts/simState['slowMoFactor']


if __name__=='__main__':
    print "creating model"
    (ode, others) = freemodel.model()
    ode.init()

    print "creating integrator"
    f = C.CVodesIntegrator(ode)
    f.setOption("reltol",1e-5)
    f.setOption("abstol",1e-7)
    f.setOption("t0",0)
    f.setOption("tf",tsSimStep)
    f.setOption('name','integrator')
#    f.setOption("linear_solver_creator",C.CSparse)
#    f.setOption("linear_solver","user_defined")
#    f.setOption("monitor",["res"])
    f.init()
    
    js = joy.Joy()

    context   = zmq.Context(1)
    publisher = context.socket(zmq.PUB)
    publisher.bind("tcp://*:5563")

    stateLog = []
    xSave = {}
    xSave[0]=x0
    def advanceState(x):
        axes = js.getAxes()
        buttons = js.getButtons()
#        print [(k,v) for k,v in enumerate(axes)]
#        print [(k,v) for k,v in enumerate(buttons)]

        # time dialation
        thumb = axes[8]
        if thumb>=0:
            simState['slowMoFactor'] = 1 + 9*thumb
        else:
            simState['slowMoFactor'] = 1 + thumb*0.9

        # saving/loading
        fstButton=13
        for k in range(0,4):
            if buttons[k+fstButton+4] and k in xSave:
                print "loading save #"+str(k+1)
                x = xSave[k]
            if buttons[k+fstButton]:
                if k==0:
                    print "can't override save0"
                else:
                    print "making save #"+str(k+1)
                    xSave[k] = x

        
        u1 = -axes[0]*0.03
        u2 =  axes[1]*0.1
        tc = 600*(1 - axes[6])
        wind_x = 5*(1-axes[7])
        wind_x = 0

#        tc = 389.970797939731

        drRef = 2*axes[10]

#        r = x[20]
#        dr = x[21]
#        ddr = (drRef-dr)/tsSimStep
#        print "r: %.2f\tdr: %.2f\tdrRef: %.2f\tdrErr: %.2f\tddr: %.2f" % (r,dr,drRef,drRef-dr,ddr)
        
        u = C.DMatrix([tc,u1,u2,wind_x])
        stateLog.append((x,u))
        
        f.setInput(x,C.INTEGRATOR_X0)
        f.setInput(u,C.INTEGRATOR_P)
        f.evaluate()

        return (C.DMatrix(f.output()), u)

    x = x0
    print "simulating..."
    try:
        while True:
            t0 = time.time()
            (x,u) = advanceState(x)
            p = kiteproto.toKiteProto(x,u)
            p.wind_x = u.at(3)
            p.messages.append("slowMoFactor: "+str(simState['slowMoFactor']))
            p.messages.append("torque: "+str(u.at(0)))
            p.messages.append("u1: "+str(u.at(1))+" ("+str(u.at(1)*180/math.pi)+" deg)")
            p.messages.append("u2: "+str(u.at(2))+" ("+str(u.at(2)*180/math.pi)+" deg)")
            p.messages.append("wind_x: "+str(u.at(3)))
            dx = x.at(12)
            dy = x.at(13)
            dz = x.at(14)
            p.messages.append("v: "+str(math.sqrt(dx*dx+dy*dy+dz*dz)))
#            p.messages.append("r:  "+str(x.at(20)))
#            p.messages.append("dr: "+str(x.at(21)))
#            p.messages.append("RPM: "+str(x.at(19)*60/(2*math.pi)))
            
            publisher.send_multipart(["carousel", p.SerializeToString()])
            
            deltaTime = (t0 + tsSimStep*simState['slowMoFactor']) - time.time()
            if deltaTime > 0:
                time.sleep(deltaTime)
    except KeyboardInterrupt:
        print "closing..."
        publisher.close()
        context.term()
        pass