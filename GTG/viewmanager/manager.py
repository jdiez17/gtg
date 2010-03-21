# -*- coding: utf-8 -*-
# pylint: disable-msg=W0201
# -----------------------------------------------------------------------------
# Getting Things Gnome! - a personal organizer for the GNOME desktop
# Copyright (c) 2008-2009 - Lionel Dricot & Bertrand Rousseau
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------


"""
Manager loads the prefs and launches the gtk main loop
"""
import gtk
import gobject

import GTG
from GTG.viewmanager.delete_dialog import DeletionUI
from GTG.taskbrowser.browser import TaskBrowser
from GTG.taskeditor.editor            import TaskEditor
from GTG.viewmanager.preferences      import PreferencesDialog
from GTG.viewmanager.dbuswrapper import DBusTaskWrapper
from GTG.tools                        import clipboard
from GTG.core.plugins.engine          import PluginEngine
from GTG.core.plugins.api             import PluginAPI
from GTG.tools.logger                 import Log

class Manager():

    ############## init #####################################################

    def __init__(self, req, config):
        self.config = config.conf_dict
        self.task_config = config.task_conf_dict
        self.req = req
        # Editors
        self.opened_task  = {}   # This is the list of tasks that are already
                                 # opened in an editor of course it's empty
                                 # right now
                                 
        self.browser = None
        self.pengine = None
        self.plugins = None
        self.plugin_api = None
        self.p_apis = []
                                 
        #Shared clipboard
        self.clipboard = clipboard.TaskClipboard(self.req)
        
        #Browser
        #FIXME : the browser should not be built by default and should be a 
        # window like another and not necessary (like the editor)
        self.open_browser()
        
        #Plugins (that needs to be after the browser, this is ugly)
        self.__init_plugin_engine()
        
        #Deletion UI
        self.delete_dialog = None
        
        #Preferences windows
        # Initialize "Preferences" dialog
        self.preferences = None
        
        #DBus
        DBusTaskWrapper(self.req, self)
        
    def __init_plugin_engine(self):
        #FIXME : the plugin engine should not require the browser.
        # It should be the browser that need the plugin engine
        # plugins - Init
        self.pengine = PluginEngine(GTG.PLUGIN_DIR)
        # loads the plugins in the plugin dir
        self.plugins = self.pengine.load_plugins()
        # initializes the plugin api class
        self.plugin_api = PluginAPI(window         = self.browser.window,
                                    config         = self.config,
                                    data_dir       = GTG.DATA_DIR,
                                    builder        = self.browser.builder,
                                    requester      = self.req,
                                    tagpopup       = self.browser.tagpopup,
                                    tagview        = self.browser.tags_tv,
                                    task           = None,
                                    texteditor     = None,
                                    quick_add_cbs  = self.browser.priv['quick_add_cbs'],
                                    browser        = self.browser)
        self.p_apis.append(self.plugin_api)
        # enable some plugins
        if len(self.pengine.plugins) > 0:
            # checks the conf for user settings
            if "plugins" in self.config:
                if "enabled" in self.config["plugins"]:
                    plugins_enabled = self.config["plugins"]["enabled"]
                if "disabled" in self.config["plugins"]:
                    plugins_disabled = self.config["plugins"]["disabled"]
                for name, plugin in self.pengine.plugins.iteritems():
                    if name in plugins_enabled and name not in plugins_disabled:
                        plugin.enabled = True
                    else:
                        # plugins not explicitly enabled are disabled
                        plugin.enabled = False
        # initializes and activates each plugin (that is enabled)
        self.pengine.activate_plugins(self.p_apis)
        
    ############## Browser #################################################

    def open_browser(self):
        if not self.browser:
            self.browser = TaskBrowser(self.req, self, self.config)

    #FIXME : the browser should not be the center of the universe.
    # In fact, we should build a system where view can register themselves
    # as "stay_alive" views. As long as at least one "stay_alive" view
    # is registered, gtg keeps running. It quit only when the last 
    # "stay_alive view" is closed (and then unregistered).
    # Currently, the browser is our only "stay_alive" view.
    def close_browser(self,sender=None):
        self.quit()

    def hide_browser(self,sender=None):
        self.browser.hide()

    def show_browser(self,sender=None):
        self.browser.show()
        
################# Task Editor ############################################


    def open_task(self, uid,thisisnew=False):
        """Open the task identified by 'uid'.

        If a Task editor is already opened for a given task, we present it.
        Else, we create a new one.
        """
        t = self.req.get_task(uid)
        tv = None
        if uid in self.opened_task:
            tv = self.opened_task[uid]
            tv.present()
        elif t:
            tv = TaskEditor(
                self.req, self, t, self.plugins, \
                taskconfig=self.task_config, \
                plugin_apis=self.p_apis,thisisnew=thisisnew,\
                clipboard = self.clipboard)
            #registering as opened
            self.opened_task[uid] = tv
        return tv

    def close_task(self, tid):
        # When an editor is closed, it should de-register itself.
        if tid in self.opened_task:
            #the following line has the side effect of removing the 
            # tid key in the opened_task dictionary.
            editor = self.opened_task[tid]
            if editor:
                editor.close()
                del self.opened_task[tid]
        else:
            print "the %s editor was already unregistered" %tid
            
################ Others dialog ############################################

    def show_preferences(self,sender=None):
        if not self.preferences:
            self.preferences = PreferencesDialog(self.pengine, self.p_apis)
        self.preferences.activate()
        
    def ask_delete_tasks(self, tids):
        if not self.delete_dialog:
            self.delete_dialog = DeletionUI(self.req)
        if self.delete_dialog.delete_tasks(tids):
            for t in tids:
                self.close_task(t)
            
### MAIN ###################################################################
    def main(self):
        gobject.threads_init()
        gtk.main()
        return 0
        
        
    def quit(self,sender=None):
        gtk.main_quit()
        #save opened tasks and their positions.
        open_task = []
        for otid in self.opened_task.keys():     
            open_task.append(otid)
            self.opened_task[otid].close()
        self.config["browser"]["opened_tasks"] = open_task
        
        # adds the plugin settings to the conf
        if len(self.pengine.plugins) > 0:
            self.config["plugins"] = {}
            self.config["plugins"]["disabled"] = \
              self.pengine.disabled_plugins().keys()
            self.config["plugins"]["enabled"] = \
              self.pengine.enabled_plugins().keys()
        # plugins are deactivated
        self.pengine.deactivate_plugins(self.p_apis)

