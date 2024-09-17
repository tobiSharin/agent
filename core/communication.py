# -*- coding: utf-8 -*-

'''
This Source Code Form is subject to the terms of the Mozilla
Public License, v. 2.0. If a copy of the MPL was not distributed
with this file, You can obtain one at http://mozilla.org/MPL/2.0/.
'''

import ssl
import struct
import time
import socket
import threading
import xml.etree.ElementTree
import os
import math
import utils
import json

BUFFER_SIZE_MAX = 65536-10
BUFFER_SIZE_MIN = 1024


SIZE_INTEGER=math.pow(2,32)
SIZE_LONG=math.pow(2,64)


#_SOCKET_TIMEOUT_CONNECT = 10
_SOCKET_TIMEOUT_READ = 20

_cacerts_path="cacerts.pem"
_proxy_detected = {}
_proxy_detected["semaphore"]=threading.Condition()
_proxy_detected["check"] = False
_proxy_detected["info"] = None

def is_windows():
    return utils.is_windows()

def is_linux():
    return utils.is_linux()

def is_mac():
    return utils.is_mac()

def get_time():
    return utils.get_time()

def get_ssl_info():
    sslret=ssl.OPENSSL_VERSION + " ("
    #if hasattr(ssl, 'PROTOCOL_TLSv1_3'):
    #    sslret += "TLSv1.3"
    if hasattr(ssl, 'PROTOCOL_TLSv1_2'):
        sslret += "TLSv1.2" 
    elif hasattr(ssl, 'PROTOCOL_TLSv1_1'):
        sslret += "TLSv1.1"
    elif hasattr(ssl, 'PROTOCOL_TLSv1'):
        sslret += "TLSv1"
    else:
        sslret += "Unknown"
    sslret += ")"
    return sslret

def _get_ssl_ver():
    #if hasattr(ssl, 'PROTOCOL_TLSv1_3'):
    #    return ssl.PROTOCOL_TLSv1_3
    if hasattr(ssl, 'PROTOCOL_TLSv1_2'):
        return ssl.PROTOCOL_TLSv1_2 
    if hasattr(ssl, 'PROTOCOL_TLSv1_1'):
        return ssl.PROTOCOL_TLSv1_1
    if hasattr(ssl, 'PROTOCOL_TLSv1'):
        return ssl.PROTOCOL_TLSv1
    if hasattr(ssl, 'PROTOCOL_TLS'):
        return ssl.PROTOCOL_TLS
    return ssl.PROTOCOL_SSLv23 #DEFAULT

def _connect_proxy_http(sock, host, port, proxy_info):
    usr = proxy_info.get_user()
    pwd = proxy_info.get_password()
    arreq=[]
    arreq.append("CONNECT %s:%d HTTP/1.0" % (host, port))
    if usr is not None and len(usr)>0:
        auth=utils.bytes_to_str(utils.enc_base64_encode(utils.str_to_bytes(usr + ":" + pwd,"utf8")))
        arreq.append("\r\nProxy-Authorization: Basic %s" % (auth))
    arreq.append("\r\n\r\n")
    sock.sendall(utils.str_to_bytes("".join(arreq)))
    resp = Response(sock)
    if resp.get_code() != '200':
        raise Exception("Proxy http error: " + str(resp.get_code()) + ".")
    

def _connect_proxy_socks(sock, host, port, proxy_info):
    usr = proxy_info.get_user()
    pwd = proxy_info.get_password()
    if proxy_info.get_type()=='SOCKS5':
        arreq = []
        arreq.append(struct.pack(">BBBB", 0x05, 0x02, 0x00, 0x02))
        sock.sendall(utils.bytes_join(arreq))
        resp = sock.recv(2)
        ver = utils.bytes_get(resp,0)
        mth = utils.bytes_get(resp,1)
        if ver!=0x05:
            raise Exception("Proxy socks error: Incorrect version.")
        if mth!=0x00 and mth!=0x02:
            raise Exception("Proxy socks error: Method not supported.")
        if mth==0x02:
            if usr is not None and len(usr)>0 and pwd is not None and len(pwd)>0:
                arreq = []
                arreq.append(struct.pack(">B", 0x01))
                arreq.append(struct.pack(">B", len(usr)))
                for c in usr:
                    arreq.append(struct.pack(">B", ord(c)))
                arreq.append(struct.pack(">B", len(pwd)))
                for c in pwd:
                    arreq.append(struct.pack(">B", ord(c)))                
                sock.sendall(utils.bytes_join(arreq))
                resp = sock.recv(2)
                ver = utils.bytes_get(resp,0)
                status = utils.bytes_get(resp,1)
                if ver!=0x01 or status != 0x00:
                    raise Exception("Proxy socks error: Incorrect Authentication.")
            else:
                raise Exception("Proxy socks error: Authentication required.")
        arreq = []
        arreq.append(struct.pack(">BBB", 0x05, 0x01, 0x00))
        try:
            addr_bytes = socket.inet_aton(host)
            arreq.append(b"\x01")
            arreq.append(addr_bytes)
        except socket.error:
            arreq.append(b"\x03")
            arreq.append(struct.pack(">B", len(host)))
            for c in host:
                arreq.append(struct.pack(">B", ord(c)))
        arreq.append(struct.pack(">H", port))
        sock.sendall(utils.bytes_join(arreq))
        resp = sock.recv(1024)
        ver = utils.bytes_get(resp,0)
        status = utils.bytes_get(resp,1)
        if ver!=0x05 or status != 0x00:
            raise Exception("Proxy socks error.")
    else:
        remoteresolve=False
        try:
            addr_bytes = socket.inet_aton(host)
        except socket.error:
            if proxy_info.get_type()=='SOCKS4A':
                addr_bytes = b"\x00\x00\x00\x01"
                remoteresolve=True
            else:
                addr_bytes = socket.inet_aton(socket.gethostbyname(host))
            
        arreq = []
        arreq.append(struct.pack(">BBH", 0x04, 0x01, port))
        arreq.append(addr_bytes)
        if usr is not None and len(usr)>0:
            for c in usr:
                arreq.append(struct.pack(">B", ord(c)))
        arreq.append(b"\x00")
        if remoteresolve:
            for c in host:
                arreq.append(struct.pack(">B", ord(c)))
            arreq.append(b"\x00")
        sock.sendall(utils.bytes_join(arreq))
        
        resp = sock.recv(8)
        if len(resp)<2:
            raise Exception("Proxy socks error.")
        if utils.bytes_get(resp,0) != 0x00:
            raise Exception("Proxy socks error.")
        status = utils.bytes_get(resp,1)
        if status != 0x5A:
            raise Exception("Proxy socks error.")

def _detect_proxy_windows():
    prxi=None
    try:
        sproxy=None
        import _winreg
        aReg = _winreg.ConnectRegistry(None,_winreg.HKEY_CURRENT_USER)
        aKey = _winreg.OpenKey(aReg, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        try: 
            subCount, valueCount, lastModified = _winreg.QueryInfoKey(aKey)
            penabled=False
            pserver=None
            for i in range(valueCount):                                           
                try:
                    n,v,t = _winreg.EnumValue(aKey,i)
                    if n.lower() == 'proxyenable':
                        penabled = v and True or False
                    elif n.lower() == 'proxyserver':
                        pserver = v
                except EnvironmentError:                                               
                    break
            if penabled and pserver is not None:
                sproxy=pserver
        finally:
            _winreg.CloseKey(aKey)   
        if sproxy is not None:
            stp=None
            sho=None
            spr=None            
            lst = sproxy.split(";")
            for v in lst:
                if len(v)>0:
                    ar1 = v.split("=")
                    if len(ar1)==1:
                        stp="HTTP"
                        ar2 = ar1[0].split(":")
                        sho=ar2[0]
                        spr=ar2[1]
                        break
                    elif ar1[0].lower()=="http":
                        stp="HTTP"
                        ar2 = ar1[1].split(":")
                        sho=ar2[0]
                        spr=ar2[1]
                        break
                    elif ar1[0].lower()=="socks":
                        stp="SOCKS5"
                        ar2 = ar1[1].split(":")
                        sho=ar2[0]
                        spr=ar2[1]
                    
            if stp is not None:
                prxi = ProxyInfo()
                prxi.set_type(stp)
                prxi.set_host(sho)
                prxi.set_port(int(spr))
                #print("PROXY WINDOWS DETECTED:" + stp + "  " + spr)
                
    except:
        None
    return prxi

def _detect_proxy_linux():
    prxi=None
    try:
        sprx=None
        sprx=os.getenv("all_proxy")
        if "http_proxy" in os.environ:
            sprx = os.environ["http_proxy"]
        elif "all_proxy" in os.environ:
            sprx = os.environ["all_proxy"]
        if sprx is not None:
            stp=None
            if sprx.endswith("/"):
                sprx=sprx[0:len(sprx)-1]            
            if sprx.lower().startswith("socks:"):
                stp="SOCKS5"
                sprx=sprx[len("socks:"):]
            elif sprx.lower().startswith("http:"):
                stp="HTTP"
                sprx=sprx[len("http:"):]
            if stp is not None:
                sun=None
                spw=None
                sho=None
                spr=None
                ar = sprx.split("@")
                if len(ar)==1:
                    ar1 = sprx[0].split(":")
                    sho=ar1[0]
                    spr=ar1[1]
                else: 
                    ar1 = sprx[0].split(":")
                    sun=ar1[0]
                    spw=ar1[1]
                    ar2 = sprx[1].split(":")
                    sho=ar2[0]
                    spr=ar2[1]
                prxi = ProxyInfo()
                prxi.set_type(stp)
                prxi.set_host(sho)
                prxi.set_port(int(spr))
                prxi.set_user(sun)
                prxi.set_password(spw)
    except:
        None
    return prxi

def release_detected_proxy():
    global _proxy_detected
    _proxy_detected["semaphore"].acquire()
    try:
        _proxy_detected["check"]=False
        _proxy_detected["info"]=None
    finally:
        _proxy_detected["semaphore"].release()

def _set_detected_proxy_none():
    global _proxy_detected
    _proxy_detected["semaphore"].acquire()
    try:
        _proxy_detected["check"]=True
        _proxy_detected["info"]=None
    finally:
        _proxy_detected["semaphore"].release()
    
def set_cacerts_path(path):
    global _cacerts_path
    _cacerts_path=path

def _connect_socket(host, port, proxy_info, timeout=_SOCKET_TIMEOUT_READ):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(timeout)
        bprxdet=False
        prxi=proxy_info
        if prxi is None or prxi.get_type() is None or proxy_info.get_type()=='SYSTEM':
            global _proxy_detected
            _proxy_detected["semaphore"].acquire()
            try:
                if not _proxy_detected["check"]:
                    try:
                        if is_windows():
                            _proxy_detected["info"] = _detect_proxy_windows()
                        elif is_linux():
                            _proxy_detected["info"] = _detect_proxy_linux()
                        elif is_mac():
                            _proxy_detected["info"]=None
                    except:
                        _proxy_detected=None
                if _proxy_detected is not None:
                    bprxdet=True
                    prxi = _proxy_detected["info"]
                _proxy_detected["check"]=True
            finally:
                _proxy_detected["semaphore"].release()
            
        conn_ex=None    
        func_prx=None
        if prxi is None or prxi.get_type() is None or prxi.get_type()=='NONE':
            sock.connect((host, port))
        elif prxi.get_type()=='HTTP':
            try:
                sock.connect((prxi.get_host(), prxi.get_port()))
                func_prx=_connect_proxy_http
            except:
                conn_ex=utils.get_exception()
        elif prxi.get_type()=='SOCKS4' or prxi.get_type()=='SOCKS4A' or prxi.get_type()=='SOCKS5':
            try:
                sock.connect((prxi.get_host(), prxi.get_port()))
                func_prx=_connect_proxy_socks
            except:
                conn_ex=utils.get_exception()
        else:
            sock.connect((host, port))
        
        if func_prx is not None:
            try:
                func_prx(sock, host, port, prxi)
            except:
                conn_ex=utils.get_exception()
        
        if conn_ex is not None:
            if bprxdet:
                try:
                    release_detected_proxy()
                    sock.close()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(timeout)
                    sock.connect((host, port)) #TRY TO CONNECT WITHOUT PROXY
                    _set_detected_proxy_none()
                    bprxdet=False
                except:
                    raise conn_ex
            else:
                raise conn_ex
                
        
        while True:
            try:
                #VALIDA CERITFICATI
                global _cacerts_path
                if hasattr(ssl, 'SSLContext'):
                    ctx = ssl.SSLContext(_get_ssl_ver())
                    if _cacerts_path!="":
                        ctx.verify_mode = ssl.CERT_REQUIRED
                        ctx.check_hostname = True
                        ctx.load_verify_locations(_cacerts_path)
                        sock = ctx.wrap_socket(sock,server_hostname=host)
                    else:
                        sock = ctx.wrap_socket(sock)
                else:
                    iargs = None
                    try:
                        import inspect
                        iargs = inspect.getargspec(ssl.wrap_socket).args
                    except:                   
                        None
                    if iargs is not None and "cert_reqs" in iargs and "ca_certs" in iargs and _cacerts_path!="": 
                        sock = ssl.wrap_socket(sock, ssl_version=_get_ssl_ver(), cert_reqs=ssl.CERT_REQUIRED, ca_certs=_cacerts_path)
                    else:
                        sock = ssl.wrap_socket(sock, ssl_version=_get_ssl_ver())
                break
            except:
                conn_ex=utils.get_exception()
                if bprxdet:
                    if "CERTIFICATE_VERIFY_FAILED" in str(conn_ex):
                        try: 
                            release_detected_proxy()
                            sock.close()
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            sock.settimeout(timeout)
                            sock.connect((host, port)) #TRY TO CONNECT WITHOUT PROXY
                            _set_detected_proxy_none()
                            bprxdet=False
                        except:
                            raise conn_ex
                    else:                        
                        raise conn_ex                    
                else:
                    raise conn_ex  
            
            
    except:
        e=utils.get_exception()
        sock.close()
        raise e
    return sock

def prop_to_xml(prp):
    ardata = []
    ardata.append('<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">');
    root_element = xml.etree.ElementTree.Element("properties")
    for key in prp:
        child = xml.etree.ElementTree.SubElement(root_element, "entry")
        child.attrib['key'] = key
        child.text = prp[key]
    ardata.append(utils.bytes_to_str(xml.etree.ElementTree.tostring(root_element)));
    return ''.join(ardata)

def xml_to_prop(s):
    prp = {}
    root = xml.etree.ElementTree.fromstring(utils.buffer_new(s,0,len(s)))
    for child in root:
        prp[child.attrib['key']] = child.text
    return prp

def _split_utl(url):
    lnhttps = 8
    #legge server e porta
    p=url[lnhttps:].find('/')
    host=url[lnhttps:lnhttps+p]
    port=443
    i=host.find(':')
    if i>=0:
        port=int(host[i+1:])
        host=host[:i]
    #Legge path
    u = url[p+lnhttps:]
    return {'host':host,  'port':port,  'path':u}

def download_url_file(urlsrc, fdest, proxy_info=None, response_transfer_progress=None):
    sredurl=None
    sp = _split_utl(urlsrc)
    #Richiesta al server
    sock = _connect_socket(sp["host"], sp["port"], proxy_info)
    try:
        req = Request("GET", sp["path"],  {'Host' : sp["host"] + ':' + str(sp["port"],),  'Connection' : 'close'})
        sock.sendall(req.to_message())
    
        #Legge risposta
        if utils.path_exists(fdest):
            utils.path_remove(fdest)
        ftmp = fdest + "TMP"
        if utils.path_exists(ftmp):
            utils.path_remove(ftmp)        
        resp = Response(sock, ftmp, response_transfer_progress)
        if resp.get_code() == '301':
            sredurl=resp.get_headers()["Location"]
        elif resp.get_code() != '200':
            raise Exception("Download error " + str(resp.get_code()) + ".")
    finally:
        sock.shutdown(1)
        sock.close();
    if sredurl is not None:
        download_url_file(sredurl, fdest, proxy_info, response_transfer_progress)
    else:
        if utils.path_exists(ftmp):
            utils.path_move(ftmp, fdest)

def get_url_prop(url, proxy_info=None):
    sredurl=None
    sp = _split_utl(url)    
    sock = _connect_socket(sp["host"], sp["port"], proxy_info)
    try:
        req = Request("GET", sp["path"],  {'Host' : sp["host"] + ':' + str(sp["port"],),  'Connection' : 'close'})
        sock.sendall(req.to_message())
        
        prpresp = None;
        resp = Response(sock)
        if resp.get_code() == '200':
            rtp="xml"
            try:
                hds = resp.get_headers()  
                if hds is not None and "Content-Type" in hds:
                    if hds["Content-Type"]=="application/json":
                        rtp="json"
            except:
                None
            if rtp=="json":
                prpresp = json.loads(resp.get_body())
            else:
                prpresp = xml_to_prop(resp.get_body())
        elif resp.get_code() == '301':
            sredurl=resp.get_headers()["Location"]
        else:
            raise Exception("Get url properties error " + str(resp.get_code())  + ".")
    finally:
        sock.shutdown(1)
        sock.close();
    if sredurl is not None:
        prpresp = get_url_prop(sredurl,proxy_info)
    return prpresp

def ping_url(url, proxy_info=None):
    tmret=-1
    try:
        tm=time.time()
        sp = _split_utl(url)
        sock = _connect_socket(sp["host"], sp["port"], proxy_info,timeout=2)
        try:
            req = Request("GET", sp["path"],  {'Host': sp["host"] + ':' + str(sp["port"],),  'Connection': 'close'})
            sock.sendall(req.to_message())
            resp = Response(sock)
            if resp.get_code() == '200':
                tmret=round(time.time()-tm,3)                
        finally:
            sock.shutdown(1)
            sock.close();
    except:
        None
    return tmret

class ProxyInfo:
    def __init__(self):
        self._type="None"
        self._host=None
        self._port=None
        self._user=None
        self._password=None
        
    def set_type(self, ptype):
        self._type=ptype
    
    def set_host(self, host):
        self._host=host
        
    def set_port(self, port):
        self._port=port
    
    def set_user(self,  user):
        self._user=user
    
    def set_password(self,  password):
        self._password=password
    
    def get_type(self):
        return self._type
    
    def get_host(self):
        return self._host
        
    def get_port(self):
        return self._port
    
    def get_user(self):
        return self._user
    
    def get_password(self):
        return self._password
        

class Request:
    def __init__(self, method, url, prp=None):
        self._method = method
        self._url = url
        self._prp = prp
        self._body = None

    def set_body(self, body):
        self._body = body

    def to_message(self):
        arhead = []
        arhead.append(self._method)
        arhead.append(' ')
        arhead.append(self._url)
        arhead.append(' ')
        arhead.append('HTTP/1.1')
        if self._prp is not None:
            for k in self._prp:
                arhead.append('\r\n')
                arhead.append(k)
                arhead.append(': ')
                arhead.append(self._prp[k])
            
        if self._body is not None:
            arhead.append('\r\n')
            arhead.append('Compression: zlib')
            arhead.append('\r\n')
            arhead.append('Content-Length: ')
            arhead.append(str(len(self._body)));
        arhead.append('\r\n')
        arhead.append('\r\n')
        if self._body is not None:
            arhead.append(self._body)
        return utils.str_to_bytes(''.join(arhead))

class Response_Transfer_Progress:
    
    def __init__(self, events=None):
            self._on_data=None
            self._properties={}
            self._byte_transfer=0
            self._byte_length=0
            if events is not None:
                if 'on_data' in events:
                    self._on_data=events['on_data']
    
    def set_property(self, key, value):
        self._properties[key]=value
    
    def get_property(self, key):
        if key not in self._properties:
            return None
        return self._properties[key]
    
    def get_byte_transfer(self):
        return self._byte_transfer
    
    def get_byte_length(self):
        return self._byte_length
    
    def fire_on_data(self,  byte_transfer,  byte_length):
        self._byte_transfer=byte_transfer
        self._byte_length=byte_length
        if self._on_data is not None:
            self._on_data(self)

class Response:
    def __init__(self, sock, body_file_name=None,  response_transfer_progress=None):
        data = bytes()
        while utils.bytes_to_str(data).find('\r\n\r\n') == -1:
            app=sock.recv(1024 * 4)
            if app is None or len(app)==0:
                raise Exception('Close connection')
            data += app 
        ar = utils.bytes_to_str(data).split('\r\n\r\n')
        head = ar[0].split('\r\n')
        appbody = []
        appbody.append(data[len(ar[0])+4:])
        self._code = None
        self._headers = {}
        clenkey=None
        for item in head:
            if self._code is None:
                self._code = item.split(' ')[1]
            else:
                apppos = item.index(':')
                appk=item[0:apppos].strip()
                if appk.lower()=="content-length":
                    clenkey=appk
                self._headers[appk] = item[apppos+1:].strip()
        #Legge eventuale body
        if self._code != '301' and clenkey is not None:
            self._extra_data=None
            lenbd = int(self._headers[clenkey])
            fbody=None
            try:
                jbts=utils.bytes_join(appbody)
                if body_file_name is not None:
                    fbody=utils.file_open(body_file_name, 'wb')
                    fbody.write(jbts)
                cnt=len(jbts)
                if response_transfer_progress is not None:
                    response_transfer_progress.fire_on_data(cnt,  lenbd)
                szbuff=1024*2
                buff=None
                while lenbd > cnt:
                    buff=sock.recv(szbuff)
                    if buff is None or len(buff)==0:
                        break
                    cnt+=len(buff)
                    if response_transfer_progress is not None:
                        response_transfer_progress.fire_on_data(cnt,  lenbd)
                    if body_file_name is None:
                        appbody.append(buff)
                    else:
                        fbody.write(buff)
            finally:
                if fbody is not None:
                    fbody.close()
                else:
                    self._body=utils.bytes_join(appbody)
        else:
            self._extra_data=utils.bytes_join(appbody)
            if len(self._extra_data)==0:
                self._extra_data=None

    def get_extra_data(self):
        return self._extra_data

    def get_code(self):
        return self._code

    def get_headers(self):
        return self._headers
    
    def get_body(self):
        return self._body


class Worker(threading.Thread):
    
    def __init__(self, parent,  queue, i):
        self._parent = parent
        threading.Thread.__init__(self, name=self._parent.get_name() + "_" + str(i))
        self.daemon=True
        self._queue=queue
        
    def run(self):
        while not self._parent._destroy:
            func, args, kargs = self._queue.get()
            if func is not None:
                try: 
                    func(*args, **kargs)
                except: 
                    e=utils.get_exception()
                    self._parent.fire_except(e)
                self._queue.task_done()

class ThreadPool():
    
    def __init__(self, name, queue_size, core_size , fexcpt):
            self._destroy=False
            self._name=name
            self._fexcpt=fexcpt
            self._queue = utils.Queue(queue_size)
            for i in range(core_size):
                self._worker = Worker(self, self._queue, i)
                self._worker.start()
    
    def get_name(self):
        return self._name 

    def fire_except(self, e):
        if self._fexcpt is not None:
            self._fexcpt(e)

    def execute(self, func, *args, **kargs):
        if not self._destroy:
            self._queue.put([func, args, kargs])
    
    def destroy(self):
        self._destroy=True #DA GESTIRE


class QueueTask():
    
    def __init__(self, tpool):
        self._task_pool=tpool
        self._semaphore = threading.Condition()
        self.list = []
        self.running = False
        
    
    def _exec_func(self):
        while True:
            func = None
            self._semaphore.acquire()
            try:
                if len(self.list)==0:
                    self.running = False
                    break;
                func = self.list.pop(0)
            finally:
                self._semaphore.release()
            func();
                        
        
    def execute(self, f, only_if_empty=False):
        self._semaphore.acquire()
        try:
            if not self.running:
                self.list.append(f);
                self.running=True;
                self._task_pool.execute(self._exec_func)
            else:
                if only_if_empty:
                    if len(self.list)<2: #con < 2 sono sicuro che almeno l'ultimo viene eseguito
                        self.list.append(f)
                else:
                    self.list.append(f)
        finally:
            self._semaphore.release()
        
        
            
class BandwidthCalculator:
    
    def __init__(self, ckint=0.5, ccint=5.0):
        self._semaphore = threading.Condition()
        self._current_byte_transfered=0
        self._last_byte_transfered=0
        self._last_time=0
        self._bps=0
        self._buffer_size=BUFFER_SIZE_MIN
        self._check_intervall=ckint
        self._calc_intervall=ccint
        self._calc_ar=[]
        self._calc_elapsed=0
        self._calc_transfered=0
    
    def set_check_intervall(self,i):
        self._semaphore.acquire()
        try:
            self._check_intervall=i
        finally:
            self._semaphore.release()
    
    def get_check_intervall(self):
        self._semaphore.acquire()
        try:
            return self._check_intervall
        finally:
            self._semaphore.release()
            
    def add(self, c):
        self._semaphore.acquire()
        try:
            self._current_byte_transfered += c
            self._calculate()
        finally:
            self._semaphore.release()
    
    def _calculate(self):
        tm=get_time() 
        transfered=self._current_byte_transfered-self._last_byte_transfered
        elapsed = (tm - self._last_time)
        if elapsed<0:
            elapsed=0
            self._last_time=tm
        if elapsed>self._check_intervall:
            self._calc_ar.append({"elapsed":elapsed, "transfered":transfered})
            self._calc_elapsed+=elapsed
            self._calc_transfered+=transfered
            while len(self._calc_ar)>1 and self._calc_elapsed>self._calc_intervall:
                ar = self._calc_ar.pop(0)
                self._calc_elapsed-=ar["elapsed"]
                self._calc_transfered-=ar["transfered"]
            self._bps=int(float(self._calc_transfered)*(1.0/self._calc_elapsed))
            self._calculate_buffer_size()
            self._last_time=tm
            self._last_byte_transfered=self._current_byte_transfered        
    
    def get_bps(self):
        return self._bps
    
    def get_buffer_size(self):
        return self._buffer_size
    
    def _calculate_buffer_size(self):
        self._buffer_size=int(0.1*float(self._bps))
        if self._buffer_size<BUFFER_SIZE_MIN:
            self._buffer_size=BUFFER_SIZE_MIN
        elif self._buffer_size>BUFFER_SIZE_MAX:
            self._buffer_size=BUFFER_SIZE_MAX
        else:
            self._buffer_size=int((float(self._buffer_size)/512.0)*512.0)
        
    
    def get_transfered(self):
        self._semaphore.acquire()
        try:
            return self._current_byte_transfered
        finally:
            self._semaphore.release()

'''
class BandwidthLimiter:
    
    def __init__(self,sync=True):
        if sync:
            self._semaphore = threading.Condition()
        else:
            self._semaphore = None
        self._last_time=0
        self._bandlimit=0
        self._last_wait=0
        self._buffsz=0        
        self.set_bandlimit(0)
     
     
    def _semaphore_acquire(self):
        if self._semaphore is not None:
            self._semaphore.acquire()
    
    def _semaphore_release(self):
        if self._semaphore is not None:
            self._semaphore.release()
    
    def get_bandlimit(self):
        self._semaphore_acquire()
        try:
            return self._bandlimit
        finally:
            self._semaphore_release()
        
    def set_bandlimit(self,pbps):
        self._semaphore_acquire()
        try:
            if self._bandlimit==pbps:
                return
            if pbps>0:
                self._bandlimit=pbps
                self._buffsz=calculate_buffer_size(pbps)
            else:
                self._bandlimit=0
                self._buffsz=BUFFER_SIZE_MAX
        finally:
            self._semaphore_release()
        
    def get_buffer_size(self):
        self._semaphore_acquire()
        try:
            return self._buffsz
        finally:
            self._semaphore_release()
    
    def get_waittime(self, c):
        self._semaphore_acquire()
        try:
            tm=get_time() 
            timeout = 0
            if c > 0:
                if self._bandlimit > 0:
                    if tm>=self._last_time:
                        elapsed = (tm - self._last_time) - self._last_wait
                        maxt = float(self._bandlimit)*elapsed
                        timeout = float(c-maxt)/float(self._bandlimit) 
                        self._last_wait=timeout
                        if self._last_wait<-1.0:
                            self._last_wait=0.0
                        self._last_time=tm
                        if timeout < 0.0:
                            timeout=0.0
                    else:
                        self._last_time=tm 
                        self._last_wait=0.0
            return timeout
        finally:
            self._semaphore_release()
            
'''
            
class ConnectionCheckAlive(threading.Thread):
    _KEEPALIVE_INTERVALL = 30
    _KEEPALIVE_THRESHOLD = 5
    
    def __init__(self, conn):
        threading.Thread.__init__(self, name="ConnectionCheckAlive")
        self.daemon=True
        self._connection=conn
        self._counter=utils.Counter()
        self._connection_keepalive_send=False
        self._semaphore = threading.Condition()

    def _send_keep_alive(self):
        try:
            if not self._connection.is_close():
                self._connection._send_ws_ping()
                #print("SESSION - PING INVIATO!")                
        except:
            #traceback.print_exc()
            None

    def reset(self):
        self._semaphore.acquire()
        try:
            if self._connection_keepalive_send:
                #print("SESSION - PING RESET!")
                self._counter.reset()
                self._connection_keepalive_send = False
        finally:
            self._semaphore.release()
        
            
    def run(self):
        #print("Thread alive started: " + str(self._connection))        
        bfireclose=False
        while not self._connection.is_shutdown():
            time.sleep(1)
            self._semaphore.acquire()
            try:
                #Verifica alive
                if not self._connection_keepalive_send:                    
                    #print("Thread alive send counter: " + str(self._counter.get_value()) + " " + str(self._connection))                    
                    if self._counter.is_elapsed((ConnectionCheckAlive._KEEPALIVE_INTERVALL-ConnectionCheckAlive._KEEPALIVE_THRESHOLD)):
                        self._connection_keepalive_send=True
                        self._send_keep_alive()
                        #print("Thread alive send: " + str(self._connection))
                        
                else:
                    if self._counter.is_elapsed((ConnectionCheckAlive._KEEPALIVE_INTERVALL+ConnectionCheckAlive._KEEPALIVE_THRESHOLD)):
                        bfireclose=not self._connection.is_close()
                        break                  
            finally:
                self._semaphore.release()
        self._connection.shutdown();
        if bfireclose is True:
            self._connection.fire_close(True)        
        #print("Thread alive stopped: " + str(self._connection))

class ConnectionReader(threading.Thread):
    
    def __init__(self, conn):
        threading.Thread.__init__(self, name="ConnectionReader")
        self.daemon=True
        self._connection = conn

    def _read_fully(self, sock, ln):
        data = []
        cnt=0
        while ln > cnt:
            s = sock.recv(ln-cnt)
            if s is None or len(s) == 0:
                return ''
            self._connection._tdalive.reset();
            data.append(s)
            cnt+=len(s)
        return utils.bytes_join(data)
        
    
    def run(self):
        #print("Thread read started: " + str(self._connection))        
        bfireclose=False
        bconnLost=True
        sock = self._connection.get_socket()
        try:
            while not self._connection.is_shutdown():
                data = self._read_fully(sock, 2)
                if len(data) == 0:
                    bfireclose=not self._connection.is_close()
                    break
                else:
                    lendt=0;
                    bt1=utils.bytes_get(data,1);
                    if bt1 <= 125:
                        if bt1 > 0:
                            lendt = bt1;
                        else:
                            bt0=utils.bytes_get(data,0);
                            if bt0 == 136: #CLOSE  
                                bconnLost=False                              
                                bfireclose=not self._connection.is_close()
                                break
                            elif bt0 == 138: #PONG
                                #print("SESSION - PONG RICEVUTO!")
                                continue
                            else:
                                continue    
                    elif bt1 == 126:
                        data = self._read_fully(sock, 2)
                        if len(data) == 0:
                            bfireclose=not self._connection.is_close()
                            break
                        lendt=struct.unpack('!H',data)[0]
                    elif bt1 == 127:
                        data = self._read_fully(sock, 4)
                        if len(data) == 0:
                            bfireclose=not self._connection.is_close()
                            break
                        lendt=struct.unpack('!I',data)[0]
                    #Legge data
                    if lendt>0:
                        data = self._read_fully(sock, lendt)
                        if len(data) == 0:
                            bfireclose=not self._connection.is_close()
                            break
                    elif lendt==0:
                        data=""
                    else:
                        bfireclose=not self._connection.is_close()
                        break
                    self._connection.fire_data(data)
                    
        except:
            e=utils.get_exception()
            bfireclose=not self._connection.is_close()
            #traceback.print_exc()
            self._connection.fire_except(e) 
        self._connection.shutdown()
        if bfireclose is True:
            self._connection.fire_close(bconnLost)        
        #print("Thread read stopped: " + str(self._connection))
        

class Connection:
            
    def __init__(self, events):
        self._close=True
        self._connection_lost=False
        self._shutdown=False
        self._on_data= None
        self._on_close = None
        self._on_except = None
        if events is not None:
            if "on_data" in events:
                self._on_data = events["on_data"]
            if "on_close" in events:
                self._on_close = events["on_close"]
            if "on_except" in events:
                self._on_except = events["on_except"]
        self._lock_status = threading.Lock()
        self._lock_send = threading.Lock()
        self._proxy_info = None
        self._sock = None
        self._tdalive = None
        self._tdread = None
        #WEBSOCKET DATA
        self._ws_data_b0 = 0;
        self._ws_data_b0 |= 1 << 7;
        self._ws_data_b0 |= 0x2 % 128;
        self._ws_data_struct_1=struct.Struct("!BBI")
        self._ws_data_struct_2=struct.Struct("!BBBBI")
        self._ws_data_struct_3=struct.Struct("!BBII")
        #WEBSOCKET PING
        self._ws_ping_b0 = 0
        self._ws_ping_b0 |= 1 << 7;
        self._ws_ping_b0 |= 0x9 % 128;
        self._ws_ping_struct=struct.Struct("!BBI")
        #WEBSOCKET CLOSE
        self._ws_close_b0 = 0;
        self._ws_close_b0 |= 1 << 7;
        self._ws_close_b0 |= 0x8 % 128;
        self._ws_close_struct=struct.Struct("!BBI")
                
            
    def open(self, prop, proxy_info):
        
        if self._sock is not None:
            raise Exception("Already connect!")

        #Apre socket
        self._prop = prop
        self._proxy_info = proxy_info
        self._sock = _connect_socket(self._prop['host'], int(self._prop['port']), proxy_info)
        try:
            #Invia richiesta
            appprp = {}
            for k in prop:
                if prop[k] is not None:
                    appprp["dw_" + k]=prop[k];
                    
                    
            appprp["host"] = prop['host'] + ":" + prop['port']
            appprp["Connection"] = 'keep-alive, Upgrade'
            appprp["Upgrade"] = 'websocket'
            appprp["Sec-WebSocket-Key"] = 'XV3+Fd9KMg54tXP7Tsrl8Q=='
            appprp["Sec-WebSocket-Version"] = '13'
                    
            req = Request("GET", "/openraw.dw", appprp)
            self._sock.sendall(req.to_message())
    
            #Legge risposta
            resp = Response(self._sock);
            if resp.get_code() != '101':
                if resp.get_body() is not None:
                    raise Exception(resp.get_body())
                else:
                    raise Exception("Server error.")
                        
            self._close=False
            self._sock.settimeout(None)
            
            #Avvia thread alive
            self._tdalive = ConnectionCheckAlive(self)
            self._tdalive.start()
    
            #Avvia thread lettura
            self._tdread = ConnectionReader(self)
            self._tdread.start()
            return resp            
                            
        except:
            e=utils.get_exception()
            self.shutdown()
            raise e
    
    def get_socket(self):
        return self._sock
    
   
    def send(self, data):
        self._send_ws_data(data)
        
    def fire_data(self, dt):
        if self._on_data is not None:
            self._on_data(dt)        
            
    def fire_close(self,connlost):        
        with self._lock_status:
            self._connection_lost=connlost
            onc=self._on_close
            self._on_data= None
            self._on_close = None
            self._on_except = None
        if onc is not None:
            onc()
    
    def fire_except(self,e):  
        if self._on_except is not None:
            self._on_except(e) 
    
    def _send_ws_data(self,dt):
        if self._sock is None:
            raise Exception('connection closed.')
        self._lock_send.acquire()
        try:
            length = len(dt);
            if length <= 125:
                ba=bytearray(self._ws_data_struct_1.pack(self._ws_data_b0, 0x80|length,0)) #rnd=random.randint(0,2147483647)
            elif length <= 0xFFFF:
                ba=bytearray(self._ws_data_struct_2.pack(self._ws_data_b0, 0xFE,length >> 8 & 0xFF,length & 0xFF,0)) #rnd=random.randint(0,2147483647)
            else: 
                ba=bytearray(self._ws_data_struct_3.pack(self._ws_data_b0, 0xFF,length,0)) #rnd=random.randint(0,2147483647)
            ba+=dt
            utils.socket_sendall(self._sock,ba)
        finally:
            self._lock_send.release()
            
    def _send_ws_close(self):
        if self._sock is None:
            raise Exception('connection closed.')
        self._lock_send.acquire()
        try:
            utils.socket_sendall(self._sock,self._ws_close_struct.pack(self._ws_close_b0, 0x80 | 0, 0)) #rnd=random.randint(0,2147483647)
        finally:
            self._lock_send.release() 
    
    def _send_ws_ping(self):
        if self._sock is None:
            raise Exception('connection closed.')
        self._lock_send.acquire()
        try:
            utils.socket_sendall(self._sock,self._ws_ping_struct.pack(self._ws_ping_b0, 0x80 | 0, 0)) #rnd=random.randint(0,2147483647)
        finally:
            self._lock_send.release()

    def is_close(self):
        with self._lock_status:
            bret = self._close
        return bret
    
    def is_connection_lost(self):
        with self._lock_status:
            bret = self._connection_lost
        return bret        
    
    def is_shutdown(self):
        with self._lock_status:
            bret = self._shutdown
        return bret
    
    def close(self):
        bsendclose=False
        try:
            with self._lock_status:
                if not self._close:
                    self._close=True
                    bsendclose=True
                    self._on_data= None
                    self._on_close = None
                    self._on_except = None
                    #print("session send stream close.")
            if bsendclose:
                self._send_ws_close();
                #Attende lo shutdown
                cnt = utils.Counter()
                while not self.is_shutdown():
                    time.sleep(0.2)
                    if cnt.is_elapsed(10):
                        break
        except:
            None
            
    
    def shutdown(self):
        
        with self._lock_status:
            if self._shutdown:
                return
            self._close=True
            self._shutdown=True
        
        if self._sock is not None:
            #Chiude thread alive
            #if (self._tdalive is not None) and (not self._tdalive.is_close()):
            #    self._tdalive.join(5000)
            self._tdalive = None

            #Chiude thread read
            #if (self._tdread is not None) and (not self._tdread.is_close()):
            #    self._tdread.join(5000)
            self._tdread = None
            
            try:                
                self._sock.shutdown(socket.SHUT_RDWR)
            except:
                None
            try:
                self._sock.close()
            except:
                None
            self._sock = None
            self._prop = None
            self._proxy_info = None
        