# -*- coding: utf-8 -*-

'''
This Source Code Form is subject to the terms of the Mozilla
Public License, v. 2.0. If a copy of the MPL was not distributed
with this file, You can obtain one at http://mozilla.org/MPL/2.0/.
'''

try:
    from . import messages
except: #FIX INSTALLER
    import messages
try:
    from . import gdi
except: #FIX INSTALLER
    import gdi
import os
import sys
import threading
import traceback
import utils

_WIDTH=780
_HEIGHT=510
_HEIGHT_BOTTOM=55
_WIDTH_LEFT=90
_CONTENT_WIDTH=_WIDTH-_WIDTH_LEFT
_CONTENT_HEIGHT=_HEIGHT-_HEIGHT_BOTTOM
_GAP_TEXT=20
_BUTTON_WIDTH=140
_BUTTON_HEIGTH=36
_BUTTON_GAP=10

class VarString:
        
    def __init__(self, value = None,  password= False):
        self._value=value
        self._password=password
    
    def is_password(self):
        return self._password
    
    def set(self, v):
        self._value=v
    
    def get(self):
        return self._value

class BaseUI:
    def __init__(self):
        self._cancel=False
        self._prev_step=None
        self._next_step=None
        self._key=None
        self._params={}
  
    def set_key(self,  k):
        self._key=k
        
    def get_key(self):
        return self._key
    
    def set_param(self,  k, v):
        self._params[k]=v
        
    def get_param(self, k, d=None):
        if k in self._params:
            return self._params[k]
        else:
            return d
        
    def is_next_enabled(self):
        return self._next_step is not None
    
    def is_back_enabled(self):
        return self._prev_step is not None
    
    def prev_step(self, np):
        self._prev_step=np
    
    def next_step(self, np):
        self._next_step=np
    
    def fire_prev_step(self):
        if self._prev_step is not None:
            return self._prev_step(self)
        return None
        
    def fire_next_step(self):
        if self._next_step is not None:
            return self._next_step(self)
        return None

class Message(BaseUI):
    def __init__(self, msg=''):
        BaseUI.__init__(self)
        self._message=msg
    
    def set_message(self, msg):
        self._message=msg
        
    def get_message(self):
        return self._message
    
class Inputs(BaseUI):
   
    def __init__(self):
        BaseUI.__init__(self)
        self._message=None
        self._arinputs=[]
    
    def set_message(self, msg):
        self._message=msg
        
    def get_message(self):
        return self._message
    
    def add(self, key, label, variable, mandatory):
        self._arinputs.append({'key':key,  'label':label,  'variable':variable,  'mandatory':mandatory })
    
    def get_inputs(self):
        return self._arinputs
    
    def fire_next_step(self):
        #Verifica mandatory
        for i in range(len(self._arinputs)):
            inp = self._arinputs[i]
            if inp['mandatory'] is True and inp['variable'].get().strip()=="":
                return ErrorDialog(messages.get_message("fieldRequired").format(inp['label']))
        return BaseUI.fire_next_step(self)

    def on_validate(self,e):
        for i in range(len(self._arinputs)):
            inp = self._arinputs[i]
            if inp["key"]==e["source"].get_name():
                inp["variable"].set(e["source"].get_text())
                break
        
class Chooser(BaseUI):
        
    def __init__(self):
        BaseUI.__init__(self)
        self._archooser=[]
        self._selected_key=None
        self._variable=None
        self._message=None
        self._message_hyperlink=[]
        self._message_height=100
        self._accept_key=None
        self._main=None
        self._selected=None
        
        
    def set_message(self, m):
        self._message=m
    
    def add_message_hyperlink(self, ps, ln, url):
        self._message_hyperlink.append({"start":ps, "length":ln, "url": url})
    
    def set_message_height(self, h):
        self._message_height=h
    
    def get_message_height(self):
        return self._message_height
    
    def get_message(self):
        return self._message
    
    def get_message_hyperlinks(self):
        return self._message_hyperlink
    
    def set_accept_key(self, k):
        self._accept_key=k
    
    def get_accept_key(self):
        return self._accept_key
    
    def is_accept_key(self,s):
        if self._accept_key is not None:
            ar = self._accept_key.split(";")
            for i in ar:
                if i==s:
                    return True
        return False
    
    def add(self, key, label):
        self._archooser.append({'key':key,  'label':label})
    
    def get_choices(self):
        return self._archooser
    
    def get_variable(self):
        return self._variable
        
    def set_variable(self, v):
        self._variable=v
    
    def fire_next_step(self):
        #Verifica se selezionato
        bok = False
        for i in range(len(self._archooser)):
            inp = self._archooser[i]
            if self._variable.get()==inp["key"]:
                bok = True
                break
        if not bok:
            return ErrorDialog(messages.get_message("mustSelectOptions"))
        return BaseUI.fire_next_step(self)
    
    def set_main(self, main):
        self._main=main
        self._disble_next_button()

    def on_selected(self,e):
        if e["action"]=="SELECTED":
            self.get_variable().set(e["source"].get_name())
            self._disble_next_button()
    
    def is_next_enabled(self):
        if self._main is not None and self.get_accept_key() is not None:
            if self.is_accept_key(self.get_variable().get()):
                return self._next_step is not None
            else:
                return False
        return self._next_step is not None
    
    def _disble_next_button(self):
        if self._main is not None and self.get_accept_key() is not None:
            if self.is_accept_key(self.get_variable().get()):
                self._main._enable_next_button()
            else:
                self._main._disable_next_button()


class Custom(BaseUI):
        
    def __init__(self):
        BaseUI.__init__(self)
        self._content=None
        
    def set_content(self, cnt):
        self._content=cnt
            
class ErrorDialog():
    
    def __init__(self, msg):
        self._message=msg
    
    def get_message(self):
        return self._message

class AsyncInvoke(threading.Thread):
    def __init__(self, main, func, callback=None):
        threading.Thread.__init__(self, name="User_Interface")
        self._func=func
        self._callback=callback
        self._main=main
    
    def run(self):
        try:
            self._main._wait_ui=None
            self._main.wait_message(messages.get_message("waiting"))
            ret=self._func()  
        except SystemExit:
            self._main._action=None
            self._main.close()
            return         
        except Exception as e:
            msg = e.__class__.__name__
            if e.args is not None and len(e.args)>0 and e.args[0] != '':
                msg = e.args[0]
            ret=ErrorDialog(messages.get_message('unexpectedError').format(msg))
        if self._callback is not None:
            self._callback(ret)

'''
class DialogMessage(gdi.DialogMessage):
    def on_keyboard(self,tp,c,shift,ctrl,alt,meta):
        if alt==1 and tp==u"CHAR" and c==u"o":
            self._ok_action(None)
        if alt==1 and tp==u"CHAR" and c==u"y":
            self._yes_action(None)
        if alt==1 and tp==u"CHAR" and c==u"n":
            self._no_action(None)
        #print(tp + " " + c + " " + str(alt))
        gdi.Window.on_keyboard(self, tp, c, shift, ctrl, alt, meta)

class Window(gdi.Window):
    def setUI(self,v):
        self._ui=v
    
    def on_keyboard(self,tp,c,shift,ctrl,alt,meta):
        if alt==1 and tp==u"CHAR" and c==u"c" and self._ui._cur_step_ui is not None:
            self._ui.close()
            return
        if alt==1 and tp==u"CHAR" and c==u"b" and self._ui._cur_step_ui is not None:
            if self._ui._cur_step_ui.is_back_enabled():
                self._ui.back()
            return
        if alt==1 and tp==u"CHAR" and c==u"n" and self._ui._cur_step_ui is not None:
            if self._ui._cur_step_ui.is_next_enabled():
                if hasattr(self._ui._cur_step_ui,"on_validate"):
                    fc = self.get_focus_component()
                    if fc is not None:
                        self._ui._cur_step_ui.on_validate({"source":fc})
                self._ui.next()
            return
        if alt==1 and tp==u"CHAR" and c==u"u" and self._ui._cur_step_ui is not None:
            if self._ui._cur_step_ui.on_selected:
                cmps = self._ui._pnlmain.get_components();
                for i in range(len(cmps)):
                    if i>=1:
                        rb = cmps[i]
                        if rb.get_selected():
                            if i>1:
                                rb.set_selected(False)
                                cmps[i-1].set_selected(True)
                                self._ui._cur_step_ui.on_selected({"source":cmps[i-1]})
                            break;
        if alt==1 and tp==u"CHAR" and  c==u"d" and self._ui._cur_step_ui is not None:
            if self._ui._cur_step_ui.on_selected:
                cmps = self._ui._pnlmain.get_components();
                for i in range(len(cmps)):
                    if i>=1:
                        rb = cmps[i]
                        if rb.get_selected():
                            if i<len(cmps)-1:
                                rb.set_selected(False)
                                cmps[i+1].set_selected(True)
                                self._ui._cur_step_ui.on_selected({"source":cmps[i+1]})
                            break;
        #print(tp + " " + c + " " + str(alt))
        gdi.Window.on_keyboard(self, tp, c, shift, ctrl, alt, meta)
'''
            
class UI():
    def __init__(self, params, step_init):
        self._title = "DWAgent"
        if "title" in params:
            self._title = utils.str_new(params["title"])
        self._logo = None
        self._topimage = None
        self._topinfo = None
        self._leftcolor = None
        if "logo" in params:
            self._logo = utils.str_new(params["logo"])
        if "topimage" in params:
            self._topimage = utils.str_new(params["topimage"])
        if "topinfo" in params:
            self._topinfo = utils.str_new(params["topinfo"])
        if "leftcolor" in params:
            self._leftcolor = params["leftcolor"]
        self._step_init=step_init
        self._cur_step_ui=None
        self._wait_ui=None
        self._wait_panel_on_destroy=None
        self._action=None
        self._closing=False
        self._is_raw_input=False
        self._gui_enable=False
        self._prev_msg_wait=""
        
    
    def set_action(self,f):
        self._action=f
    
    def is_gui(self):
        return self._gui_enable
    
    def start(self, bgui=True):
        if bgui:
            try:
                if gdi.is_linux():
                    if not "DISPLAY" in os.environ:
                        raise("NODIPLAY") 
                    d = os.environ["DISPLAY"]
                    if d is None or d=="":
                        raise("NODIPLAY")    
                self._gui_enable=True
                self._guimode_start()
            except Exception as e:
                if gdi.is_linux():
                    self._gui_enable=False
                    self._clmode_start()
                else:
                    raise e
        else:
            self._gui_enable=False
            self._clmode_start()
    
    def _prepare_step(self, stp):
        if not self._closing:
            self._prev_msg_wait=""
            self._prepare_buttons(stp)
            func = getattr(self,  '_show_' + stp.__class__.__name__ .lower())
            func(stp)
    
    def next(self):
        if self._gui_enable==True:            
            self._guimode_next(None)
        else:
            self._clmode_next()
            
    def back(self):
        if self._gui_enable==True:
            self._guimode_back(None)
        else:
            self._clmode_back()
    
    def _op_complete(self, app):
        if app is None and self._wait_ui is not None:
            self._prepare_step(self._cur_step_ui)
        elif app.__class__.__name__ .lower()=='errordialog':
            self._show_error(app.get_message())
        else:
            self._cur_step_ui = app
            self._prepare_step(self._cur_step_ui)
            
    def _signal_close(self, signal, frame):
        if self._gui_enable is False:
            print("")
        if self._is_raw_input:
            raise Exception("#EXIT");
        else:
            self.close()
    
    def _printcl(self, msg):
        #print("ENC:" + sys.stdout.encoding)
        if utils.is_py2():
            if sys.stdout.encoding is None:
                print(msg)
            else:
                print(msg.encode(sys.stdout.encoding,'replace'))
        else:
            print(msg)
    
    def _raw_input(self,msg,bpasswd=False):
        try:
            appmsg=msg + u" "
            if utils.is_py2():
                if sys.stdout.encoding is not None:
                    appmsg=appmsg.encode(sys.stdout.encoding,'replace')            
            self._is_raw_input=True
            if not bpasswd:
                if utils.is_py2():
                    sr = raw_input(appmsg)
                else:
                    sr = input(appmsg)
            else:
                import getpass
                sr = getpass.getpass(appmsg)
            if utils.is_py2():
                sr=sr.decode('utf-8','replace')            
            if sr.lower()==u"#exit":
                raise Exception("#EXIT")
            elif sr.lower()==u"#back":
                raise Exception("#BACK")
            self._is_raw_input=False
            return sr
        except Exception as e:
            self._is_raw_input=False
            msg = utils.exception_to_string(e)
            if msg==u"#EXIT":
                self.close()
            elif msg==u"#BACK":
                if self._cur_step_ui.is_back_enabled():
                    self._clmode_back()
                else:
                    return u""
            else:
                self._printcl(u"")
                self._printcl(u"")
                self._printcl(messages.get_message('unexpectedError').format(utils.str_new(traceback.format_exc())))
                self.close()
            return None
        
    
    def close(self):
        self._closing=True
        if self._action is not None:
            self._action({"action":"CLOSE"})
        if self._gui_enable is True:
            self._app.destroy()
                
        
    def _clmode_next(self):
        try:
            self.wait_message(messages.get_message("waiting"))
            ret=self._cur_step_ui.fire_next_step()
        except Exception:
            ret=ErrorDialog(messages.get_message('unexpectedError').format(utils.str_new(traceback.format_exc())))
        self._op_complete(ret)
    
    def _clmode_back(self):
        try:
            self.wait_message(messages.get_message("waiting"))
            ret=self._cur_step_ui.fire_prev_step()
        except Exception:
            ret=ErrorDialog(messages.get_message('unexpectedError').format(utils.str_new(traceback.format_exc())))            
        self._op_complete(ret)
     
    def _clmode_start(self):
        try:
            import signal 
            signal.signal(signal.SIGINT, self._signal_close)
            signal.signal(signal.SIGTERM, self._signal_close)
            signal.signal(signal.SIGQUIT, self._signal_close)
        except:
            None            
        
        self._printcl(u"")
        self._printcl(u"****************************************")
        self._printcl(messages.get_message('commands') + u":")
        self._printcl(u" #BACK <" + messages.get_message('enter')  + "> " + messages.get_message('toBack'))
        self._printcl(u" #EXIT <" + messages.get_message('enter')  + "> " + messages.get_message('toExit'))
        self._printcl(u"****************************************")            
        try:
            self._cur_step_ui=self._step_init(BaseUI())
            if isinstance(self._cur_step_ui,ErrorDialog):
                self._cur_step_ui=Message(self._cur_step_ui.get_message())
        except Exception as e:            
            self._cur_step_ui=Message("Error: " + utils.exception_to_string(e))        
        self._prepare_step(self._cur_step_ui)
        self._printcl(u"")
    
    def _guimode_next(self, e):
        if e["action"]=="PERFORMED":
            self._guimode_execute(self._cur_step_ui.fire_next_step, self._op_complete)
        
    def _guimode_back(self, e):
        if e["action"]=="PERFORMED":
            self._guimode_execute(self._cur_step_ui.fire_prev_step, self._op_complete)
        
    def _guimode_close_action(self, e):
        if e["action"]=="DIALOG_YES":
            self._guimode_execute(self.close)
    
    def _guimode_close(self, e):
        if e["action"]=="PERFORMED":
            if self._cur_step_ui is None or (self._cur_step_ui.is_next_enabled() or self._cur_step_ui.is_back_enabled()) :
                dlgerr = gdi.DialogMessage(gdi.DIALOGMESSAGE_ACTIONS_YESNO,gdi.DIALOGMESSAGE_LEVEL_INFO,parentwin=self._app, logopath=self._logo)
                dlgerr.set_title(self._title)
                dlgerr.set_message(messages.get_message('confirmExit'))
                dlgerr.set_action(self._guimode_close_action)
                dlgerr.show();
            else:
                self.close()
    
    def _guimode_action(self, e):
        if e["action"]==u"ONCLOSE":
            e["cancel"]=True
            if self._btclose.is_enable():
                self._guimode_close(e)
    
    def _guimode_step_init_start(self):
        self._guimode_execute(self._guimode_step_init, self._guimode_step_init_callback)        
    
    def _guimode_step_init(self):
        ui=None
        try:
            ui=self._step_init(BaseUI())
            if isinstance(ui,ErrorDialog):
                ui=Message(ui.get_message())
        except Exception as e:            
            ui=Message("Error: " + utils.exception_to_string(e))
        return ui
    
    def _guimode_step_init_callback(self,curui):
        self._cur_step_ui=curui
        self._prepare_step(self._cur_step_ui)
    
    
    def _guimode_start(self):
        
        gdi.gdw_lib() #Se non è presente la libreria va in errore quindi in modalita console
                
        self._top_height=0
        if self._topimage is not None:
            self._top_height=gdi.get_image_size(self._topimage)["height"]
        elif self._topinfo is not None:
            self._top_height=(22*len(self._topinfo.split("\n"))) + 10
        
        self._app = gdi.Window(gdi.WINDOW_TYPE_NORMAL_NOT_RESIZABLE, logopath=self._logo)
        #self._app = Window(gdi.WINDOW_TYPE_NORMAL_NOT_RESIZABLE, logopath=self._logo)
        #self._app.setUI(self)
        
        self._app.set_title(self._title)
        self._app.set_size(_WIDTH, _HEIGHT+self._top_height)
        self._app.set_show_position(gdi.WINDOW_POSITION_CENTER_SCREEN)
        self._app.set_action(self._guimode_action)
        
        pnl_left = gdi.Panel();
        pnl_left.set_position(0, self._top_height)
        pnl_left.set_size(_WIDTH_LEFT,_HEIGHT)
        
        if self._leftcolor is not None:
            pnl_left.set_background_gradient(self._leftcolor, "FFFFFF", gdi.GRADIENT_DIRECTION_LEFTRIGHT)
        else:
            pnl_left.set_background_gradient("83e5ff", "FFFFFF", gdi.GRADIENT_DIRECTION_LEFTRIGHT)
        self._app.add_component(pnl_left)
        
        if self._topimage is not None:
            pnl_top = gdi.ImagePanel();
            pnl_top.set_position(0, 0)
            pnl_top.set_filename(self._topimage)
            pnl_top.set_size(_WIDTH,self._top_height)
            self._app.add_component(pnl_top)
        elif self._topinfo is not None:
            pnl_top = gdi.Panel();
            pnl_top.set_position(0, 0)
            pnl_top.set_size(_WIDTH,self._top_height)
            pnl_top.set_background("d9d9d9")
            self._app.add_component(pnl_top)
            
            pnl_top_text = gdi.Label()
            pnl_top_text.set_position(10,0)
            pnl_top_text.set_size(_WIDTH-(2*10),self._top_height)
            pnl_top_text.set_wordwrap(True)
            pnl_top_text.set_foreground("000000")
                        
            pnl_top_text.set_text(self._topinfo)
            pnl_top.add_component(pnl_top_text)
        
        
        pnl_bottom = gdi.Panel();
        pnl_bottom.set_position(0, _CONTENT_HEIGHT+self._top_height)
        pnl_bottom.set_size(_WIDTH,_HEIGHT_BOTTOM)
        self._app.add_component(pnl_bottom)
        
        wbtn=_BUTTON_WIDTH
        hbtn=_BUTTON_HEIGTH
                
        self._btback = gdi.Button();
        self._btback.set_position(_BUTTON_GAP, _BUTTON_GAP)
        self._btback.set_size(wbtn, hbtn)
        self._btback.set_text(messages.get_message('back'))
        self._btback.set_enable(False);
        self._btback.set_action(self._guimode_back)
        pnl_bottom.add_component(self._btback)
                
        self._btnext = gdi.Button();
        self._btnext.set_position(_BUTTON_GAP+wbtn+5, _BUTTON_GAP)
        self._btnext.set_size(wbtn, hbtn)
        self._btnext.set_text(messages.get_message('next'))
        self._btnext.set_enable(False);
        self._btnext.set_action(self._guimode_next)
        pnl_bottom.add_component(self._btnext)
        
        self._btclose = gdi.Button();
        self._btclose.set_position(_WIDTH-wbtn-_BUTTON_GAP, _BUTTON_GAP)
        self._btclose.set_size(wbtn, hbtn)
        self._btclose.set_text(messages.get_message('close'))
        self._btclose.set_enable(False);
        self._btclose.set_action(self._guimode_close)
        pnl_bottom.add_component(self._btclose)
        
        self._pnlmain=None
        self._cur_step_ui=None
        self._step_init_run=False
        
        self._guimode_step_init_start()
        self._app.show()
        gdi.loop()
        
    
    def _guimode_execute(self, func, callback=None):
        ac = AsyncInvoke(self, func, callback)
        ac.start()
   
    def _prepare_main_panel(self):
        if self._gui_enable is True:
            if (self._pnlmain is not None):
                if self._wait_panel_on_destroy is not None:
                    self._wait_panel_on_destroy()
                    #print("self._pnlmain.remove_component(self._wait_panel)")
                    #self._pnlmain.remove_component(self._wait_panel)
                self._wait_panel_on_destroy=None
                self._pnlmain.remove_all_components()
            else:
                self._pnlmain = gdi.Panel();
                self._pnlmain.set_background("ffffff")
                self._pnlmain.set_position(_WIDTH_LEFT, self._top_height)
                self._pnlmain.set_size(_CONTENT_WIDTH,_CONTENT_HEIGHT)
                self._app.add_component(self._pnlmain)

    def _prepare_buttons(self,  curui):
        if self._gui_enable is True:
            self._btnext.set_enable(curui.is_next_enabled())
            self._btback.set_enable(curui.is_back_enabled())
            self._btclose.set_enable(True)
    
    def _disable_next_button(self):
        if self._gui_enable is True:
            self._btnext.set_enable(False)
    
    def _enable_next_button(self):
        if self._gui_enable is True:
            self._btnext.set_enable(True)
    
    def _show_error_gui_ok(self,e):
        if self._wait_ui is not None and e["action"]==u"MOUSECLICK":
            self._prepare_step(self._cur_step_ui)
            
    def _show_error(self,  msg):
        if self._gui_enable is True:
            dlgerr = gdi.DialogMessage(gdi.DIALOGMESSAGE_ACTIONS_OK,gdi.DIALOGMESSAGE_LEVEL_ERROR,parentwin=self._app, logopath=self._logo)
            dlgerr.set_title(self._title)
            dlgerr.set_message(msg)
            dlgerr.set_action(self._show_error_gui_ok)
            dlgerr.show();
        else:
            self._printcl(u"")
            self._printcl(messages.get_message('error') + u": " + msg)
            if self._raw_input(messages.get_message('pressEnter')) is not None:
                self._prepare_step(self._cur_step_ui)
            
    
    def wait_panel(self, pnl, ondestroy, allowclose=False):
        if self._gui_enable is True:
            self._btnext.set_enable(False)
            self._btback.set_enable(False)
            self._btclose.set_enable(allowclose)
            self._prepare_main_panel()
            self._wait_ui=None
            self._wait_panel_on_destroy=ondestroy
            self._pnlmain.add_component(pnl)
        else:
            self._show_error("wait_panel allowed only in gui mode.")
            
    
    def wait_message(self, msg, perc=None, progr=None, allowclose=False):
        if self._gui_enable is True:
            if perc is not None:
                msg=msg + "     (" + str(perc) + "%)"
            self._wait_message_gui(msg, progr, allowclose)
        else:
            if self._prev_msg_wait!=msg:
                self._prev_msg_wait=msg
                if allowclose:
                    msg+=u"\n\nCTRL+C " + messages.get_message('toExit') + u"\n" 
                self._printcl(msg) 
    
    def _wait_message_gui(self, msg, progr=None, allowclose=False):
        if self._wait_ui is None:
            self._btnext.set_enable(False)
            self._btback.set_enable(False)
            self._btclose.set_enable(allowclose)
            self._prepare_main_panel()
            lbl=gdi.Label()
            lbl.set_wordwrap(True)
            lbl.set_position(_GAP_TEXT,(_CONTENT_HEIGHT/2)-60)
            lbl.set_size(_CONTENT_WIDTH-(2*_GAP_TEXT),60)
            lbl.set_text_align(gdi.TEXT_ALIGN_LEFTTOP)
            self._pnlmain.add_component(lbl)
            pbar = gdi.ProgressBar()
            pbar.set_position(_GAP_TEXT,_CONTENT_HEIGHT/2)
            pbar.set_size(_CONTENT_WIDTH-(4*_GAP_TEXT),24)
            self._pnlmain.add_component(pbar)
            self._wait_ui={'label':lbl, 'progress':pbar}
        else:
            self._btclose.set_enable(allowclose)
            lbl=self._wait_ui['label']
            pbar=self._wait_ui['progress']
        
        if 'label_value' not in self._wait_ui or self._wait_ui['label_value'] !=msg:
            lbl.set_text(msg)
        self._wait_ui['label_value']=msg
        if progr is None:
            if 'progress_value' not in self._wait_ui or self._wait_ui['progress_value'] is not None:
                pbar.set_y(-100)
                lbl.set_y(0)
                lbl.set_height(_CONTENT_HEIGHT)
                lbl.set_text_align(gdi.TEXT_ALIGN_LEFTMIDDLE)
            self._wait_ui['progress_value']=None
        else:
            if 'progress_value' not in self._wait_ui  or self._wait_ui['progress_value'] is None or self._wait_ui['progress_value']!=progr:
                lbl.set_y((_CONTENT_HEIGHT/2)-40)
                lbl.set_height(30)
                lbl.set_text_align(gdi.TEXT_ALIGN_LEFTTOP)
                pbar.set_y(_CONTENT_HEIGHT/2)
                pbar.set_percent(progr)                
            self._wait_ui['progress_value']=progr
            
            
        
    def _clmode_read(self, msg,  bpwd=False):
        ui = self._cur_step_ui;
        if not ui.is_next_enabled() and not ui.is_back_enabled():
            self.close()
            return None #Termina Installazione
        if not bpwd:
            return self._raw_input(msg)
        else:
            return self._raw_input(msg,True)
    
    def _show_message(self,  msg):
        if self._gui_enable is True:
            self._prepare_main_panel()
            w=_CONTENT_WIDTH-(2*_GAP_TEXT)
            h=_CONTENT_HEIGHT-(2*_GAP_TEXT)
            
            l = gdi.Label()
            l.set_position(_GAP_TEXT,_GAP_TEXT)
            l.set_size(w,h)
            l.set_wordwrap(True)
            l.set_text(msg.get_message())
            self._pnlmain.add_component(l)
        else:
            self._printcl(u"")
            self._printcl(msg.get_message())
            rd = self._clmode_read(messages.get_message('pressEnter'))
            if rd is not None:
                self._clmode_next()

    def _show_inputs(self,  inps):
        if self._gui_enable is True:
            self._prepare_main_panel()
            w=_CONTENT_WIDTH-(2*_GAP_TEXT)
            h=100
            
            l = gdi.Label()
            l.set_position(_GAP_TEXT,_GAP_TEXT)
            l.set_size(w,h)
            l.set_wordwrap(True)
            l.set_text_align(gdi.TEXT_ALIGN_LEFTTOP)
            l.set_text(inps.get_message())
            self._pnlmain.add_component(l)

            lblw=210
            ar = inps.get_inputs()
            p=120
            for i in range(len(ar)):
                inp=ar[i]
                #LABEL
                l = gdi.Label()
                l.set_position(_GAP_TEXT,p)
                l.set_size(lblw-1,30)
                l.set_text(inp['label'])
                self._pnlmain.add_component(l)
                
                #TEXTBOX
                t = gdi.TextBox()
                t.set_name(inp['key'])
                t.set_position(_GAP_TEXT+lblw,p)
                t.set_size(_CONTENT_WIDTH-(4*_GAP_TEXT)-lblw,30)
                t.set_text(inp['variable'].get())
                if inp['variable'].is_password():
                    t.set_password_mask(True)
                self._pnlmain.add_component(t)
                t.set_validate(inps.on_validate)
                if i==0:
                    t.focus()
                p+=36
        else:
            self._printcl(u"")
            self._printcl(inps.get_message())
            ar = inps.get_inputs()
            for i in range(len(ar)):
                inp=ar[i]
                v=inp['variable'].get()
                if v is None:
                    v=u""
                if v!=u"" and not inp['variable'].is_password():
                    v=u" (" + v + u")"
                rd = self._clmode_read(inp['label']  +  v + u":", inp['variable'].is_password())
                if rd is not None:
                    if rd.strip()!=u"":
                        inp['variable'].set(rd)
                else:
                    return
            self._clmode_next()
                            
               
    def _show_chooser(self,  chs):
        if self._gui_enable is True:
            self._prepare_main_panel()
            h=chs.get_message_height()
            w=_CONTENT_WIDTH-(2*_GAP_TEXT)
            l = gdi.Label() 
            l.set_wordwrap(True)
            l.set_text_align(gdi.TEXT_ALIGN_LEFTTOP)
            l.set_text(chs.get_message())
            
            if len(chs.get_message_hyperlinks())>0:
                for i in range(len(chs.get_message_hyperlinks())):
                    itm=chs.get_message_hyperlinks()[i]
                    l.add_hyperlink("k" + str(i), itm["start"], itm["length"], itm["url"])  
            
            l.set_position(_GAP_TEXT, _GAP_TEXT)
            l.set_size(w, h)
            
            self._pnlmain.add_component(l)
        
            ar = chs.get_choices()
            p=h+_GAP_TEXT
            for i in range(len(ar)):
                inp=ar[i]
                rb = gdi.RadioButton()
                rb.set_text(inp['label'])
                rb.set_position(_GAP_TEXT, p)
                rb.set_size(_CONTENT_WIDTH-(2*_GAP_TEXT), 30)
                rb.set_name(inp['key'])
                rb.set_group("RADIOBUTTON")
                if chs.get_variable().get()==inp['key']:
                    rb.set_selected(True);
                rb.set_action(chs.on_selected)
                self._pnlmain.add_component(rb)
                p+=30
            chs.set_main(self)
        else:
            self._printcl(u"")
            self._printcl(chs.get_message())
            self._printcl(u"")
            ar = chs.get_choices()
            df = u""
            ar_idx_accept=[]
            idx_default=None
            for i in range(len(ar)):
                inp=ar[i]
                self._printcl(str(i+1) + u". " + inp['label'])
                if chs.get_variable().get()==inp['key']:
                    idx_default=i+1
                    df = u" (" + str(idx_default) + u")"
                if chs.is_accept_key(inp['key']):
                    ar_idx_accept.append(i+1)
            rd = self._clmode_read(messages.get_message('option') + df + u":")
            if rd is not None:
                if rd=="":
                    rd=str(idx_default)
                try:
                    ird=int(rd)
                    if (ird>len(ar)):
                        raise Exception("")
                    if len(ar_idx_accept) > 0:
                        serr=[]
                        berr=True
                        for idxcur in ar_idx_accept:
                            serr.append(str(idxcur))
                            if ird==idxcur:
                                berr=False
                        if berr:
                            self._show_error(messages.get_message('mustAccept').format((u" " + messages.get_message('or') + u" ").join(serr)))
                            return
                    inp=ar[ird-1]
                except:
                    self._show_error(messages.get_message('optionNotValid'))
                    return
                chs.get_variable().set(inp['key'])
                self._clmode_next()
               
   