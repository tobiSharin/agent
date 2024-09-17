# -*- coding: utf-8 -*-

'''
This Source Code Form is subject to the terms of the Mozilla
Public License, v. 2.0. If a copy of the MPL was not distributed
with this file, You can obtain one at http://mozilla.org/MPL/2.0/.
'''
import ipc
import agent
import threading
import native
import utils
import ctypes
import time
import os
import sys
import logging
import platform
import struct
import hashlib
from . import common

class ProcessCaptureScreen(threading.Thread):
    def __init__(self, cprc, args):
        threading.Thread.__init__(self,  name="ProcessCaptureScreen")
        self._struct_Q=struct.Struct("!Q")
        self._process=cprc
        self._args = args
        self._bdestory=False
        self._screen_module = None
        self._screen_libver = 0        
        self._cnt_image = utils.Counter()
        self._status = "C" # I INIT; O OPEN; C CLOSE
        self._capture_allowed=True
        self._capture_fallback_ok=False
        self._capture_fallback_lib=None
        self._capture_cnt_err=None
        self._capture_cnt_init=None
        self._monitors_info = common.MONITORS_INFO()
        self._monitors_info.count = 0        
        self._monitors_instance = None
        self._curimage=common.CURSOR_IMAGE()
        self._curid=0
        self._curx=-1
        self._cury=-1
        self._curvis=False        
        self._curcounter=utils.Counter()
        self._max_cpu_usage=30
        self._frame_wait_min=0.015
        self._frame_wait_max=0.8
        self._frame_wait_step=0.005
        self._frame_wait=self._frame_wait_min
        self._frame_wait_cnt=utils.Counter()
        self._inputs_list=[]
        self._inputs_lock=threading.Lock()
        self._privacy_mode=False
        self._clipboard_data=common.CLIPBOARD_DATA()
        self._clipboard_to_send=None
        self._clipboard_hash=""
    
    def _load_screen_module(self):
        if self._screen_module is None:
            loadseq=[]
            if agent.is_windows():
                if self._process._force_capturescreenlib is None:
                    if platform.release() == '10' or platform.release() == '11':
                        loadseq.append("dwagscreencapturedesktopduplication.dll")
                    loadseq.append("dwagscreencapturebitblt.dll")
                else:
                    loadseq.append("dwagscreencapture" + self._process._force_capturescreenlib + ".dll")
            elif agent.is_linux():
                if self._process._force_capturescreenlib is None:
                    loadseq.append("dwagscreencapturexorg.so")
                else:
                    loadseq.append("dwagscreencapture" + self._process._force_capturescreenlib + ".so")
            elif agent.is_mac():
                if self._process._force_capturescreenlib is None:
                    loadseq.append("dwagscreencapturequartzdisplay.dylib")
                else:
                    loadseq.append("dwagscreencapture" + self._process._force_capturescreenlib + ".so")
            
            #CHECK fallback args
            if self._args is not None: 
                for s in self._args:
                    if s[0:21]=="capture_fallback_lib=":
                        cfblklib = s[21:]
                        apploadseq=loadseq[:]
                        for nm in apploadseq:
                            if nm==cfblklib:
                                break
                            else:
                                loadseq.pop(0)
                        if len(loadseq)==0:
                            raise Exception("Invalid capture_fallback_lib " + cfblklib)
                
            lastex=None
            for nm in loadseq:
                try:
                    self._screen_listlibs = native.load_libraries_with_deps("screencapture")
                    self._screen_module = native._load_lib_obj(nm)
                    try:
                        self._screen_libver = self._screen_module.DWAScreenCaptureVersion()
                    except:
                        None
                    try:
                        common._libmap["cb_write_log"]=self._process._cb_write_log
                        self._screen_module.DWALoggerSetCallback(common.cb_write_log)
                    except:
                        None
                    if self._screen_module.DWAScreenCaptureLoad():
                        idx = loadseq.index(nm)
                        if idx>=0 and idx+1<=len(loadseq)-1:
                            self._capture_fallback_lib=loadseq[idx+1]
                        else:
                            self._capture_fallback_lib=None
                        lastex=None
                        pwi=len("dwagscreencapture")
                        self._process._write_info(u"Loaded screen capture library: " + nm.split(".")[0][pwi:])                        
                        break
                    else:
                        raise Exception("Library " + nm + " not load.")
                except:
                    ex = utils.get_exception()
                    lastex=ex
                    self._process._write_debug(utils.exception_to_string(ex))
                    self._unload_screen_module()
            if lastex is not None:                
                raise lastex
                                
        return self._screen_module
    
    def _unload_screen_module(self):
        if self._screen_module is not None:
            self._screen_module.DWAScreenCaptureUnload()
            native.unload_libraries(self._screen_listlibs)
            self._screen_module=None     
        
    def _send_monitors_changed(self):
        jomon=[]
        for i in range(self._monitors_info.count):
            m = self._monitors_info.monitor[i]
            jomon.append({"index":m.index,"x":m.x,"y":m.y,"width":m.width,"height":m.height})
        self._process.write_obj({u"request": u"MONITORS_CHANGED", u"monitors":jomon})
        
    def init_capture(self, joconf):
        mns=joconf["monitors"]
        if self._status != "C":
            raise Exception("Status must be C")        
        self._monitors_instance = mns
        self._status="I"
    
    def _handle_inputs(self,ar):
        imon=ar[0]
        ips=ar[1]
        for i in range(len(ips)):
            try:
                prms=ips[i].split(",")
                if prms[0]==u"MOUSE":
                    m=imon-1
                    x=int(prms[1])
                    y=int(prms[2])
                    if x>=0 and y>=0:
                        if m==-1 and self._monitors_info.count>1:
                            gx=0
                            gy=0
                            for i in range(self._monitors_info.count):
                                mon = self._monitors_info.monitor[i]
                                if mon.x<gx:
                                    gx=mon.x
                                if mon.y<gy:
                                    gy=mon.y
                            gx=abs(gx)
                            gy=abs(gy)
                            for i in range(self._monitors_info.count):
                                mon = self._monitors_info.monitor[i]
                                if x-gx>=mon.x and x-gx<mon.x+mon.width and y-gy>=mon.y and y-gy<mon.y+mon.height:
                                    m=i
                                    x-=gx+mon.x
                                    y-=gy+mon.y
                                    break
                    mon=None
                    if m>=0 and m<=self._monitors_info.count-1:
                        mon = ctypes.byref(self._monitors_info.monitor[m])
                    bcommand=False
                    if len(prms)==9:
                        bcommand=(prms[8]=="true")
                    self._screen_module.DWAScreenCaptureInputMouse(mon, x, y, int(prms[3]), int(prms[4]), prms[5]=="true", prms[6]=="true", prms[7]=="true", bcommand)
                elif prms[0]==u"KEYBOARD":                    
                    bcommand=False
                    if len(prms)==7:
                        bcommand=(prms[6]=="true")
                    self._screen_module.DWAScreenCaptureInputKeyboard(utils.str_to_bytes(prms[1]), utils.str_to_bytes(prms[2]), prms[3]=="true", prms[4]=="true", prms[5]=="true", bcommand)
                elif prms[0]==u"COPY":
                    apps = None
                    self._screen_module.DWAScreenCaptureCopy()
                    if self._screen_libver>=2:
                        self._clipboard_hash=""
                    else: #COMPATIBILITY OLD LIB VERSION 22/08/2022
                        pi = ctypes.c_void_p()
                        iret = self._screen_module.DWAScreenCaptureGetClipboardText(ctypes.byref(pi))
                        if iret>0:
                            apps = ctypes.wstring_at(pi,size=iret)
                            self._screen_module.DWAScreenCaptureFreeMemory(pi)
                        if apps is None:
                            apps = u""
                        self._clipboard_to_send = {}
                        self._clipboard_to_send["type"] = 1 #TEXT
                        self._clipboard_to_send["data"] = utils.str_to_bytes(apps,"utf8")
                        self._clipboard_to_send["sizedata"] = len(self._clipboard_to_send["data"])
                        self._clipboard_to_send["posdata"] = 0
                elif prms[0]==u"PASTE":
                    stxt=ips[i][6:]
                    if self._screen_libver>=2:
                        bts = ctypes.create_unicode_buffer(stxt)
                        appclp=common.CLIPBOARD_DATA()
                        appclp.type=1
                        appclp.data=ctypes.c_void_p(ctypes.addressof(bts))
                        appclp.sizedata=ctypes.sizeof(bts)
                        self._screen_module.DWAScreenCaptureSetClipboard(ctypes.byref(appclp))
                    else: #COMPATIBILITY OLD LIB VERSION 22/08/2022
                        self._screen_module.DWAScreenCaptureSetClipboardText(ctypes.c_wchar_p(utils.str_new(stxt)))
                    #time.sleep(0.1)
                    self._screen_module.DWAScreenCapturePaste()
                elif prms[0]==u"SET_CLIPBOARD":
                    stxt=ips[i][14:]
                    stxt=stxt[5:] #REMOVE type (text)
                    ns=utils.str_new(stxt);
                    self._clipboard_hash=hashlib.sha512(utils.str_to_bytes(u":".join([u"1",ns]),"utf8")).hexdigest()
                    if self._screen_libver>=2:
                        bts = ctypes.create_unicode_buffer(stxt)
                        appclp=common.CLIPBOARD_DATA()
                        appclp.type=1
                        appclp.data=ctypes.c_void_p(ctypes.addressof(bts))
                        appclp.sizedata=ctypes.sizeof(bts)
                        self._screen_module.DWAScreenCaptureSetClipboard(ctypes.byref(appclp))
                    else: #COMPATIBILITY OLD LIB VERSION 22/08/2022
                        self._screen_module.DWAScreenCaptureSetClipboardText(ctypes.c_wchar_p(ns))                    
            except:
                ex = utils.get_exception()
                appexs=""
                try:
                    appexs=u" (" + prms[0] + u")"
                except:
                    None
                self._process._write_err(u"Handle inputs" + appexs + u" Error: " + utils.exception_to_string(ex))
        
    
    def add_inputs(self,mon,ips):
        with self._inputs_lock:
            self._inputs_list.append([mon,ips])
    
    def copy_text(self,imon):
        self._inputs_list.append([imon,[u"COPY"]])        
        
    def paste_text(self,imon,stxt):
        self._inputs_list.append([imon,[u"PASTE," + stxt]])
    
    def set_clipboard(self,imon,stp,sdt):
        self._inputs_list.append([imon,[u"SET_CLIPBOARD," + stp + u"," + sdt]])
            
    #TMP PRIVACY MODE
    def set_privacy_mode(self, b):
        try:
            if agent.is_windows():
                if self._privacy_mode!=b:
                    self._privacy_mode=b
                    self._screen_module.DWAScreenCaptureSetPrivacyMode(b)
        except:
            None
    
    def _close_memmap(self):
        try:                                
            if self._monitors_instance is not None:
                if "memmap" in self._monitors_instance:
                    memmap=self._monitors_instance["memmap"]
                    if memmap is not None:
                        memmap.close()                
                    del self._monitors_instance["memmap"]
        except:
            ex = utils.get_exception()                    
            self._process._write_err(utils.exception_to_string(ex))
    
    def _lib_init_monitors(self):
        self._capture_cnt_err=None
        monlist=self._monitors_instance["list"]
        for i in range(len(monlist)):
            mon = monlist[i]
            if not "capid" in mon:
                mon["capid"]=0
            mon["capses"]=ctypes.c_void_p()
            mon["rgbimage"]=common.RGB_IMAGE()
            cmon = common.MONITORS_INFO_ITEM()
            cmon.index=mon["index"]
            cmon.x=mon["x"]
            cmon.y=mon["y"]
            cmon.width=mon["width"]
            cmon.height=mon["height"]
            iret = self._screen_module.DWAScreenCaptureInitMonitor(ctypes.byref(cmon),ctypes.byref(mon["rgbimage"]),ctypes.byref(mon["capses"]))
            if iret!=0:
                mon["capses"]=None
                self._lib_term_monitors()
                self._capture_fallback_ok=True
                raise Exception("Unable to initialize capture monitor (code: " + str(iret) + ").")
        
    def _lib_term_monitors(self):
        if self._monitors_instance is not None and "list" in self._monitors_instance:
            monlist=self._monitors_instance["list"]
            for i in range(len(monlist)):
                mon = monlist[i]
                if "capses" in mon and mon["capses"] is not None:
                    try:                
                        self._screen_module.DWAScreenCaptureTermMonitor(mon["capses"])
                    except:
                        ex = utils.get_exception()                    
                        self._process._write_err(utils.exception_to_string(ex))
                    mon["capses"]=None
    
    def _lib_get_image_monitors(self, forcechange):
        memmap=self._monitors_instance["memmap"]
        cond=self._monitors_instance["cond"]
        monlist=self._monitors_instance["list"]
        self._cnt_image.reset()
        for i in range(len(monlist)):
            mon = monlist[i]
            if "capses" in mon and mon["capses"] is not None:
                rgbimage=mon["rgbimage"]
                if self._capture_allowed==True:
                    iret = self._screen_module.DWAScreenCaptureGetImage(mon["capses"])
                    if (iret==0 and (rgbimage.sizechangearea>0 or rgbimage.sizemovearea>0)):
                        self._capture_cnt_init=None
                else:
                    iret = -99999 #Permission
                    if self._capture_cnt_init is not None:
                        self._capture_cnt_init.reset()
                    
                if iret!=0 or rgbimage.sizechangearea>0 or rgbimage.sizemovearea>0 or forcechange:
                    cond.acquire()
                    try:
                        while not self._bdestory and not self._process.is_destroy():
                            memmap.seek(0)
                            st = memmap.read(1)
                            if st==b"O":
                                memmap.seek(mon["pos"])
                                if iret==0:
                                    mon["capid"]+=1
                                    memmap.write(b"K")
                                    memmap.write(self._struct_Q.pack(mon["capid"]))                                
                                    memmap.write(rgbimage)
                                    memmap.write((ctypes.c_char*rgbimage.sizedata).from_address(rgbimage.data))
                                    cond.notify_all()                                                                        
                                elif iret==-99999:
                                    memmap.write(b"P") #Permission 
                                else:
                                    memmap.write(b"E")
                                    if self._capture_cnt_err==None:
                                        self._capture_cnt_err=utils.Counter()
                                    if self._capture_cnt_err.is_elapsed(1.0):
                                        self._capture_fallback_ok=True
                                        raise Exception("Unable to capture monitor (code: " + str(iret) + ").")
                                break
                            elif st==b"C":
                                self._bdestory=True
                                break
                            cond.wait(0.5)                        
                    finally:
                        cond.release()
        
        if self._frame_wait_cnt.is_elapsed(0.5):
            ucpu = self._screen_module.DWAScreenCaptureGetCpuUsage()
            if ucpu<=self._max_cpu_usage:
                self._frame_wait-=self._frame_wait_step
                if self._frame_wait<self._frame_wait_min:
                    self._frame_wait=self._frame_wait_min
            else:
                self._frame_wait+=self._frame_wait_step
                if self._frame_wait>self._frame_wait_max:
                    self._frame_wait=self._frame_wait_max
            self._frame_wait_cnt.reset()
        
        w = self._frame_wait-self._cnt_image.get_value()
        if w>0:
            time.sleep(w)
    
    def _lib_get_cursor(self):
        if self._curcounter.is_elapsed(0.02):
            memmap=self._monitors_instance["memmap"]
            cond=self._monitors_instance["cond"]
            curpos=self._monitors_instance["curpos"]
            if self._capture_allowed==True:
                iret = self._screen_module.DWAScreenCaptureCursor(ctypes.byref(self._curimage))
            else:
                iret = -2 #Permission
            if iret==0:
                if self._curx!=self._curimage.x or self._cury!=self._curimage.y or self._curvis!=self._curimage.visible or self._curimage.changed==1:
                    self._curx=self._curimage.x
                    self._cury=self._curimage.y
                    self._curvis=self._curimage.visible
                    cond.acquire()
                    try:
                        while not self._bdestory and not self._process.is_destroy():
                            memmap.seek(0)
                            st = memmap.read(1)
                            if st==b"O":
                                memmap.seek(curpos)
                                memmap.write(self._curimage)
                                if self._curimage.changed==1:
                                    cdt = utils.zlib_compress((ctypes.c_char*self._curimage.sizedata).from_address(self._curimage.data))
                                    if len(cdt)<common.MAX_CURSOR_IMAGE_SIZE:
                                        self._curid+=1
                                        memmap.write(self._struct_Q.pack(self._curid))                                    
                                        memmap.write(cdt)
                                cond.notify_all()
                                break
                            elif st==b"C":
                                self._bdestory=True
                                break
                            cond.wait(0.5)
                    finally:
                        cond.release()
            self._curcounter.reset()
    
    
    def _lib_get_clipboard(self):
        if self._screen_libver>=2:
            self._screen_module.DWAScreenCaptureGetClipboardChanges(ctypes.byref(self._clipboard_data))
            if self._clipboard_data.type==1: #TEXT
                cvdt = ctypes.c_void_p(self._clipboard_data.data)
                apps = ctypes.wstring_at(cvdt,size=int(self._clipboard_data.sizedata/ctypes.sizeof(ctypes.c_wchar)))
                self._screen_module.DWAScreenCaptureFreeMemory(cvdt)                
                clphs=hashlib.sha512(utils.str_to_bytes(u":".join([u"1",apps]),"utf8")).hexdigest()
                if self._clipboard_hash!=clphs:
                    self._clipboard_hash=clphs                                                    
                    self._clipboard_to_send = {}
                    self._clipboard_to_send["type"] = self._clipboard_data.type
                    self._clipboard_to_send["data"] = utils.str_to_bytes(apps,"utf8")
                    self._clipboard_to_send["sizedata"] = len(self._clipboard_to_send["data"])
                    self._clipboard_to_send["posdata"] = 0
            
        if self._clipboard_to_send is not None:
            sizedata=self._clipboard_to_send["sizedata"]
            posdata=self._clipboard_to_send["posdata"]
            tosenddata=sizedata-posdata
            req={u"request": u"CLIPBOARD_CHANGED"}
            req["type"]=self._clipboard_to_send["type"]
            req["size"]=self._clipboard_to_send["sizedata"]
            req["tokenpos"]=posdata            
            if tosenddata<=common.MAX_CLIPBOARD_TOKEN_SIZE:
                req["tokensize"]=tosenddata
                req["tokendata"]=self._clipboard_to_send["data"][posdata:posdata+tosenddata]
                req["tokenlast"]=True
                self._process.write_obj(req)
                self._clipboard_to_send=None
            else:
                req["tokensize"]=common.MAX_CLIPBOARD_TOKEN_SIZE                
                req["tokendata"]=self._clipboard_to_send["data"][posdata:posdata+common.MAX_CLIPBOARD_TOKEN_SIZE]
                req["tokenlast"]=False
                self._process.write_obj(req)
                self._clipboard_to_send["posdata"]=posdata+common.MAX_CLIPBOARD_TOKEN_SIZE
           
    def run(self):
        first_time=True
        detect_monitors_zero_cnt = None
        detect_monitors_cnt = None        
        try:            
            self._load_screen_module()
            while not self._bdestory and not self._process.is_destroy():
                forceChanges = False
                iretchanged = self._screen_module.DWAScreenCaptureIsChanged()
                if iretchanged==0: #NOT CHANGED
                    cptallow=True
                elif iretchanged==1: #CHANGED
                    cptallow=True
                    if self._status=="O":
                        self._lib_term_monitors()
                        self._status="I" 
                    forceChanges = True                       
                elif iretchanged==2: #PERMISSION
                    cptallow=False
                    self._capture_allowed=False
                    if first_time==True:
                        self._process.write_obj({u"request": u"MONITORS_CHANGED", u"monitors":[], u"error_code":-1})
                        detect_monitors_cnt = utils.Counter()
                    detect_monitors_cnt.reset()
                
                if self._capture_allowed!=cptallow:
                    self._capture_allowed=cptallow
                    if self._capture_allowed==True: 
                        if self._status=="O":
                            self._lib_term_monitors()
                            self._status="I"
                        forceChanges = True
                    
                #INPUTS
                inplst=None
                with self._inputs_lock:
                    if len(self._inputs_list)>0:
                        inplst=self._inputs_list
                        self._inputs_list=[]
                if self._capture_allowed==True and inplst is not None:
                    for inpitm in inplst:
                        self._handle_inputs(inpitm)
                
                #DETECT MONITORS
                tmcheck=2.0
                if self._capture_cnt_err is not None:
                    tmcheck=0.5
                if (self._capture_allowed==True) and (detect_monitors_cnt is None or detect_monitors_cnt.is_elapsed(tmcheck) or forceChanges==True):
                    iret = self._screen_module.DWAScreenCaptureGetMonitorsInfo(ctypes.byref(self._monitors_info))
                    if self._monitors_info.changed==1 or detect_monitors_cnt is None or iret!=0:
                        if iret==0:
                            self._close_memmap()
                            if self._status=="O":
                                self._lib_term_monitors()
                            self._status="C"                            
                            if first_time==False and self._monitors_info.count==0:
                                if detect_monitors_zero_cnt is None:
                                    detect_monitors_zero_cnt=utils.Counter()
                                if detect_monitors_zero_cnt.is_elapsed(6):
                                    self._send_monitors_changed()
                            else:
                                self._send_monitors_changed()
                        elif detect_monitors_cnt is None:
                            self._capture_fallback_ok=True
                            raise Exception("Unable to detect monitors.")
                    if detect_monitors_cnt is None:
                        detect_monitors_cnt = utils.Counter()
                    else:
                        detect_monitors_cnt.reset()

                #GET IMAGE
                if self._status=="I":
                    self._lib_init_monitors()
                    self._status="O"
                    first_time=False
                    detect_monitors_zero_cnt=None
                    self._capture_cnt_init=utils.Counter()                    
                if self._status=="O":
                    self._lib_get_image_monitors(forceChanges)
                    self._lib_get_cursor()                    
                    if self._capture_cnt_init is not None and self._capture_cnt_init.is_elapsed(4):
                        self._capture_fallback_ok=True
                        raise Exception("Unable to capture monitor (init).")
                else:
                    time.sleep(0.25)
                
                
                #CLIPBOARD
                self._lib_get_clipboard()
        except:
            ex = utils.get_exception() 
            ar={u"request": u"RAISE_ERROR", u"class":u"ProcessCaptureScreen",  u"message":utils.exception_to_string(ex)}
            if self._capture_fallback_ok and self._capture_fallback_lib is not None:
                ar["capture_fallback_lib"]=self._capture_fallback_lib
            self._process.write_obj(ar)                   
            self._process._write_debug(utils.exception_to_string(ex))
        
        self._close_memmap()
        if self._status=="O":
            self._lib_term_monitors()
        self._status="C"        
        self._unload_screen_module()
            
    def destory(self):
        self._bdestory = True
                
class ProcessCaptureSound(threading.Thread):
        
    def __init__(self, cprc, args):
        threading.Thread.__init__(self,  name="ProcessCaptureSound")
        self._struct_Q=struct.Struct("!Q")
        self._process = cprc
        self._args = args
        self._bdestory=False
        self._sound_module = None
        self._sound_libver = 0
        self._memmap_limit=0
        self._memmap_size=0
        self._memmap=None
        self._cond=None
        self._frameid=0
        self._status = "C" #O OPEN; C CLOSE
        
    def _is_old_windows(self):
        return (agent.is_windows() and (native.get_instance().is_win_xp()==1 or native.get_instance().is_win_2003_server()==1))
    
    def _load_sound_module(self):
        if self._sound_module is None:
            self._sound_listlibs = native.load_libraries_with_deps("soundcapture")
            self._sound_module = self._sound_listlibs[0]
            try:
                self._sound_libver = self._sound_module.DWASoundCaptureVersion()
            except:
                None
            try:
                common._libmap["cb_write_log"]=self._process._cb_write_log
                self._sound_module.DWALoggerSetCallback(common.cb_write_log)
            except:
                None
        return self._sound_module
    
    def _unload_sound_module(self):
        if self._sound_module is not None:            
            native.unload_libraries(self._sound_listlibs)
            self._sound_module=None
    
    def get_enable(self):
        return self._enable
    
    def init_capture(self, joconf):
        if self._status != "C":
            raise Exception("Status must be C")
        self._memmap=joconf["memmap"]
        self._cond=joconf["cond"]
        self._status="O"        
    
    def cb_sound_data(self, sz, pdata):
        if self._status=="O" and sz>0:
            try:
                sdata = utils.bytes_new(pdata[0:sz])
                self._cond.acquire()
                try:
                    self._memmap.seek(0)
                    st = self._memmap.read(1)
                    if st==b"O":
                        self._frameid+=1
                        self._memmap.write(self._struct_Q.pack(self._frameid))
                        towrite=0
                        if self._memmap_limit+sz>=self._memmap_size:
                            towrite=self._memmap_size-self._memmap_limit
                            if towrite>0:
                                self._memmap.seek(17+self._memmap_limit)
                                self._memmap.write(sdata[0:towrite])                            
                            self._memmap_limit=0
                        if towrite<sz:
                            self._memmap.seek(17+self._memmap_limit)
                            self._memmap.write(sdata[towrite:sz])
                            self._memmap_limit+=(sz-towrite)
                        self._memmap.seek(9)
                        self._memmap.write(self._struct_Q.pack(self._memmap_limit))
                        self._cond.notify_all()
                    else:
                        self._status=b"C"
                finally:
                    self._cond.release()
            except:
                ex = utils.get_exception()
                self._status=b"C"
                self._process._write_err(str("cb_sound_data err: " + utils.exception_to_string(ex)))
            
    
    def run(self):
        fnsndcrash = utils.path_expanduser("~") + utils.path_sep + u".dwagent"
        if not utils.path_exists(fnsndcrash):
            utils.path_makedirs(fnsndcrash)
        fnsndcrash = fnsndcrash + utils.path_sep + u"app_desktop.soundcrash"
        fnsndcrashcnt = utils.Counter()
        err_msg=None
        capses = None
        aconf = common.AUDIO_CONFIG()
        aconf.numChannels = 2
        aconf.sampleRate = 48000
        aconf.bufferFrames = int(aconf.sampleRate*(40.0/1000.0))
        try:                
            if not self._is_old_windows():
                if self._process.get_sound_enable():
                    if fnsndcrash is None or not utils.path_exists(fnsndcrash):
                        if fnsndcrash is not None:
                            fsndcrash=utils.file_open(fnsndcrash, 'wb')
                            fsndcrash.close()
                        self._load_sound_module()
                        if self._sound_libver>=4:
                            common._libmap["cb_sound_data"]=self.cb_sound_data
                            capses = ctypes.c_void_p()
                            iret = self._sound_module.DWASoundCaptureStart(ctypes.byref(aconf),common.cb_sound_data,ctypes.byref(capses))
                            if iret==0:
                                if agent.is_mac():
                                    bf = ctypes.create_string_buffer(2048)
                                    l = self._sound_module.DWASoundCaptureGetDetectOutputName(capses,bf,2048)
                                    if l>0:
                                        sodn=utils.bytes_to_str(bf.value[0:l],"utf8")
                                    else:
                                        sodn=""
                                    if "SOUNDFLOWER" not in sodn.upper():
                                        err_msg="Soundflower not found. Please install it and set it as your primary output device."
                            else:
                                capses=None
                                err_msg="Not started (Error: " + str(iret) + ")."
                        else:
                            capses=None
                            err_msg="Invalid library version: " + str(self._sound_libver)                    
                    else:
                        err_msg="Crash soundlib."
                else:
                    err_msg="Not enabled."
            else:
                err_msg="Not supported."
        except:
            ex = utils.get_exception()            
            err_msg=utils.exception_to_string(ex)
            self._process._write_err("Sound load error. " + utils.exception_to_string(ex))
        
        if err_msg is not None:
            self._process.write_obj({u"request": u"SOUND_STATUS", u"status":u"ERROR", u"message":err_msg})
        else:
            self._memmap_size=2*(ctypes.sizeof(ctypes.c_float)*aconf.sampleRate*aconf.numChannels) #2 seconds
            self._process.write_obj({u"request": u"SOUND_STATUS", u"status":u"OK", u"num_channels":aconf.numChannels, u"sample_rate":aconf.sampleRate, u"buffer_frames":aconf.bufferFrames, u"memmap_size":self._memmap_size}) 
            while not self._bdestory and not self._process.is_destroy():
                #TODO detect output change
                #if self._counter.is_elapsed(3):
                    #self._counter.reset()
                    #self._sndmdl.DWASoundCaptureDetectOutput() #TO CHECK
                time.sleep(0.5)
                if fnsndcrashcnt.is_elapsed(5):
                    if utils.path_exists(fnsndcrash):
                        os.remove(fnsndcrash)
        if utils.path_exists(fnsndcrash):
            os.remove(fnsndcrash)
        self._status="C"        
        time.sleep(1)
        if capses is not None:
            l = self._sound_module.DWASoundCaptureStop(capses)
            capses=None        
        self._cond=None
        if self._memmap is not None:
            try:
                self._memmap.close()
            except:
                ex = utils.get_exception()               
                self._process._write_err(utils.exception_to_string(ex))
            self._memmap=None
        self._unload_sound_module()
                
        
    def destory(self):
        self._bdestory = True

class ProcessCaptureStdRedirect(object):
    
    def __init__(self,lg,lv):
        self._logger = lg
        self._level = lv
        
    def write(self, data):
        for line in data.rstrip().splitlines():
            self._logger.log(self._level, line.rstrip())
    
    def flush(self):
        None

class ProcessCaptureStdOut(object):
    def __init__(self, prc):
        self._process=prc
        self._arapp=[]
        
    def write(self, data):
        if data=="\n":
            self._process._write_debug("".join(self._arapp))
            self._arapp=[]
        else:
            self._arapp.append(data)

class ProcessCaptureStdErr(object):
    
    def __init__(self, prc):
        self._process=prc
        self._arapp=[]
    
    def write(self, data):
        if data=="\n":
            self._process._write_err("".join(self._arapp))
            self._arapp=[]
        else:
            self._arapp.append(data)
        

class ProcessCapture(ipc.ChildProcessThread):
    
    def _on_init(self):
        common._libmap["captureprocess"]=self
        self._semaphore = threading.Condition()
        self._screen_thread= None
        self._sound_thread= None        
        self._write_lock=threading.RLock()        
        self._debug_enable=False 
        self._sound_enable=True
        self._privacy_mode=""
        self._force_capturescreenlib=None
        
        if ipc.is_load_libbase():
            sys.stdout = ProcessCaptureStdOut(self)
            sys.stderr = ProcessCaptureStdErr(self)
    
    def get_sound_enable(self):
        return self._sound_enable        
    
    def _write_info(self,s):
        self._write_log("INFO",s)
    
    def _write_err(self,s):
        self._write_log("ERR",s)
    
    def _write_debug(self,s):
        self._write_log("DEBUG",s)
    
    def _write_log(self,l,s):
        try:
            self.write_obj({u"request": u"WRITE_LOG", u"level": l , u"text": utils.str_new(s)})
        except:
            None #DO NOT REMOVE
    
    def _cb_write_log(self,l,s):
        if l==0:
            self._write_info(s)
        elif l==1:
            self._write_err(s)
        else:
            self._write_debug(s)
                
    def _strm_read_timeout(self,strm):
        return self.is_destroy() 
        
    def write_obj(self, obj):
        with self._write_lock:
            self._stream.write_obj(obj)
    
    def run(self):
        try:
            c = agent.read_config_file()            
            if "debug_mode" in c:
                self._debug_enable=c["debug_mode"]
            if "desktop.sound_enable" in c:
                self._sound_enable=c["desktop.sound_enable"]
            if "desktop.privacy_mode" in c:
                self._privacy_mode=c["desktop.privacy_mode"]
            if "desktop.force_capturescreenlib" in c:
                self._force_capturescreenlib=c["desktop.force_capturescreenlib"]
        except:
            None
                
        self._write_debug("Init capture process.")
        try:
            #"capture_fallback_lib =" + self._capture_fallback_lib
            self._screen_thread=ProcessCaptureScreen(self, self.get_arguments())
            self._screen_thread.start()
            
            self._sound_thread=ProcessCaptureSound(self, self.get_arguments())
            self._sound_thread.start()
            
            self._write_debug("Ready to accept requests")   
            self._stream.set_read_timeout_function(self._strm_read_timeout)            
            while not self.is_destroy():
                joreq = None
                try:
                    joreq = self._stream.read_obj()
                except:
                    None
                if joreq==None:
                    break
                sreq = joreq["request"]
                #self._write_debug("Request: " + sreq)
                try:
                    if sreq==u"INIT_SCREEN_CAPTURE":
                        self._screen_thread.init_capture(joreq)
                        #TMP PRIVACY MODE
                        if self._privacy_mode=="always":
                            self._screen_thread.set_privacy_mode(True)                                                
                    elif sreq==u"INIT_SOUND_CAPTURE":
                        self._sound_thread.init_capture(joreq)
                    elif sreq==u"INPUTS":
                        self._screen_thread.add_inputs(joreq["monitor"],joreq["inputs"].split(";"))
                    elif sreq==u"COPY_TEXT":
                        self._screen_thread.copy_text(joreq["monitor"])
                    elif sreq==u"PASTE_TEXT":
                        self._screen_thread.paste_text(joreq["monitor"],joreq["text"])
                    elif sreq==u"SET_CLIPBOARD":
                        self._screen_thread.set_clipboard(joreq["monitor"],joreq["type"],joreq["data"])
                    else:
                        raise Exception(u"Request '" + sreq + u"' is not valid.")
                except:
                    ex = utils.get_exception()
                    self._write_err(utils.exception_to_string(ex))
                    
        except:
            ex = utils.get_exception()
            if not self.is_destroy():
                self._write_err(utils.exception_to_string(ex))
        self.destroy()
        if self._stream is not None:
            try:
                self._stream.close()
            except:
                ex = utils.get_exception()
                self._write_err(utils.exception_to_string(ex))
        
        
        #TMP PRIVACY MODE
        self._screen_thread.set_privacy_mode(False)
        self._screen_thread.destory()
        self._screen_thread.join(2)
        self._sound_thread.destory()
        self._sound_thread.join(2)
        
        self._write_debug("Term capture process.")

