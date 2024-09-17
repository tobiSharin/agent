# -*- coding: utf-8 -*-

'''
This Source Code Form is subject to the terms of the Mozilla
Public License, v. 2.0. If a copy of the MPL was not distributed
with this file, You can obtain one at http://mozilla.org/MPL/2.0/.
'''

import ctypes
import utils
import os
import stat
import subprocess
import sys
import time
import ipc
import threading
import signal
import json

GUILNC_ARG_MAX=10 #COMPATIBILITA VERSIONI PRECEDENTI
GUILNC_ARG_SIZE=1024 #COMPATIBILITA VERSIONI PRECEDENTI

_nativemap={}
_nativemap["semaphore"] = threading.Condition()

def get_instance():
    oret=None
    _nativemap["semaphore"].acquire()
    try:
        if "instance" in _nativemap:
            oret=_nativemap["instance"]
        else:
            if utils.is_windows():
                oret = Windows()
            elif utils.is_linux():
                oret = Linux()
            elif utils.is_mac():
                oret = Mac()
            oret.load_library();
            _nativemap["instance"]=oret
    finally:
        _nativemap["semaphore"].release()
    return oret

def fmain(args):
    if utils.is_mac():
        if len(args)>1:
            a1=args[1]            
            if a1 is not None and a1.lower()=="guilnc": #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE) (DO NOT REMOVE)
                main = Mac()
                main.start_guilnc()
                sys.exit(0)

def get_suffix():
    if utils.is_windows():
        return "win"
    elif utils.is_linux():
        return "linux"
    elif utils.is_mac():
        return "mac"
    return None

def get_library_config(name):
    fn=None
    if utils.path_exists(".srcmode"):
        fn=".." + utils.path_sep + "lib_" + name + utils.path_sep + "config.json"        
    else:
        fn="native" + utils.path_sep + "lib_" + name + ".json"
    if utils.path_exists(fn):
        f = utils.file_open(fn)
        jsapp = json.loads(f.read())
        f.close()
        return jsapp
    else:
        return None

def _load_libraries_with_deps(ar,name):
    cnflib=get_library_config(name)
    if cnflib is not None:
        if "lib_dependencies" in cnflib:
            for ln in cnflib["lib_dependencies"]:
                _load_libraries_with_deps(ar,ln)
        if "filename_" + get_suffix() in cnflib:
            fn = cnflib["filename_" + get_suffix()]
            ar.insert(0,_load_lib_obj(fn))

def load_libraries_with_deps(name):
    lstlibs=[]
    _load_libraries_with_deps(lstlibs,name)
    return lstlibs

def unload_libraries(lstlibs):
    for i in range(len(lstlibs)):
        _unload_lib_obj(lstlibs[i])

def _load_lib_obj(name):
    print('load_lib_obj', name)
    retlib = None
    if utils.is_windows():
        if not utils.path_exists(".srcmode"):
            retlib = ctypes.CDLL("native\\" + name)
        else:
            dll_path = os.path.abspath(os.path.join("..\\make\\native\\",name))
            retlib = ctypes.CDLL(dll_path)
        if retlib is None:
            raise Exception("Missing library " + name + ".")
    elif utils.is_linux():
        if not utils.path_exists(".srcmode"):
            retlib  = ctypes.CDLL("native/" + name, ctypes.RTLD_GLOBAL)
        else: 
            retlib = ctypes.CDLL("../make/native/" + name, ctypes.RTLD_GLOBAL)
        if retlib is None:
            raise Exception("Missing library " + name + ".")
    elif utils.is_mac():
        if not utils.path_exists(".srcmode"):
            retlib  = ctypes.CDLL("native/" + name, ctypes.RTLD_GLOBAL)
        else: 
            retlib = ctypes.CDLL("../make/native/" + name, ctypes.RTLD_GLOBAL)
        if retlib is None:
            raise Exception("Missing library " + name + ".")
    return retlib;
    

def _unload_lib_obj(olib):
    if olib is not None:
        try:
            if utils.is_windows():
                import _ctypes
                _ctypes.FreeLibrary(olib._handle)
                del olib
            elif utils.is_linux():
                import _ctypes
                _ctypes.dlclose(olib._handle)
                del olib
            elif utils.is_mac():
                import _ctypes
                _ctypes.dlclose(olib._handle)
                del olib
        except:
            None
'''
del olib
    olib.dlclose(olib._handle)
while isLoaded('./mylib.so'):
    dlclose(handle)

It's so unclean that I only checked it works using:

def isLoaded(lib):
   libp = utils.path_absname(lib)
   ret = os.system("lsof -p %d | grep %s > /dev/null" % (os.getpid(), libp))
   return (ret == 0)

def dlclose(handle)
   libdl = ctypes.CDLL("libdl.so")
   libdl.dlclose(handle)
'''

class Windows():
        
    def __init__(self):
        self._dwaglib=None

    def load_library(self):
        if self._dwaglib is None:
            self._dwaglib = _load_lib_obj("dwaglib.dll");
    
    def unload_library(self):
        _unload_lib_obj(self._dwaglib)
        self._dwaglib=None
    
    def get_library(self):
        return self._dwaglib

    def task_kill(self, pid) :
        bret = self._dwaglib.taskKill(pid)
        return bret==1
    
    def is_task_running(self, pid):
        bret=self._dwaglib.isTaskRunning(pid);
        return bret==1
    
    def set_file_permission_everyone(self,fl):
        if utils.is_py2():
            self._dwaglib.setFilePermissionEveryone(fl)
        else:
            self._dwaglib.setFilePermissionEveryone(fl.encode('utf-8'))
    
    def fix_file_permissions(self,operation,path,path_src=None):
        None
        
    def is_win_xp(self):
        return self._dwaglib.isWinXP()
        
    def is_win_2003_server(self):
        return self._dwaglib.isWin2003Server()
    
    def is_user_in_admin_group(self):
        return self._dwaglib.isUserInAdminGroup()
    
    def is_run_as_admin(self):
        return self._dwaglib.isRunAsAdmin()
        
    def is_process_elevated(self):
        return self._dwaglib.isProcessElevated()
    
    def get_active_console_id(self):
        return self._dwaglib.getActiveConsoleId();
    
    def start_process(self, scmd, spythonHome):
        return self._dwaglib.startProcess(scmd, spythonHome);
    
    def start_process_in_active_console(self, scmd, spythonHome):
        return self._dwaglib.startProcessInActiveConsole(scmd, spythonHome);
    
    def win_station_connect(self):
        self._dwaglib.winStationConnect()
    
    def is_gui(self):
        return True 
    
    def reboot(self):
        os.system("shutdown -r -f -t 0")

class Linux():
    
    def __init__(self):
        self._dwaglib=None
    
    def load_library(self):
        try:
            if self._dwaglib is None:
                self._dwaglib = _load_lib_obj("dwaglib.so")
        except:
            None
    
    def unload_library(self):
        _unload_lib_obj(self._dwaglib)
        self._dwaglib=None
    
    def get_library(self):
        return self._dwaglib 
    
    def task_kill(self, pid) :
        try:
            os.kill(pid, -9)
        except OSError:
            return False
        return True
    
    def is_task_running(self, pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    
    def set_file_permission_everyone(self,f):
        utils.path_change_permissions(f, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
    
        
    def fix_file_permissions(self,operation,path,path_template=None):
        apppath=path
        if apppath.endswith(utils.path_sep):
            apppath=apppath[0:len(apppath)-1]
        apppath_template=path_template
        if apppath_template is not None:
            if apppath_template.endswith(utils.path_sep):
                apppath_template=apppath_template[0:len(apppath_template)-1]
        
        if operation=="CREATE_DIRECTORY":
            apppath_template=utils.path_dirname(path)    
            stat_info = utils.path_stat(apppath_template)
            mode = stat.S_IMODE(stat_info.st_mode)
            utils.path_change_permissions(path,mode)
            utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        elif operation=="CREATE_FILE":
            apppath_template=utils.path_dirname(path)    
            stat_info = utils.path_stat(apppath_template)
            mode = stat.S_IMODE(stat_info.st_mode)
            utils.path_change_permissions(path, ((mode & ~stat.S_IXUSR) & ~stat.S_IXGRP) & ~stat.S_IXOTH)
            utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        elif operation=="COPY_DIRECTORY" or operation=="COPY_FILE":
            if apppath_template is not None:
                stat_info = utils.path_stat(apppath_template)
                mode = stat.S_IMODE(stat_info.st_mode)
                utils.path_change_permissions(path,mode)
                stat_info = utils.path_stat(utils.path_dirname(path)) #PRENDE IL GRUPPO E L'UTENTE DELLA CARTELLA PADRE 
                utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        elif operation=="MOVE_DIRECTORY" or operation=="MOVE_FILE":
            if apppath_template is not None:
                stat_info = utils.path_stat(apppath_template)
                mode = stat.S_IMODE(stat_info.st_mode)
                utils.path_change_permissions(path,mode)
                utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        
    def is_gui(self):
        try:
            import detectinfo
            appnsfx = detectinfo.get_native_suffix()
            if not appnsfx=="linux_generic":
                appout = subprocess.Popen("ps ax -ww | grep 'X.*-auth .*'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate() 
                lines = appout[0].splitlines()
                for l in lines:
                    if 'X.*-auth .*' not in l:
                        return True
        except:
            None
        return False
    
    def reboot(self):
        os.system("reboot")
        
    def get_tty_active(self):
        scons=None
        try:
            sactive=None
            fn = "/sys/class/tty/console/active"
            if os.path.exists(fn):
                f = open(fn, "rb")
                try:
                    s = utils.bytes_to_str(f.read(),"utf8")    
                    if s is not None and len(s)>0:
                        s=s.strip("\n").strip("\r")
                        appar = s.split(" ")
                        for apps in appar:
                            if apps[3:].isdigit():
                                sactive = apps
                                break
                        
                finally:
                    f.close()
            if sactive is not None:
                fn = "/sys/class/tty/" + sactive+ "/active"
                if os.path.exists(fn):
                    f = open(fn , "rb")
                    try:
                        s = utils.bytes_to_str(f.read(),"utf8")
                        if s is not None and len(s)>0:
                            s=s.strip("\n").strip("\r")
                            scons = s.split(" ")[0]                        
                    finally:
                        f.close()
                else:
                    scons = None
            if scons is None:
                #Try fgconsole
                data = subprocess.Popen(["fgconsole"], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
                so, se = data.communicate()
                if so is not None and len(so)>0:
                    so=utils.bytes_to_str(so, "utf8")
                    scons="tty"+so.replace("\n","").replace("\r","")
                    if not os.path.exists("/sys/class/tty/" + scons):
                        scons=None                    
            if scons is None:
                scons = sactive
        except:
            None
        return scons
    
    def get_process_ids(self):
        lret=[]
        lst = os.listdir("/proc")
        for name in lst:
            if name.isdigit():
                lret.append(int(name))
        return lret
    
    def get_process_environ(self,pid):
        eret = {} 
        try:
            fn = "/proc/" + str(pid) + "/" + "environ"
            if os.path.exists(fn):
                f = open(fn , "rb")
                try:
                    s = utils.bytes_to_str(f.read(),"utf8")    
                    if s is not None and len(s)>0:
                        arenv = s.split("\0")
                        for apps in arenv:
                            p = apps.index("=")
                            if p>0:
                                eret[apps[:p]]=apps[p+1:]                            
                finally:
                    f.close()
        except:
            None
        return eret
    
    def get_process_stat(self,pid):
        sret = {} 
        try:
            fn = "/proc/" + str(pid) + "/" + "stat"
            if os.path.exists(fn):
                f = open(fn , "rb")
                try:
                    s = utils.bytes_to_str(f.read(),"utf8")
                    if s is not None and len(s)>0:
                        rpar = s.rfind(r')')
                        name = s[s.find(r'(') + 1:rpar]
                        fields = s[rpar + 2:].split()            
                        sret['name'] = name
                        sret['status'] = fields[0]
                        sret['ppid'] = int(fields[1])
                        sret['pgrp'] = int(fields[2])
                        sret['session'] = fields[3]
                        sret['tty'] = int(fields[4])
                        sret['tpgid'] = int(fields[5])             
                finally:
                    f.close()
        except:
            None
        return sret

    def get_process_uid(self,pid):
        sret = -1
        try:
            fn = "/proc/" + str(pid) + "/" + "status"
            if os.path.exists(fn):
                f = open(fn , "rb")
                try:
                    s = utils.bytes_to_str(f.read(),"utf8")
                    if s is not None and len(s)>0:
                        import re
                        reuids=re.compile(r'Uid:\t(\d+)\t(\d+)\t(\d+)')
                        ur, ue, us = reuids.findall(s)[0]
                        sret = int(ur)
                finally:
                    f.close()
        except:
            None
        return sret
    
    def get_process_gid(self, pid):
        sret = -1
        try:
            fn = "/proc/" + str(pid) + "/" + "status"
            if os.path.exists(fn):
                f = open(fn , "rb")
                try:
                    s = utils.bytes_to_str(f.read(),"utf8")
                    if s is not None and len(s)>0:
                        import re
                        reuids=re.compile(r'Gid:\t(\d+)\t(\d+)\t(\d+)')
                        gr, ge, gs = reuids.findall(s)[0]
                        sret = gr
                finally:
                    f.close()
        except:
            None
        return sret
    
    
    def get_process_cmdline(self, pid):
        lret = [] 
        try:
            fn = "/proc/" + str(pid) + "/" + "cmdline"
            if os.path.exists(fn):
                f = open(fn , "rb")
                try:
                    s = utils.bytes_to_str(f.read(),"utf8")
                    if s is not None and len(s)>0:
                        lret = s.split("\0")             
                finally:
                    f.close()
        except:
            None
        return lret
    
    def get_utf8_lang(self):
        altret=None
        try:
            p = subprocess.Popen("locale | grep LANG=", stdout=subprocess.PIPE, shell=True)
            (po, pe) = p.communicate()
            p.wait()
            if len(po) > 0:                
                po = utils.bytes_to_str(po, "utf8")                
                ar = po.split("\n")[0].split("=")[1].split(".")
                if ar[1].upper()=="UTF8" or ar[1].upper()=="UTF-8":
                    if ar[0].upper()=="C":
                        altret = ar[0] + "." + ar[1]
                    else:
                        return ar[0] + "." + ar[1]
        except:
            None        
        try:                
            p = subprocess.Popen("locale -a", stdout=subprocess.PIPE, shell=True)
            (po, pe) = p.communicate()
            p.wait()
            if len(po) > 0:
                po = utils.bytes_to_str(po, "utf8")
                arlines = po.split("\n")
                for r in arlines:
                    ar = r.split(".")
                    if len(ar)>1 and ar[0].upper()=="EN_US" and (ar[1].upper()=="UTF8" or ar[1].upper()=="UTF-8"):
                        if ar[0].upper()=="C":
                            altret = ar[0] + "." + ar[1]
                        else:
                            return ar[0] + "." + ar[1]
                #If not found get the first utf8
                for r in arlines:
                    ar = r.split(".")
                    if len(ar)>1 and (ar[1].upper()=="UTF8" or ar[1].upper()=="UTF-8"):
                        if ar[0].upper()=="C":
                            altret = ar[0] + "." + ar[1]
                        else:
                            return ar[0] + "." + ar[1]
        except:
            None
        return altret

class Mac():
        
    def __init__(self):
        self._dwaglib = None
        self._propguilnc = None #COMPATIBILITA VERSIONI PRECEDENTI
        self._propguilnc_semaphore = threading.Condition() #COMPATIBILITA VERSIONI PRECEDENTI
            
    def load_library(self):
        try:
            if self._dwaglib is None:
                lbn="dwaglib.dylib"
                #COMPATIBILITY BEFORE 14/11/2019
                if not utils.path_exists(".srcmode"):
                    if not utils.path_exists("native/"+lbn):
                        lbn="dwaglib.so"
                #COMPATIBILITY BEFORE 14/11/2019
                self._dwaglib = _load_lib_obj(lbn)
        except:
            None
    
    def unload_library(self):
        _unload_lib_obj(self._dwaglib)
        self._dwaglib=None
    
    def get_library(self):        
        return self._dwaglib
    
    def task_kill(self, pid) :
        try:
            os.kill(pid, -9)
        except OSError:
            return False
        return True
    
    def is_task_running(self, pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    
    def set_file_permission_everyone(self,f):
        utils.path_change_permissions(f, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
    
    def fix_file_permissions(self,operation,path,path_src=None):
        apppath=path
        if apppath.endswith(utils.path_sep):
            apppath=apppath[0:len(apppath)-1]
        apppath_src=path_src
        if apppath_src is not None:
            if apppath_src.endswith(utils.path_sep):
                apppath_src=apppath_src[0:len(apppath_src)-1]
        else:
            apppath_src=utils.path_dirname(path)    
        stat_info = utils.path_stat(apppath_src)
        mode = stat.S_IMODE(stat_info.st_mode)
        if operation=="CREATE_DIRECTORY":
            utils.path_change_permissions(path,mode)
            utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        elif operation=="CREATE_FILE":
            utils.path_change_permissions(path, ((mode & ~stat.S_IXUSR) & ~stat.S_IXGRP) & ~stat.S_IXOTH)
            utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        elif operation=="COPY_DIRECTORY" or operation=="COPY_FILE":
            utils.path_change_permissions(path,mode)
            stat_info = utils.path_stat(utils.path_dirname(path)) #PRENDE IL GRUPPO E L'UTENTE DELLA CARTELLA PADRE 
            utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
        elif operation=="MOVE_DIRECTORY" or operation=="MOVE_FILE":
            utils.path_change_permissions(path,mode)
            utils.path_change_owner(path, stat_info.st_uid, stat_info.st_gid)
    
    def is_gui(self):
        return True
    
    def get_console_user_id(self):
        return self._dwaglib.getConsoleUserId();
    
    #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE)
    def is_old_guilnc(self):
        #READ installer.ver
        bold=False
        try:
            sver="0"
            ptver="native" + os.sep + "installer.ver"
            if utils.path_exists(ptver):
                fver = utils.file_open(ptver, "rb")
                sver=utils.bytes_to_str(fver.read())
                fver.close()
            bold=(int(sver)==0)
        except:
            None
        return bold
    
    
    #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE)
    def _signal_handler(self, signal, frame):
        self._propguilnc_stop=True
    
    #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE)
    def start_guilnc(self):        
        self._propguilnc_stop=False
        signal.signal(signal.SIGTERM, self._signal_handler)
        bload=False
        suid=str(os.getuid())
        spid=str(os.getpid())
        lnc = ipc.Property()
        prcs = []
        try:
            while not self._propguilnc_stop and utils.path_exists("guilnc.run"):
                if not bload:
                    if lnc.exists("gui_launcher_" + suid):
                        try:
                            lnc.open("gui_launcher_" + suid)
                            lnc.set_property("pid", spid)
                            bload=True
                        except:
                            time.sleep(1)
                    else:
                        time.sleep(1)
                if bload:
                    if lnc.get_property("state")=="LNC":
                        popenar=[]
                        popenar.append(sys.executable)
                        popenar.append("agent.py")
                        popenar.append(u"app=" + lnc.get_property("app"))
                        for i in range(GUILNC_ARG_MAX):
                            a = lnc.get_property("arg" + str(i))
                            if a=="":
                                break;
                            popenar.append(a)
                        libenv = os.environ
                        libenv["LD_LIBRARY_PATH"]=utils.path_absname("runtime/lib")
                        #print("Popen: " + " , ".join(popenar))
                        try:
                            p = subprocess.Popen(popenar, env=libenv)
                            prcs.append(p)
                            #print("PID: " + str(p.pid))
                            if p.poll() is None:
                                lnc.set_property("state", str(p.pid))
                            else:
                                lnc.set_property("state", "ERR")
                        except:
                            lnc.set_property("state", "ERR")
                    time.sleep(0.2)
                #Pulisce processi
                prcs = [p for p in prcs if p.poll() is None]
        finally:
            if bload:
                lnc.close()
    
    #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE)
    def init_guilnc(self,ag):
        if self.is_old_guilnc():
            self._propguilnc_semaphore.acquire()
            try:
                #COMPATIBILITA VERSIONI PRECEDENTI
                if utils.path_exists("native/dwagguilnc"):
                    self._propguilnc = {}
                    if not utils.path_exists("guilnc.run"):
                        f = utils.file_open("guilnc.run","wb")
                        f.close()
            finally:
                self._propguilnc_semaphore.release()                        
    
    #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE)
    def term_guilnc(self):
        if self.is_old_guilnc():
            self._propguilnc_semaphore.acquire()
            try:
                if utils.path_exists("guilnc.run"):
                    utils.path_remove("guilnc.run")
                if self._propguilnc is not None:
                    for l in self._propguilnc:
                        self._propguilnc[l].close()
                    self._propguilnc=None
            finally:
                self._propguilnc_semaphore.release()            
    
    #GUI LAUNCHER OLD VERSION 03/11/2021 (DO NOT REMOVE)
    def exec_guilnc(self, uid, app, args):
        self._propguilnc_semaphore.acquire()
        try:
            if self._propguilnc is not None:
                suid=str(uid)
                lnc = None
                if suid not in self._propguilnc:
                    lnc = ipc.Property()
                    fieldsdef=[]
                    fieldsdef.append({"name":"pid","size":20})
                    fieldsdef.append({"name":"state","size":20}) # ""=NESSUNA OPERAZIONE; "LNC"="ESEGUI"; "NUM"=PID ESEGUITO 
                    fieldsdef.append({"name":"app","size":100})
                    for i in range(GUILNC_ARG_MAX):
                        fieldsdef.append({"name":"arg" + str(i),"size":GUILNC_ARG_SIZE})
                    def fix_perm(fn):
                        utils.path_change_owner(fn, uid, -1)
                        utils.path_change_permissions(fn, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
                    lnc.create("gui_launcher_" + suid, fieldsdef, fix_perm)
                    self._propguilnc[suid]=lnc
                else:
                    lnc=self._propguilnc[suid]
                
                cnt=20.0                
                #PULISCE
                lnc.set_property("state","")
                lnc.set_property("app","")
                for i in range(GUILNC_ARG_MAX):
                    lnc.set_property("arg" + str(i),"")
                #RICHIESTA                        
                lnc.set_property("app", app)
                for i in range(len(args)):
                    lnc.set_property("arg" + str(i), args[i])
                st="LNC" 
                lnc.set_property("state", st)
                while st=="LNC" and cnt>0.0:
                    st = lnc.get_property("state")
                    time.sleep(0.2)
                    cnt-=0.2                        
                if st=="LNC":
                    lnc.set_property("state", "")
                    raise Exception("GUI launcher timeout.")
                if st=="ERR":
                    raise Exception("GUI launcher error.")
                return int(st)          
        finally:
            self._propguilnc_semaphore.release() 
        return None
    
    def reboot(self):
        os.system("shutdown -r now")