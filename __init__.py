from zim.plugins import PluginClass
from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog,ScrolledTextView

from zim.notebook.operations import NotebookState, ongoing_operation
from zim.newfs.helpers import FSObjectMonitor
from zim.newfs.base import _md5

from gi.repository import GObject, Gtk
import zim.plugins.diskmerger.diffs

import os, stat
import logging
import time
logger = logging.getLogger('zim.plugins.tags')

class MergerPlugin(PluginClass):
    plugin_info = {
        'name': _('Disk Change Merger'),
        'description': _('Gracefully merge changes done on disk'),
        'author': '',
        }
    plugin_preferences = (
    ##  #key, type, label, default,
      ('confirm', 'bool', _('Show and confirm changes before merging'), False, ),
      ('polltime', 'int', _('Actively poll for changes on disk (s), 0 disables'), 0, (0,10)),
    )

class ConfirmDialog(Dialog):
    '''Dialog for showing the diff and choosing if it is saved or discarded'''
    def __init__(self,parent,title,content):
        Dialog.__init__(self,parent.pageview.get_toplevel(),title)
        self.add_text('Detected changes on disk. Ok to merge them, Keep disk or buffer to only keep one source')
        self.parent = parent
        window, textview = ScrolledTextView("".join(content), monospace=True)
        window.set_size_request(400, 350)
        window.set_property('expand', True)
        self.vbox.add(window)
        self.vbox.show_all()
        self.set_resizable(True)
        self.parent.merge_changes = 'cancel' #default for cancel
        btn = Gtk.Button('Keep disk')
        btn.connect('clicked', self.do_keep_disk)
        self.add_extra_button(btn)
        btn = Gtk.Button('Keep Buffer')
        btn.connect('clicked', self.do_keep_buffer)
        self.add_extra_button(btn)

    def do_response_ok(self):
        self.parent.merge_changes = 'merge'
        return 1
    def do_keep_disk(self, btn):
        self.parent.merge_changes = 'disk'
        self.close()
        return 1
    def do_keep_buffer(self, btn):
        self.parent.merge_changes = 'buffer'
        self.close()
        return 1


################################################################################
class MergerPageViewExtension(PageViewExtension):
    def __init__(self, plugin, notebookview):
        #init the parent and store arguments
        PageViewExtension.__init__(self, plugin, notebookview)
        self.notebook = notebookview.notebook
        self.plugin = plugin
        page = self.pageview.page

        self.blocked = False #switch for allowing saving
        self._autoload_timer = None #for disk polling

        self.old_lines, self.old_etag = None, (None, None)
        if page.source_file.exists():  #get the initial contents on disk
            self.old_lines, self.old_etag = page.source_file.read_with_etag()
            self.old_lines = self.old_lines.split('\n')
            self.old_lines = ["\n".join(self.old_lines[0:3])] + self.old_lines[3:]
            self.old_lines = [x+"\n" for x in self.old_lines]



        #connect to signals from notebook and file
        self.connectto(notebookview, 'page-changed', self.on_page_change)
        #self.connectto(notebookview.notebook,'store-page',func)
        self.connect_file_monitor()
    
        #intercept page saving methods, store originals
        self.try_save_page_orig = self.pageview._save_page_handler.try_save_page
        self.pageview._save_page_handler.try_save_page = self.try_save_pagewrap

        self.do_try_save_page_orig = self.pageview._save_page_handler.do_try_save_page
        self.pageview._save_page_handler.do_try_save_page = self.do_try_save_pagewrap


    def on_page_change(self,*args,**kwargs):
        self.connect_file_monitor()
        return False

    def connect_file_monitor(self, *args, **kwargs):
        self._poll_file_timer(self.plugin.preferences['polltime'])

        filemonitor = FSObjectMonitor( self.pageview.page.source_file)
        self.connectto(filemonitor,'changed', self.on_file_changed)
        self.filemonitor = filemonitor #must store to keep running

         #set write permission umask bit of group the same as for the notebook root
        perms = os.stat(self.notebook.folder.path).st_mode & stat.S_IWGRP ^ (stat.S_IWGRP | stat.S_IWOTH)
        logger.debug('Setting file permission umask to %s from %s', str(oct(perms)), self.notebook.folder.path)
        os.umask(perms)
        return False

    def _poll_file_timer(self,timeout=5):
       if self._autoload_timer is not None:
           GObject.source_remove(self._autoload_timer)
           self._autoload_timer = None
       if timeout>0:
           logger.debug('Reset poll timer')
           self._autoload_timer = GObject.timeout_add(
                   timeout*1000, # s -> ms
                   #self.try_save_pagewrap
                   self.do_try_save_pagewrap
           )

    def on_file_changed(self,*args, **kwargs):
        self.do_try_save_pagewrap()

    def try_save_pagewrap(self, *args, **kwargs):
        #print('saving page with', args, kwargs)
        self.do_try_save_pagewrap(args, kwargs)

    def do_try_save_pagewrap(self,*args, **kwargs):
        if self.blocked or ongoing_operation(self.notebook):
            logger.debug('Saving aborted... Another saving process ongoing')
            return
        self.blocked = True #prevent concurrent processes
        #self.pageview.textview.set_property('editable',False)
        page = self.pageview.page
        
        #copied from original do_try_save_page
        self.pageview._save_page_handler.cancel_autosave()
        #reset poll timer
        self._poll_file_timer(self.plugin.preferences['polltime'])

        disklines, disk_etag = self.get_disk_text_etag()
        disklines = [ "".join(disklines[0:3])]+disklines[3:]
        
        last_tag = page._last_etag
        if last_tag is None: last_tag = (None, None)
        #if disk_etag[1] == page._last_etag[1]: #disk has not changed
        if disk_etag[1] == last_tag[1]: #disk has not changed
            #print('no need for extra actions, saving through zim')
            logger.debug('Saving... No conflicts')
            self.do_try_save_page_orig(args, kwargs)
            #self.old_etag = page._last_etag
            self.old_etag = last_tag
        else: #disk has changed
            logger.debug('Saving... Etag conflict detected.')
            self.merge_changes = 'merge'
            bufferlines = self.get_buffer_text()
            buf_etag = _md5(bufferlines)

            if self.plugin.preferences['confirm']:
                mdialog = ConfirmDialog(self,'Merge changes',"".join(diffs.unidiff2(bufferlines, disklines,'Buffer','Disk',nlines=1)))
                mdialog.run() #dialog changes value of merge_changes from 'cancel'
            
            if self.merge_changes == 'disk':
                newlines = disklines
                self.merge_disk_in_buffer(newlines,disk_etag)
            elif self.merge_changes == 'merge':
                newlines = self.get_merged_text(bufferlines, disklines)
                self.merge_disk_in_buffer(newlines,disk_etag)
            elif self.merge_changes == 'buffer':
                page.set_modified(True)
            page._last_etag = disk_etag #enable saving without errors
            self.old_etag = disk_etag
        
            self.old_lines = self.get_buffer_text()
            self.do_try_save_page_orig()
        self.blocked = False #allow saving again
        #self.pageview.textview.set_property('editable',True)

        perms = os.stat(self.notebook.folder.path).st_mode & stat.S_IWGRP ^ (stat.S_IWGRP | stat.S_IWOTH)
        os.umask(perms)
        #logger.debug('Setting file permission umask to %s from %s page %s', str(oct(perms)), self.notebook.folder.path,self.pageview.page.source_file)
        #perms = os.stat(self.notebook.folder.path).st_mode | stat.S_IWGRP | stat.S_IRGRP #& ^stat.S_IEXEC
        perms = os.stat(self.notebook.folder.path).st_mode 
        try:
            os.chmod(str(self.pageview.page.source_file), perms)
        except FileNotFoundError: pass

    def get_merged_text(self, bufferlines, disklines):
        page = self.pageview.page
        logger.debug('Merged text requested')
        if self.old_lines is None: #only 2-way merge can be used
            logger.debug('\n2way merge old_lines')
            output = diffs.diff2(bufferlines,disklines, include=(' ', '+'))
        else:
            #logger.debug('\n3way merge old_lines:\n\t'+'\t'.join(self.old_lines))
            logger.debug('\n3way merge old_lines')
            logger.debug('\nOLD LINES'.join(self.old_lines))
            logger.debug('\nNEW LINES b'.join(bufferlines))
            logger.debug('\nNEW LINES d'.join(disklines))
            output = diffs.diff3(bufferlines, self.old_lines, disklines)  #full 3way merge
            logger.debug('\nOUTPUT'.join(output))
            #breakpoint()
        logger.debug('Merged text ready')
        return output

    def merge_disk_in_buffer(self,newlines,disk_etag):
        page = self.pageview.page

        #HERE WRITING TO BUFFER NEEDS TO BE HALTED FOR A MOMENT to keep history synchronized
        self.pageview.textview.set_property('editable',False)

        self.old_etag = disk_etag
        if len(newlines)>0:
            self._settree_and_update_view(newlines)
            self.old_lines = newlines
        self.pageview.textview.set_property('editable',True)
        return True

    def get_disk_text_etag(self):
        page = self.pageview.page
        if page.source_file.exists():  #get the new contents on disk
            disktext, disk_etag = page.source_file.read_with_etag()
            disktree = page.format.Parser().parse(disktext)
        else:
            disktree = self.pageview.notebook.get_template(page)
            disk_etag = (None, None)
        disklines = page.format.Dumper().dump(disktree, file_output=False)
        return disklines, disk_etag
    
    def get_buffer_text(self):
        page = self.pageview.page
        buffer = page.get_parsetree()
        if buffer is None:
            buffer = self.pageview.notebook.get_template(page)
        bufferlines = page.format.Dumper().dump(buffer,file_output=True)
        return bufferlines
    
    def _settree_and_update_view(self, newlines):
        if len(newlines) == 0: return
        page = self.pageview.page

        #directly adapted from page.reload_textbuffer
        logger.debug('setting new tree with contents'+"\n".join(newlines))
        newtree = page.format.Parser().parse(newlines[2:])
        buffer = page._textbuffer
        page._textbuffer = None
        page._parsetree = None
        if buffer is not None:
            #tree = page.get_parsetree()
            page._textbuffer = buffer
            page._textbuffer.set_modified(False)
            #page._set_parsetree(tree)
            page._set_parsetree(newtree)
                # load new tree in buffer, undo-able in 1 step
                # private method circumvents readonly check !
            page.set_modified(False)
        #else do nothing - source will be read with next call to `get_parsetree()`
        return
